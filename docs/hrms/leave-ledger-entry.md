# Leave Ledger Entry Override

`overrides/hrms/leave_ledger_entry/leave_ledger_entry.py` —
`CustomLeaveLedgerEntry(Document)`.

This site runs **duration-based** (seconds) leave rather than day-based, and the
override exists mainly to support that plus mid-year PTO expiry. It reimplements from
`Document` rather than subclassing the HRMS controller.

## What it changes

**`on_cancel` allows cancelling expiry entries.** Stock HRMS does not. Cancelling an
`is_expired` entry also resets `expired = 0` on the parent Leave Allocation. Anything
that is not an expiry entry still throws. This is what makes `pto_reset.py` reversible.

**`create_custom_leave_ledger_entry`** handles duration-based allocation amounts.

**`expire_allocation` is exposed via `override_whitelisted_methods`** so the desk can
call the patched version.

## The upstream bug this fixes — read before touching `delete_ledger_entry`

Cancelling a Leave Application used to **silently hard-delete an unrelated expiry
ledger entry**, handing expired hours back to the employee. It cost two real employees
(HR-EMP-00026 on 22/07, HR-EMP-00001 on 18/08) before it was found.

The mechanism, in stock HRMS:

1. `delete_ledger_entry` calls `get_previous_expiry_ledger_entry(ledger)` and then
   `DELETE ... WHERE transaction_name=%s OR name=%s` — **raw SQL**.
2. For a Leave Application, the `creation_date` lookup filters on
   `transaction_type="Leave Allocation"` under the *application's* name, so it never
   matches and falls back to `""`.
3. That makes the next query `creation LIKE "%"`, matching **any** of that employee's
   expiry entries.
4. The raw `DELETE` then removes it, leaving no `docstatus=2`, no Version row and no
   Deleted Document. There is no audit trace at all.

The override adds two guards:

```python
if ledger.transaction_type != "Leave Allocation":
    return None          # an application must never touch expiry entries

if not creation_date:
    return None          # never fall back to "" -> `creation LIKE "%"`
```

**If you refactor this file, keep both.** The failure is silent, destructive, and only
visible later as a wrong balance.

## Related

- `pto_reset.py` in [maintenance-scripts.md](../maintenance-scripts.md) creates the
  `is_expired` entries this override lets you cancel.
- `process_expired_allocation`, `expire_allocation` and
  `expire_carried_forward_allocation` are the scheduled/expiry paths.
