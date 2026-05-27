import frappe
from frappe import _
from frappe.utils import getdate, nowdate, flt
from collections import defaultdict
from datetime import timedelta

FREE_FIELDS = ["project", "project_name", "task", "custom_task_name", "custom_task_type"]


def clear_free_activity_fields(doc, method):
    for row in doc.time_logs:
        if row.activity_type in ["Free", "Documents"]:
            for field in FREE_FIELDS:
                row.set(field, None)


def update_completed_from_task(doc, method):
    for row in doc.time_logs:
        if row.task:
            task = frappe.db.get_value("Task", row.task, ["status", "completed_on"], as_dict=True)
            if (
                task
                and task.status in ("Completed", "Closed")
                and task.completed_on
                and row.from_time
                and getdate(row.from_time) >= getdate(task.completed_on)
            ):
                row.completed = 1
            else:
                row.completed = 0
        else:
            row.completed = 0


def validate_timesheet_rules(doc, method):
    """Enforce custom timesheet rules on validate:
    1) Daily hours per date <= company working hours
    2) Daily hours must subtract approved leave; full-day leave blocks entry
    3) from_time date must be within ±4 calendar days of today
    4) Working hours must not exceed into the next day
    """
    if not doc.employee or not doc.company:
        return

    from gs_customizations.utils.timesheet_checkin import get_leave_hours_for_date

    company_hours = _get_company_working_hours_float(doc.company)
    if not company_hours:
        return

    today = getdate(nowdate())
    date_hours = defaultdict(float)

    for row in doc.time_logs:
        if not row.from_time:
            continue

        row_date = getdate(row.from_time)

        if abs((row_date - today).days) > 4:
            frappe.throw(
                _("Row {0}: Date {1} is more than 4 days from today. "
                  "You can only log time within ±4 calendar days of today.").format(
                    row.idx, row_date.strftime("%Y-%m-%d")
                )
            )

        if row.to_time and getdate(row.to_time) != row_date:
            frappe.throw(
                _("Row {0}: Working hours exceed into the next day. "
                  "From time {1} plus {2}h goes past midnight. "
                  "Please reduce the hours or adjust the start time.").format(
                    row.idx,
                    frappe.format_value(row.from_time, {"fieldtype": "Datetime"}),
                    flt(row.hours, 2),
                )
            )

        date_hours[str(row_date)] += flt(row.hours)

    for date_str, total_hours in date_hours.items():
        leave_hours = get_leave_hours_for_date(doc.employee, date_str, company_hours)

        if leave_hours >= company_hours:
            frappe.throw(
                _("You have a full-day leave on {0}. "
                  "You cannot log timesheet hours on this date.").format(date_str)
            )

        max_hours = company_hours - leave_hours
        if total_hours > max_hours + 0.01:
            if leave_hours > 0:
                frappe.throw(
                    _("Total hours on {0} is {1}h, but the maximum allowed is {2}h "
                      "({3}h working hours minus {4}h leave).").format(
                        date_str,
                        round(total_hours, 2),
                        round(max_hours, 2),
                        round(company_hours, 2),
                        round(leave_hours, 2),
                    )
                )
            else:
                frappe.throw(
                    _("Total hours on {0} is {1}h, which exceeds the maximum "
                      "working hours of {2}h.").format(
                        date_str,
                        round(total_hours, 2),
                        round(company_hours, 2),
                    )
                )


def _get_company_working_hours_float(company):
    if not company:
        return 0
    seconds = frappe.db.get_value("Company", company, "custom_total_working_hours")
    if not seconds:
        return 0
    return flt(seconds) / 3600.0


@frappe.whitelist()
def get_timesheet_validation_context(employee, company):
    """Return validation context for client-side timesheet rules."""
    from gs_customizations.utils.timesheet_checkin import get_leave_hours_for_date

    company_hours = _get_company_working_hours_float(company)

    start_working_hour = frappe.db.get_value("Company", company, "custom_start_working_hour")
    if isinstance(start_working_hour, timedelta):
        total_sec = int(start_working_hour.total_seconds())
        h, rem = divmod(total_sec, 3600)
        m, s = divmod(rem, 60)
        start_working_hour = f"{h:02d}:{m:02d}:{s:02d}"
    elif start_working_hour:
        start_working_hour = str(start_working_hour)
    else:
        start_working_hour = "09:00:00"

    today = getdate(nowdate())
    leave_data = {}
    for delta in range(-4, 5):
        date = today + timedelta(days=delta)
        date_str = str(date)
        leave_hours = get_leave_hours_for_date(employee, date_str, company_hours)
        leave_data[date_str] = round(leave_hours, 2)

    return {
        "company_working_hours": round(company_hours, 2),
        "start_working_hour": start_working_hour,
        "leave_data": leave_data,
    }
