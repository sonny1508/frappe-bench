"""
PTO mid-year reset — expire each employee's Paid Time Off balance held as of a
cutoff date (default 30/06/2026), WITHOUT creating a new allocation and WITHOUT
touching any leave applications.

How it works
------------
Leave balance in this (duration/seconds-based) setup is computed per allocation
period. For each employee we:

  1. Find the submitted PTO allocation whose period contains the cutoff date.
  2. Compute X = net balance as of the cutoff
     (get_leave_balance_on(..., consider_all_leaves_in_the_allocation_period=False)).
  3. If X != 0: insert ONE `is_expired=1` Leave Ledger Entry of `-X`, dated on the
     cutoff, against that allocation. This clears the pre-cutoff balance to 0 while any
     accrual/leave dated after the cutoff keeps counting normally.
       - Positive X (balance held): entry is negative -> "Leave(s) Expired" shows +X,
         closing drops by X.
       - Negative X (balance owed): entry is positive -> the pre-cutoff debt is cleared,
         and (with the signed Expired column) "Leave(s) Expired" shows -|X|.
  4. If X == 0: SKIP (nothing to expire).

Idempotent: an employee that already has an `is_expired` entry dated on the cutoff
for that allocation is skipped, so re-runs are safe.

To reverse for an employee: cancel the `is_expired` Leave Ledger Entry created here
(this is allowed by the CustomLeaveLedgerEntry.on_cancel override).

Usage (always dry-run first!)
-----------------------------
    # Preview everyone (no writes):
    bench --site <site> execute gs_customizations.maintenance.pto_reset.run \
        --kwargs "{'exclude': ['HR-EMP-00050','HR-EMP-00045'], 'dry_run': True}"

    # Apply for real:
    bench --site <site> execute gs_customizations.maintenance.pto_reset.run \
        --kwargs "{'exclude': ['HR-EMP-00050','HR-EMP-00045'], 'dry_run': False}"

    # Restrict to a specific set of employees instead of "everyone":
    bench --site <site> execute gs_customizations.maintenance.pto_reset.run \
        --kwargs "{'employees': ['HR-EMP-00003','HR-EMP-00004'], 'dry_run': False}"
"""

import frappe
from frappe.utils import flt, getdate

LEAVE_TYPE = "Paid Time Off"
DEFAULT_CUTOFF = "2026-06-30"


def _target_allocation(employee, cutoff):
    """Submitted PTO allocation whose period contains the cutoff date."""
    return frappe.db.get_value(
        "Leave Allocation",
        {
            "employee": employee,
            "leave_type": LEAVE_TYPE,
            "from_date": ("<=", cutoff),
            "to_date": (">=", cutoff),
            "docstatus": 1,
        },
        "name",
    )


def _all_candidate_employees(cutoff):
    """Every employee with a submitted PTO allocation covering the cutoff date."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT employee
        FROM `tabLeave Allocation`
        WHERE leave_type = %(lt)s AND docstatus = 1
          AND from_date <= %(cut)s AND to_date >= %(cut)s
        """,
        {"lt": LEAVE_TYPE, "cut": cutoff},
        as_dict=True,
    )
    return [r.employee for r in rows]


def _process_one(employee, cutoff, dry_run):
    from gs_customizations.overrides.hrms.leave_application.leave_application import (
        get_leave_balance_on,
    )

    alloc = _target_allocation(employee, cutoff)
    if not alloc:
        return {"employee": employee, "status": "skip:no-allocation", "hours": 0.0, "entry": None}

    if frappe.db.exists(
        "Leave Ledger Entry",
        {"transaction_name": alloc, "is_expired": 1, "from_date": cutoff, "docstatus": 1},
    ):
        return {
            "employee": employee,
            "status": "skip:already-expired",
            "allocation": alloc,
            "hours": 0.0,
            "entry": None,
        }

    x = flt(
        get_leave_balance_on(
            employee, LEAVE_TYPE, cutoff, consider_all_leaves_in_the_allocation_period=False
        )
    )
    if x == 0:
        return {
            "employee": employee,
            "status": "skip:zero-balance",
            "allocation": alloc,
            "hours": 0.0,
            "entry": None,
        }

    entry = None
    if not dry_run:
        doc = frappe.get_doc(
            dict(
                doctype="Leave Ledger Entry",
                employee=employee,
                employee_name=frappe.db.get_value("Employee", employee, "employee_name"),
                leave_type=LEAVE_TYPE,
                transaction_type="Leave Allocation",
                transaction_name=alloc,
                from_date=cutoff,
                to_date=cutoff,
                custom_time_leaves=-x,
                is_carry_forward=0,
                is_expired=1,
                is_lwp=0,
            )
        )
        doc.flags.ignore_permissions = 1
        doc.submit()
        entry = doc.name

    return {
        "employee": employee,
        "status": "applied" if not dry_run else "would-apply",
        "allocation": alloc,
        "hours": round(x / 3600, 2),
        "entry": entry,
    }


def run(exclude=None, employees=None, cutoff=DEFAULT_CUTOFF, dry_run=True):
    """Expire pre-cutoff PTO balances.

    :param exclude: list of Employee IDs to skip (only used when `employees` is None).
    :param employees: explicit list of Employee IDs to process; if omitted, every
        employee with a PTO allocation covering the cutoff is targeted.
    :param cutoff: balance is expired as of this date (default 2026-06-30).
    :param dry_run: when True (default) nothing is written — only a preview is returned.
    """
    cutoff = str(getdate(cutoff))
    exclude = set(exclude or [])

    if employees:
        targets = [e for e in employees if e not in exclude]
    else:
        targets = [e for e in _all_candidate_employees(cutoff) if e not in exclude]
    targets = sorted(set(targets))

    results = [_process_one(e, cutoff, dry_run) for e in targets]

    if not dry_run:
        frappe.db.commit()

    applied = [r for r in results if r["status"] in ("applied", "would-apply")]
    total_hours = round(sum(r["hours"] for r in applied), 2)
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    print(f"\n=== PTO reset {'(DRY RUN)' if dry_run else '(APPLIED)'} | cutoff {cutoff} ===")
    print(f"targets: {len(targets)} | excluded: {sorted(exclude)}")
    print(f"status breakdown: {summary}")
    print(f"total hours {'to expire' if dry_run else 'expired'}: {total_hours}")
    print(f"{'EMPLOYEE':<16}{'STATUS':<22}{'HOURS':>8}  ENTRY")
    for r in results:
        print(f"{r['employee']:<16}{r['status']:<22}{r['hours']:>8}  {r.get('entry') or ''}")

    return {"cutoff": cutoff, "dry_run": dry_run, "summary": summary,
            "total_hours": total_hours, "results": results}
