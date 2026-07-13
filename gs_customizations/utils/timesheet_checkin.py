"""
Daily Timesheet Check-in Enforcement
=====================================

Core logic for computing whether an employee must be redirected to the
Timesheet Check-in page to fill missing timesheets.

Opt-in per employee via Employee.custom_enable_timesheet_checkin (default 0).
Managers and users without an Employee record are always exempt.

See plan: /home/uriel-server-01/.claude/plans/cryptic-beaming-sketch.md
"""

import frappe
from frappe.utils import (
    getdate,
    nowdate,
    cstr,
    flt,
)
from datetime import timedelta


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def get_checkin_status(user=None, include_today=False):
    """Top-level function called from boot_session and the API endpoint.

    Returns a dict:
        {
            "enforce": bool,
            "missing_days": [...],
            "employee": str or None,
            "employee_name": str or None,
            "end_working_hour": "HH:MM:SS" or None,
            "include_today": bool,
        }
    """
    user = user or frappe.session.user
    result = {
        "enforce": False,
        "missing_days": [],
        "employee": None,
        "employee_name": None,
        "end_working_hour": None,
        "include_today": bool(include_today),
    }

    if not is_checkin_enabled(user):
        return result

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        ["name", "employee_name", "company", "date_of_joining"],
        as_dict=True,
    )
    if not employee:
        return result

    result["employee"] = employee.name
    result["employee_name"] = employee.employee_name

    # End-of-day time from the company
    if employee.company:
        end_hour = frappe.db.get_value(
            "Company", employee.company, "custom_end_working_hour"
        )
        if end_hour:
            # Frappe returns Time fields as timedelta
            if isinstance(end_hour, timedelta):
                total_sec = int(end_hour.total_seconds())
                h, rem = divmod(total_sec, 3600)
                m, s = divmod(rem, 60)
                result["end_working_hour"] = f"{h:02d}:{m:02d}:{s:02d}"
            else:
                result["end_working_hour"] = str(end_hour)

    missing = get_missing_timesheet_days(employee, include_today=include_today)
    result["missing_days"] = missing
    result["enforce"] = bool(missing)

    return result


def is_checkin_enabled(user):
    """Return True only if the feature is explicitly enabled for this user.

    The enforcement pipeline short-circuits when this returns False, meaning
    the user experiences zero impact.
    """
    if not user or user == "Administrator" or user == "Guest":
        return False

    # Managers are always exempt
    manager_roles = frappe.conf.get("manager_roles") or []
    if manager_roles:
        user_roles = set(frappe.get_roles(user))
        if user_roles.intersection(set(manager_roles)):
            return False

    # Must have an active Employee with the opt-in flag set
    enabled = frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        "custom_enable_timesheet_checkin",
    )
    return bool(enabled)


# ---------------------------------------------------------------------------
# Missing-day computation
# ---------------------------------------------------------------------------

def get_missing_timesheet_days(employee, include_today=False):
    """Compute the list of weekdays (Mon-Fri) in the current week
    that are missing or have insufficient timesheet hours.

    `employee` may be a dict (with name/company/date_of_joining) or an
    employee name (str) — in which case we fetch the record.
    """
    if isinstance(employee, str):
        employee = frappe.db.get_value(
            "Employee",
            employee,
            ["name", "company", "date_of_joining"],
            as_dict=True,
        )
        if not employee:
            return []

    today = getdate(nowdate())
    monday_this_week = today - timedelta(days=today.weekday())
    start_date = monday_this_week
    end_date = today if include_today else today - timedelta(days=1)

    if end_date < start_date:
        return []

    # Company working hours (in seconds -> hours)
    company_working_hours = _get_company_working_hours(employee.company)
    if not company_working_hours:
        return []

    # Non-working days in the window: holidays + Absent attendance.
    holiday_dates = get_holiday_dates(employee.name, start_date, end_date)
    absent_dates = get_absent_dates(employee.name, start_date, end_date)

    date_of_joining = getdate(employee.date_of_joining) if employee.get("date_of_joining") else None

    missing = []
    current = start_date
    while current <= end_date:
        current_str = cstr(current)

        # Skip weekends (Saturday=5, Sunday=6)
        if current.weekday() >= 5:
            current = current + timedelta(days=1)
            continue

        # Skip if before date_of_joining
        if date_of_joining and current < date_of_joining:
            current = current + timedelta(days=1)
            continue

        # Skip if holiday or marked Absent (non-working days)
        if current_str in holiday_dates or current_str in absent_dates:
            current = current + timedelta(days=1)
            continue

        leave_hours = get_leave_hours_for_date(
            employee.name, current_str, company_working_hours
        )
        required_hours = company_working_hours - leave_hours
        if required_hours <= 0:
            # Fully on leave
            current = current + timedelta(days=1)
            continue

        logged_hours = get_logged_hours_for_date(employee.name, current_str)
        if logged_hours + 0.01 < required_hours:  # epsilon
            missing.append({
                "date": current_str,
                "day_name": current.strftime("%A"),
                "required_hours": round(required_hours, 2),
                "logged_hours": round(logged_hours, 2),
                "shortfall": round(required_hours - logged_hours, 2),
                "leave_hours": round(leave_hours, 2),
                "existing_timesheet": find_existing_timesheet(
                    employee.name, current_str
                ),
            })

        current = current + timedelta(days=1)

    return missing


def _get_company_working_hours(company):
    """Return company working hours in float hours, or 0 if not set."""
    if not company:
        return 0
    seconds = frappe.db.get_value("Company", company, "custom_total_working_hours")
    if not seconds:
        return 0
    return flt(seconds) / 3600.0


def leave_hours_from_attendance(status, custom_total_leave_time, company_working_hours):
    """Map an Attendance status to leave hours for the day (see CustomAttendance):
      - "On Leave"    -> full company working hours
      - "Hours Leave" -> custom_total_leave_time (seconds) / 3600
      - "Half Day"    -> half of company working hours (legacy; half-day is
                         being phased out in favour of Hours Leave)
      - anything else / no record -> 0
    """
    if status == "On Leave":
        return company_working_hours
    if status == "Hours Leave":
        return min(flt(custom_total_leave_time) / 3600.0, company_working_hours)
    if status == "Half Day":
        return company_working_hours / 2.0
    return 0.0


def get_attendance_map(employee, start_date, end_date):
    """Return {date_str: frappe._dict(status, custom_total_leave_time)} for the
    employee's submitted Attendance within [start_date, end_date].

    Lets callers that scan a whole window read Attendance once instead of
    per-day."""
    rows = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "docstatus": 1,
            "attendance_date": ["between", [cstr(start_date), cstr(end_date)]],
        },
        fields=["attendance_date", "status", "custom_total_leave_time"],
    )
    return {cstr(r.attendance_date): r for r in rows}


def get_leave_hours_for_date(employee, date, company_working_hours=None):
    """Return approved leave hours for this employee on this date.

    Sourced from the **Attendance** record, not Leave Application: every
    approved Leave Application creates/updates the matching Attendance (see
    CustomLeaveApplication.update_attendance), so Attendance is the single
    source of truth and avoids re-deriving leave from the application range.
    """
    if company_working_hours is None:
        company = frappe.db.get_value("Employee", employee, "company")
        company_working_hours = _get_company_working_hours(company)

    attendance = frappe.db.get_value(
        "Attendance",
        {"employee": employee, "attendance_date": date, "docstatus": 1},
        ["status", "custom_total_leave_time"],
        as_dict=True,
    )
    if not attendance:
        return 0.0

    return leave_hours_from_attendance(
        attendance.status, attendance.custom_total_leave_time, company_working_hours
    )


def get_holiday_dates(employee, start_date, end_date):
    """Return a set of holiday date strings for the employee's Holiday List
    within [start_date, end_date]. Returns empty set on any failure so callers
    degrade gracefully."""
    try:
        from hrms.hr.utils import get_holiday_dates_for_employee
        return set(
            get_holiday_dates_for_employee(employee, cstr(start_date), cstr(end_date))
        )
    except Exception:
        return set()


def get_absent_dates(employee, start_date, end_date):
    """Return a set of date strings where the employee has a submitted
    Attendance with status 'Absent' within [start_date, end_date].

    An Absent day is a non-working day for timesheet purposes — treated like a
    holiday: hidden in the daily summary and blocked from time entry."""
    rows = frappe.get_all(
        "Attendance",
        filters={
            "employee": employee,
            "docstatus": 1,
            "status": "Absent",
            "attendance_date": ["between", [cstr(start_date), cstr(end_date)]],
        },
        pluck="attendance_date",
    )
    return {cstr(d) for d in rows}


def get_logged_hours_for_date(employee, date):
    """Sum Timesheet Detail hours for this employee where DATE(from_time) = date
    and the parent Timesheet is Draft or Submitted (not Cancelled).
    """
    rows = frappe.db.sql(
        """
        SELECT SUM(td.hours) AS total
        FROM `tabTimesheet Detail` td
        INNER JOIN `tabTimesheet` ts ON td.parent = ts.name
        WHERE ts.employee = %(employee)s
          AND ts.docstatus IN (0, 1)
          AND DATE(td.from_time) = %(date)s
        """,
        {"employee": employee, "date": date},
        as_dict=True,
    )
    if rows and rows[0].total:
        return flt(rows[0].total)
    return 0.0


def find_existing_timesheet(employee, date):
    """Return the name of an existing Draft Timesheet for this employee
    within the same week (Mon–Sun) as the target date.

    Artists use one weekly Timesheet per week with multiple time_logs across
    days, so we want to deep-link to the existing weekly draft whenever one
    exists — regardless of which specific days already have time_logs.
    """
    target = getdate(date)
    monday = target - timedelta(days=target.weekday())
    sunday = monday + timedelta(days=6)

    # 1) Any draft whose start_date (earliest logged day) falls within this
    #    week. Catches drafts already seeded with at least one time_log in
    #    the current week.
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabTimesheet`
        WHERE employee = %(employee)s
          AND docstatus = 0
          AND start_date >= %(monday)s
          AND start_date <= %(sunday)s
        ORDER BY modified DESC
        LIMIT 1
        """,
        {"employee": employee, "monday": monday, "sunday": sunday},
        as_dict=True,
    )
    if rows:
        return rows[0].name

    # 2) Fallback: any draft whose date range overlaps this week (in case
    #    start_date is outside the week but time_logs cross into it).
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabTimesheet`
        WHERE employee = %(employee)s
          AND docstatus = 0
          AND start_date <= %(sunday)s
          AND (end_date >= %(monday)s OR end_date IS NULL)
        ORDER BY modified DESC
        LIMIT 1
        """,
        {"employee": employee, "monday": monday, "sunday": sunday},
        as_dict=True,
    )
    if rows:
        return rows[0].name

    return None
