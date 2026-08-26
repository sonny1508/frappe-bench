# Maintenance Scripts

`gs_customizations/maintenance/` — one-off data operations run by hand with
`bench execute`. Not patches: these are **not** in `patches.txt` and do not run on
`bench migrate`, because they should only ever execute when an operator decides to.

## The house pattern

Every script follows the same shape. Copy it.

- A long module docstring with **How it works**, an explicit **Idempotent**
  paragraph, a **To reverse** paragraph, and a literal `Usage (always dry-run first!)`
  block containing runnable commands.
- Module constants at the top; `_`-prefixed private helpers; one public `run(...)`.
- **`dry_run=True` by default.** Always.
- Per-record status strings — `applied` / `would-apply` / `skip:<reason>` — collected
  into a summary dict and printed as a table.
- Idempotency enforced by a pre-check, so re-runs converge instead of double-applying.
- A single `frappe.db.commit()` at the end, guarded by `if not dry_run`.

Two things about `bench execute` that shape the pattern:

- **It commits unconditionally** when the function returns. The dry-run guarantee comes
  entirely from the script not writing — not from any rollback.
- **It masks tracebacks.** On any exception it retries the call under `eval()` and you
  get a confusing `NameError` instead of your real error. Wrap per-record work in
  `try/except` so one bad row cannot abort the batch or hide the cause.

Return values are printed via `json.dumps`, so stringify dates before returning.

## `pto_reset.py`

Expires each employee's Paid Time Off balance held as of a cutoff (default
`2026-06-30`) by inserting one `is_expired` Leave Ledger Entry of `-X` dated on the
cutoff — without creating a new allocation and without touching leave applications.

```bash
bench --site glenda-studio-portal.me execute gs_customizations.maintenance.pto_reset.run \
    --kwargs "{'exclude': ['HR-EMP-00050'], 'dry_run': True}"
```

Idempotent via a `frappe.db.exists` check for an existing expiry entry on the cutoff.
Reverse by cancelling the created entry — allowed by `CustomLeaveLedgerEntry.on_cancel`.

## `task_exp_start_backfill.py`

Populates `Task.exp_start_date` from historical assignment dates in `tabToDo`.

```bash
# preview
bench --site glenda-studio-portal.me execute \
    gs_customizations.maintenance.task_exp_start_backfill.run \
    --kwargs "{'days': 100, 'dry_run': True}"

# apply
bench --site glenda-studio-portal.me execute \
    gs_customizations.maintenance.task_exp_start_backfill.run \
    --kwargs "{'days': 100, 'dry_run': False}"
```

| Parameter | Default | Meaning |
|---|---|---|
| `days` | 100 | Lookback on `Task.creation` |
| `include_started` | `True` | Also fill tasks that already have `act_start_date` |
| `source` | `"latest"` | `MAX(ToDo.creation)`, or `"first"` for `MIN` |
| `limit` | `None` | Cap the batch, for a staged first run |
| `dry_run` | `True` | |

Three entry points:

- `run(...)` — the backfill. Writes an undo manifest to
  `sites/<site>/private/files/task_exp_start_backfill_<timestamp>.json`.
- `verify(snapshot)` — checks, per task, that the value still matches what was written
  **and that `modified` never moved**. Use this rather than a whole-table checksum:
  the site is actively used, so a global fingerprint drifts from ordinary user saves
  and proves nothing.
- `revert(snapshot)` — clears only the tasks whose current value still matches what
  the run wrote; anything edited since is reported as `skip:changed-since` and left alone.

Two details worth preserving if you adapt it:

- The ToDo join deliberately does **not** filter on `status`. Many tasks have no `Open`
  ToDo left — every assignment was later Closed or Cancelled — and the value is stamped
  at insert time, before any later status change. Filtering on `Open` would miss them.
- Per-row `frappe.db.set_value` rather than one bulk `UPDATE ... JOIN`, because
  `set_value` calls `frappe.clear_document_cache` for each row. A bulk statement leaves
  stale documents in redis and users keep seeing the old value.

## Running any of these safely

1. `bench --site glenda-studio-portal.me backup` first. A manifest is a targeted undo,
   not a substitute for a backup.
2. Dry-run and read the summary table.
3. Apply with `limit` first if the script supports it, and eyeball the result.
4. Apply fully, then verify.

Prefer running outside working hours. Writes use `update_modified=False`, which means
a form somebody already has open will not be told the record changed — and could write
its stale value back on save.
