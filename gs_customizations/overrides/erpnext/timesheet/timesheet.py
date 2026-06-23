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
    2) Daily hours must subtract approved leave (from Attendance); full-day
       leave blocks entry
    3) No hours on a non-working day: Holiday List dates and Absent-attendance
       dates are blocked entirely
    4) from_time date must be within ±6 days of today — gated on the logged-in
       user's check-in flag (is_checkin_enabled), only for new rows or rows
       where the date changed
    5) Working hours must not exceed into the next day
    """
    if not doc.employee or not doc.company:
        return

    from gs_customizations.utils.timesheet_checkin import (
        get_leave_hours_for_date,
        get_holiday_dates,
        get_absent_dates,
        is_checkin_enabled,
    )

    company_hours = _get_company_working_hours_float(doc.company)
    if not company_hours:
        return

    today = getdate(nowdate())

    # The ±6 day window is gated on the *logged-in user*, not the timesheet's
    # employee: only a user who has check-in enabled is date-restricted. A
    # manager (or any user without the flag) editing a sheet is unrestricted.
    checkin_enabled = is_checkin_enabled(frappe.session.user)

    # Fetch the dates already persisted in DB for each row of this timesheet.
    # Keyed by child-row name so we can detect new rows (not in DB yet) vs
    # rows whose date was merely edited.  Bypasses get_doc_before_save() which
    # is unreliable when the pre-save cache wasn't populated (API calls, new
    # tabs, certain submit paths).
    saved_row_dates = {}
    if checkin_enabled and not doc.is_new():
        rows_in_db = frappe.db.sql(
            """
            SELECT name, DATE(from_time) AS dt
            FROM `tabTimesheet Detail`
            WHERE parent = %(parent)s
            """,
            {"parent": doc.name},
            as_dict=True,
        )
        for r in rows_in_db:
            if r.dt:
                saved_row_dates[r.name] = getdate(r.dt)

    date_hours = defaultdict(float)

    for row in doc.time_logs:
        if not row.from_time:
            continue

        row_date = getdate(row.from_time)

        if checkin_enabled:
            saved_date = saved_row_dates.get(row.name)
            is_new_or_date_changed = saved_date is None or saved_date != row_date
            if is_new_or_date_changed and abs((today - row_date).days) > 6:
                frappe.throw(
                    _("Row {0}: Date {1} is outside the allowed ±6 day window. "
                      "You can only log time within 6 days of today.").format(
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

    # Non-working days (holidays + Absent attendance) over the span of logged
    # dates. Both are blocked from time entry.
    holiday_dates = set()
    absent_dates = set()
    if date_hours:
        all_dates = sorted(date_hours.keys())
        holiday_dates = get_holiday_dates(doc.employee, all_dates[0], all_dates[-1])
        absent_dates = get_absent_dates(doc.employee, all_dates[0], all_dates[-1])

    for date_str, total_hours in date_hours.items():
        if date_str in holiday_dates:
            frappe.throw(
                _("{0} is a holiday. You cannot log timesheet hours on this date.").format(date_str)
            )

        if date_str in absent_dates:
            frappe.throw(
                _("{0} is marked as Absent in Attendance. "
                  "You cannot log timesheet hours on this date.").format(date_str)
            )

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
    from gs_customizations.utils.timesheet_checkin import (
        get_attendance_map,
        leave_hours_from_attendance,
        get_holiday_dates,
        is_checkin_enabled,
    )

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

    # Date restriction follows the *logged-in user*, not the timesheet's
    # employee — only a check-in-enabled user is date-limited.
    checkin_enabled = is_checkin_enabled(frappe.session.user)

    # Window covers current + previous week fully (prev Monday can be up to
    # 13 days ago) plus a one-week look-ahead for the ±6 day date check.
    today = getdate(nowdate())
    window_start = today - timedelta(days=14)
    window_end = today + timedelta(days=7)

    holiday_dates = sorted(get_holiday_dates(employee, window_start, window_end))

    # One Attendance read for the whole window; derive leave hours per day and
    # the Absent-day set from it (instead of a query per day).
    attendance_map = get_attendance_map(employee, window_start, window_end)
    absent_dates = sorted(
        d for d, att in attendance_map.items() if att.status == "Absent"
    )

    leave_data = {}
    current = window_start
    while current <= window_end:
        date_str = str(current)
        att = attendance_map.get(date_str)
        leave_data[date_str] = round(
            leave_hours_from_attendance(
                att.status, att.custom_total_leave_time, company_hours
            ) if att else 0.0,
            2,
        )
        current += timedelta(days=1)

    # Hours already logged in submitted timesheets for this employee.
    # Wrapped in try/except so a SQL failure here never blocks leave_data
    # from reaching the client.
    submitted_hours = {}
    try:
        submitted_rows = frappe.db.sql(
            """
            SELECT DATE(td.from_time) AS log_date, SUM(td.hours) AS total
            FROM `tabTimesheet Detail` td
            INNER JOIN `tabTimesheet` ts ON td.parent = ts.name
            WHERE ts.employee = %(employee)s
              AND ts.docstatus = 1
              AND DATE(td.from_time) >= %(start)s
              AND DATE(td.from_time) <= %(end)s
            GROUP BY DATE(td.from_time)
            """,
            {"employee": employee, "start": str(window_start), "end": str(window_end)},
            as_dict=True,
        )
        for row in submitted_rows:
            submitted_hours[str(row.log_date)] = round(flt(row.total), 2)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "gs_customizations: submitted_hours fetch failed")

    return {
        "company_working_hours": round(company_hours, 2),
        "start_working_hour": start_working_hour,
        "leave_data": leave_data,
        "submitted_hours": submitted_hours,
        "holiday_dates": holiday_dates,
        "absent_dates": absent_dates,
        "checkin_enabled": checkin_enabled,
    }
