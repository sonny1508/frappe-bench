"""
Task.exp_start_date backfill — populate Expected Start Date from the historical
assignment date, for Tasks created in the last N days.

How it works
------------
`tabToDo` is a complete, durable assignment history for Tasks: assigning always
inserts a row (frappe/desk/form/assign_to.py), and un-assigning NEVER deletes
one — remove() sets status="Cancelled", close_all_assignments() sets "Closed",
clear() sets "Cancelled", all via todo.save(). So MIN/MAX(creation) over a
Task's ToDo rows is its first/latest assignment date. ToDo.date is the DUE date
and is deliberately not used.

One GROUP BY over tabToDo joined to tabTask produces every candidate, both
candidate dates, and both validation bounds. For each candidate we:

  1. Resolve the source date — resolve_assignment_date(), the same helper the
     live ToDo after_insert hook uses.
  2. Refuse the write if it would break erpnext's Task.validate_dates() —
     exp_start_date_block_reason(), again the same helper. A date past
     exp_end_date, or past the Project's expected_end_date, is not rejected by
     frappe.db.set_value, but WOULD throw InvalidDates on the Task's next
     ordinary save and leave it un-editable.
  3. frappe.db.set_value(..., update_modified=False) — the same write style as
     the live hook and as ToDo.update_in_reference(). Does not re-run Task
     validation, does not fire Task on_update (no Matrix notification storm, no
     Project re-costing, no nested-set rebuild), does not touch `modified`.

The ToDo join deliberately does NOT filter on status. 93 of the 554 Tasks in
the 100-day window have no Open ToDo left at all — every assignment was later
Closed or Cancelled. The live rule stamps the date at INSERT time, before any
later status change, so filtering on status='Open' here would miss those 93 and
would not replay history.

Idempotent: the candidate query filters on `exp_start_date IS NULL`, so a Task
that already has a value — from an earlier run, from the live hook, or set by
hand — is never selected and never overwritten. Re-runs are safe and converge.

Reversible: every Task this touches had exp_start_date = NULL beforehand, so
the reverse is unambiguous. Each applied run writes a JSON snapshot to
    sites/<site>/private/files/task_exp_start_backfill_<timestamp>.json
and returns the same list. revert() clears only the Tasks whose current value
still matches what the run wrote, so a later legitimate change is not clobbered.

Scope flags
-----------
  days             lookback on Task.creation. Default 100.
  include_started  True (default) — fill every assigned Task in the window,
                   including the 465 that already have act_start_date. These
                   Tasks have never held an exp_start_date, so there is no
                   value to protect; the live rule's act_start_date guard
                   exists to stop overwriting, not to stop first-filling.
                   False — replay the live rule exactly and skip them (89
                   tasks over 100d instead of 554).
                   NOTE at True: 42 of those already-started Tasks were last
                   assigned AFTER their act_start_date, so they end up with
                   exp_start_date > act_start_date. That trips no validation
                   (validate_dates only pairs exp_start/exp_end and
                   act_start/act_end) but it is odd-looking data.
  source           "latest" (default) — MAX(ToDo.creation), which is what the
                   live re-stamp-on-reassign rule converges to.
                   "first" — MIN(ToDo.creation), the original assignment.
                   38 of the 554 differ between the two.

Usage (always dry-run first!)
-----------------------------
    # Preview the agreed scope — 100 days, every assigned task (no writes):
    bench --site glenda-studio-portal.me execute \
        gs_customizations.maintenance.task_exp_start_backfill.run \
        --kwargs "{'days': 100, 'dry_run': True}"

    # Stage it: apply to 5 tasks only, eyeball them in the UI:
    bench --site glenda-studio-portal.me execute \
        gs_customizations.maintenance.task_exp_start_backfill.run \
        --kwargs "{'days': 100, 'dry_run': False, 'limit': 5}"

    # Apply for real:
    bench --site glenda-studio-portal.me execute \
        gs_customizations.maintenance.task_exp_start_backfill.run \
        --kwargs "{'days': 100, 'dry_run': False}"

    # Strict scope instead (exact replay of the live rule, 89 tasks):
    bench --site glenda-studio-portal.me execute \
        gs_customizations.maintenance.task_exp_start_backfill.run \
        --kwargs "{'days': 100, 'include_started': False, 'dry_run': False}"

NOTE: `bench execute` calls frappe.db.commit() unconditionally when the function
returns. The dry-run guarantee comes entirely from this module not writing —
not from any rollback. Take a backup before the first real run regardless:
    bench --site glenda-studio-portal.me backup

To reverse
----------
Take `snapshot` from the run output (it is printed and returned) and pass it back:

    # Preview the revert:
    bench --site glenda-studio-portal.me execute \
        gs_customizations.maintenance.task_exp_start_backfill.revert \
        --kwargs "{'snapshot': 'task_exp_start_backfill_20260825_150000.json', 'dry_run': True}"

    # Apply the revert:
    bench --site glenda-studio-portal.me execute \
        gs_customizations.maintenance.task_exp_start_backfill.revert \
        --kwargs "{'snapshot': 'task_exp_start_backfill_20260825_150000.json', 'dry_run': False}"
"""

import json
import os

import frappe
from frappe.utils import add_days, getdate, now_datetime, nowdate

from gs_customizations.overrides.erpnext.task.task import (
    exp_start_date_block_reason,
    resolve_assignment_date,
)

DEFAULT_DAYS = 100
SOURCES = ("latest", "first")
SNAPSHOT_PREFIX = "task_exp_start_backfill_"


def _candidates(cutoff, include_started):
    """Every backfillable Task, plus both candidate dates and both bounds, in ONE query.

    Idempotency lives in the WHERE clause: `t.exp_start_date IS NULL` means a Task
    that already has a value is never even a candidate. The column is nullable with
    no '0000-00-00' rows, so IS NULL is a sufficient test.

    The join mirrors the live hook's guards — allocated_to must be a real user, since
    a role-based ToDo is not an assignment to a person. It does NOT filter on
    ToDo.status; see the module docstring for why.

    Every non-aggregated column is listed in GROUP BY (this MariaDB does not run
    ONLY_FULL_GROUP_BY, but do not depend on that).
    """
    conditions = ""
    if not include_started:
        conditions = " AND t.act_start_date IS NULL"

    return frappe.db.sql(
        f"""
        SELECT
            t.name              AS task,
            t.project           AS project,
            t.status            AS status,
            t.modified          AS modified,
            t.exp_end_date      AS exp_end_date,
            t.act_start_date    AS act_start_date,
            p.expected_end_date AS project_end_date,
            MIN(d.creation)     AS first_assigned,
            MAX(d.creation)     AS last_assigned,
            COUNT(d.name)       AS todo_count
        FROM `tabTask` t
        INNER JOIN `tabToDo` d
                ON d.reference_type = 'Task'
               AND d.reference_name = t.name
               AND d.allocated_to IS NOT NULL
               AND d.allocated_to != ''
        LEFT JOIN `tabProject` p
               ON p.name = t.project
        WHERE t.creation >= %(cutoff)s
          AND t.exp_start_date IS NULL
          {conditions}
        GROUP BY
            t.name, t.project, t.status, t.modified,
            t.exp_end_date, t.act_start_date, p.expected_end_date
        ORDER BY t.creation
        """,
        {"cutoff": cutoff},
        as_dict=True,
    )


def _process_one(row, source, dry_run):
    """Resolve, bound-check and (optionally) write one Task."""
    result = {
        "task": row.task,
        "project": row.project,
        "todo_count": row.todo_count,
        "status": None,
        "set_to": None,
        # Recorded so verify() can prove update_modified=False did its job. On a
        # busy site a global `modified` fingerprint drifts from ordinary user
        # traffic, so the check has to be per-task and captured at write time.
        "modified_before": str(row.modified),
    }

    raw = row.last_assigned if source == "latest" else row.first_assigned
    if not raw:
        result["status"] = "skip:no-assignment-date"
        return result

    assignment_date = resolve_assignment_date(raw)
    result["set_to"] = str(assignment_date)

    reason = exp_start_date_block_reason(
        assignment_date, row.exp_end_date, row.project_end_date
    )
    if reason:
        result["status"] = f"skip:{reason}"
        return result

    if dry_run:
        result["status"] = "would-apply"
        return result

    # Per-row set_value rather than one bulk UPDATE ... JOIN: set_value calls
    # frappe.clear_document_cache() for each row. A bulk statement would leave
    # stale Task docs in redis and users would keep seeing the old NULL.
    frappe.db.set_value(
        "Task", row.task, "exp_start_date", assignment_date, update_modified=False
    )
    result["status"] = "applied"
    return result


def _write_snapshot(applied, meta):
    """Durable undo record.

    Written straight into the site's private files with no File doc, so it does not
    show up in the UI or in anyone's attachments.
    """
    filename = SNAPSHOT_PREFIX + now_datetime().strftime("%Y%m%d_%H%M%S") + ".json"
    path = frappe.get_site_path("private", "files", filename)
    with open(path, "w") as f:
        json.dump({"meta": meta, "applied": applied}, f, indent=2, default=str)
    return filename


def run(days=DEFAULT_DAYS, include_started=True, source="latest", limit=None, dry_run=True):
    """Backfill Task.exp_start_date from the historical assignment date.

    :param days: lookback window on Task.creation (default 100).
    :param include_started: when True (default) every assigned Task in the window is
        filled, including those that already have act_start_date. When False, those
        are skipped, which is the exact replay of the live rule.
    :param source: "latest" (default) or "first" assignment.
    :param limit: process at most this many Tasks — for a staged first run.
    :param dry_run: when True (default) nothing is written, only a preview returned.
    """
    if source not in SOURCES:
        frappe.throw(f"source must be one of {SOURCES}, got {source!r}")

    days = int(days)
    cutoff = add_days(nowdate(), -days)

    rows = _candidates(cutoff, include_started)
    if limit:
        rows = rows[: int(limit)]

    results = []
    for i, row in enumerate(rows, 1):
        try:
            results.append(_process_one(row, source, dry_run))
        except Exception as e:
            # Never let one bad row abort the batch. This also stops `bench execute`
            # from masking the real traceback: on any exception it retries the call
            # under eval() and you get a confusing NameError instead of your error.
            results.append(
                {
                    "task": row.task,
                    "project": row.project,
                    "todo_count": row.todo_count,
                    "status": f"skip:error:{type(e).__name__}",
                    "set_to": None,
                    "modified_before": str(row.modified),
                }
            )
            frappe.log_error(
                frappe.get_traceback(),
                f"gs_customizations: exp_start_date backfill failed for {row.task}",
            )

        if not dry_run and i % 100 == 0:
            print(f"  ... {i}/{len(rows)}")

    applied = [r for r in results if r["status"] == "applied"]

    snapshot = None
    if not dry_run:
        # ONE commit for the whole batch. ~554 single-column UPDATEs on a 1636-row
        # table is sub-second work, so there is no lock-duration argument for
        # batching — and one transaction makes the run atomic, which is what keeps
        # the snapshot file and the database from ever disagreeing.
        snapshot = _write_snapshot(
            applied,
            {
                "days": days,
                "cutoff": cutoff,
                "include_started": bool(include_started),
                "source": source,
                "limit": limit,
                "run_at": str(now_datetime()),
                "run_by": frappe.session.user,
            },
        )
        frappe.db.commit()

    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    print(f"\n=== Task exp_start_date backfill {'(DRY RUN)' if dry_run else '(APPLIED)'} ===")
    print(f"window: last {days} days (Task.creation >= {cutoff})")
    print(
        f"scope: {'all assigned tasks' if include_started else 'act_start_date IS NULL only'}"
        f" | source: {source} assignment" + (f" | limit: {limit}" if limit else "")
    )
    print(f"candidates: {len(rows)} | status breakdown: {summary}")
    if snapshot:
        print(f"undo snapshot: private/files/{snapshot}")
    print(f"{'TASK':<20}{'STATUS':<26}{'SET TO':<14}{'#TODO':>6}  PROJECT")
    for r in results:
        print(
            f"{r['task']:<20}{r['status']:<26}{str(r['set_to'] or ''):<14}"
            f"{r['todo_count']:>6}  {r['project'] or ''}"
        )

    return {
        "days": days,
        "cutoff": cutoff,
        "include_started": bool(include_started),
        "source": source,
        "dry_run": dry_run,
        "snapshot": snapshot,
        "summary": summary,
        "applied_count": len(applied),
        "results": results,
    }


def revert(snapshot=None, tasks=None, dry_run=True):
    """Undo a backfill run: clear exp_start_date back to NULL.

    :param snapshot: filename returned by run(), looked up in the site's private
        files. The safest option — it carries the value each Task was set to, so
        anything changed since is left alone.
    :param tasks: alternatively an explicit list of {"task": ..., "set_to": ...}
        dicts, or bare Task names (bare names clear unconditionally).
    :param dry_run: when True (default) nothing is written.
    """
    if snapshot:
        path = frappe.get_site_path("private", "files", snapshot)
        if not os.path.exists(path):
            frappe.throw(f"snapshot not found: {path}")
        with open(path) as f:
            tasks = json.load(f)["applied"]

    if not tasks:
        frappe.throw("pass either `snapshot` or `tasks`")

    results = []
    for entry in tasks:
        if isinstance(entry, str):
            name, expected = entry, None
        else:
            name, expected = entry["task"], entry.get("set_to")

        current = frappe.db.get_value("Task", name, "exp_start_date")

        if current is None:
            results.append({"task": name, "status": "skip:already-null"})
            continue

        if expected and getdate(current) != getdate(expected):
            results.append(
                {
                    "task": name,
                    "status": "skip:changed-since",
                    "current": str(current),
                    "expected": str(expected),
                }
            )
            continue

        if dry_run:
            results.append({"task": name, "status": "would-clear", "current": str(current)})
            continue

        frappe.db.set_value("Task", name, "exp_start_date", None, update_modified=False)
        results.append({"task": name, "status": "cleared", "was": str(current)})

    if not dry_run:
        frappe.db.commit()

    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    print(f"\n=== exp_start_date revert {'(DRY RUN)' if dry_run else '(APPLIED)'} ===")
    print(f"tasks: {len(results)} | status breakdown: {summary}")
    for r in results:
        print(f"{r['task']:<20}{r['status']}")

    return {"dry_run": dry_run, "summary": summary, "results": results}


def verify(snapshot):
    """Prove an applied run did exactly what it claimed, and nothing more.

    Two invariants, checked per Task against the snapshot rather than against a
    whole-table fingerprint — this site is actively used, so a global checksum
    drifts from ordinary user saves and proves nothing:

      * exp_start_date now equals the value the run wrote.
      * `modified` is byte-identical to what it was at write time, which is the
        direct evidence that update_modified=False held and that nobody got a
        spurious "Document has been modified" error out of this.

    A Task legitimately edited by a user after the run shows as "changed-since";
    that is information, not necessarily a failure. A "WRONG-VALUE" or a
    "modified-moved" is a real problem.

    Usage:
        bench --site glenda-studio-portal.me execute \
            gs_customizations.maintenance.task_exp_start_backfill.verify \
            --kwargs "{'snapshot': 'task_exp_start_backfill_<ts>.json'}"
    """
    path = frappe.get_site_path("private", "files", snapshot)
    if not os.path.exists(path):
        frappe.throw(f"snapshot not found: {path}")

    with open(path) as f:
        payload = json.load(f)

    applied = payload["applied"]
    problems = []
    ok = 0
    changed_since = 0

    for entry in applied:
        row = frappe.db.get_value(
            "Task", entry["task"], ["exp_start_date", "modified"], as_dict=True
        )
        if not row:
            problems.append((entry["task"], "MISSING", "task no longer exists"))
            continue

        value_ok = row.exp_start_date and getdate(row.exp_start_date) == getdate(entry["set_to"])
        modified_ok = str(row.modified) == entry.get("modified_before")

        if value_ok and modified_ok:
            ok += 1
        elif value_ok and not modified_ok:
            # Someone saved the Task after the run. Expected on a live site; the
            # value survived, which is what preserve_exp_start_date() is for.
            changed_since += 1
        elif not value_ok:
            problems.append(
                (entry["task"], "WRONG-VALUE",
                 f"expected {entry['set_to']}, found {row.exp_start_date}")
            )

    print(f"\n=== exp_start_date verify | {snapshot} ===")
    print(f"run at {payload['meta'].get('run_at')} by {payload['meta'].get('run_by')}")
    print(f"applied rows: {len(applied)}")
    print(f"  intact (value correct, modified untouched): {ok}")
    print(f"  value correct, saved by a user since:       {changed_since}")
    print(f"  PROBLEMS:                                   {len(problems)}")
    for name, kind, detail in problems:
        print(f"    {name:<20}{kind:<14}{detail}")

    return {
        "snapshot": snapshot,
        "applied": len(applied),
        "intact": ok,
        "changed_since": changed_since,
        "problems": [{"task": n, "kind": k, "detail": d} for n, k, d in problems],
    }
