import frappe
from frappe import _
from frappe.utils import cint, getdate, get_first_day, get_last_day
from gs_customizations.validate.permissions import is_manager

# Task columns the date range may be applied to. The chosen value is
# interpolated into the WHERE clause, so it is resolved through this whitelist -
# a filter value is client-supplied and must never reach SQL directly.
DATE_FIELDS = ("completed_on", "exp_start_date")
DEFAULT_DATE_FIELD = "completed_on"


def get_date_field(filters):
    """Which Task date column the Month / Date Range filter applies to."""
    field = filters.get("date_field") or DEFAULT_DATE_FIELD

    if field not in DATE_FIELDS:
        frappe.throw(_("Invalid date field: {0}").format(field))

    return field


def execute(filters=None):
    """
    Main execution function for the GS Task Sheet Report
    """
    filters = frappe._dict(filters or {})
    
    # Validate filters
    if not filters.filter_based_on:
        frappe.throw(_("Please select Filter Based On"))
    
    # Month/Year always have a sensible value, so there is nothing to nag about.
    # Falling back here rather than throwing also stops an empty year from turning
    # into an unbounded query - get_conditions() skips the date clause entirely
    # when either is missing.
    if filters.filter_based_on == "Month":
        today = getdate()
        filters.month = cint(filters.month) or today.month
        filters.year = cint(filters.year) or today.year
    
    if filters.filter_based_on == "Date Range":
        if not (filters.start_date and filters.end_date):
            frappe.throw(_("Please set the date range."))
        if getdate(filters.start_date) > getdate(filters.end_date):
            frappe.throw(_("Start date cannot be greater than end date."))
    
    columns = get_columns()
    data = get_data(filters)
    
    if not data:
        frappe.msgprint(_("No task records found for this criteria."), alert=True, indicator="orange")
        return columns, [], None, None
    
    return columns, data, None, None


def get_columns():
    """Report columns.

    Deliberately one fixed list. The column order used to change when
    Group By Employee was ticked - the two completed-by columns jumped to the
    front - which made the layout inconsistent between the two modes.
    """
    return [
        {
            "fieldname": "completed_by",
            "label": _("Completed By"),
            "fieldtype": "Link",
            "options": "User",
            "width": 150
        },
        {
            "fieldname": "custom_completed_by_employee",
            "label": _("Completed By Employee"),
            "fieldtype": "Data",
            "width": 140
        },
        {
            "fieldname": "custom_assign_to_employee",
            "label": _("Assigned To"),
            "fieldtype": "Data",
            "width": 150
        },
        {
            "fieldname": "name",
            "label": _("ID"),
            "fieldtype": "Link",
            "options": "Task",
            "width": 160
        },
        {
            "fieldname": "subject",
            "label": _("Subject"),
            "fieldtype": "Data",
            "width": 220
        },
        {
            "fieldname": "custom_project_name",
            "label": _("Project Name"),
            "fieldtype": "Data",
            "width": 160
        },
        {
            "fieldname": "custom_issue_name",
            "label": _("Issue Name"),
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "status",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 140
        },
        {
            "fieldname": "type",
            "label": _("Type"),
            "fieldtype": "Link",
            "options": "Task Type",
            "width": 140
        },
        {
            "fieldname": "is_group",
            "label": _("Is Group"),
            "fieldtype": "Check",
            "width": 80
        },
        {
            "fieldname": "exp_start_date",
            "label": _("Expected Start Date"),
            "fieldtype": "Date",
            "width": 130
        },
        {
            "fieldname": "completed_on",
            "label": _("Completed On"),
            "fieldtype": "Date",
            "width": 120
        },
        {
            "fieldname": "expected_time",
            "label": _("Expected Time (In Hours)"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "actual_time",
            "label": _("Actual Time In Timesheet"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "expected_time_days",
            "label": _("Expected Time (In Days)"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "actual_time_days",
            "label": _("Actual Time In Timesheet (Days)"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "utilization",
            "label": _("% Utilization"),
            "fieldtype": "Float",
            "width": 120
        },
        {
            "fieldname": "custom_reviewer",
            "label": _("Reviewer"),
            "fieldtype": "Data",
            "width": 160
        }
    ]


def get_data(filters):
    """Fetch and return report data"""
    conditions = get_conditions(filters)
    
    # Grouping uses itertools.groupby, which only works on input already sorted
    # by the group key - so the assignee has to lead the ORDER BY. Kept the same
    # in both modes so the flat and grouped views agree on row order.
    order_by = "custom_assign_to_employee, name DESC"
    
    data = frappe.db.sql(f"""
        SELECT 
            name,
            subject,
            project,
            custom_project_name,
            issue,
            custom_issue_name,
            status,
            type,
            is_group,
            exp_start_date,
            custom_assign_to_employee,
            completed_by,
            custom_completed_by_employee,
            completed_on,
            expected_time,
            actual_time,
            custom_reviewer
        FROM `tabTask`
        WHERE 1=1
        {conditions}
        ORDER BY {order_by}
    """, filters, as_dict=1)
    
    # Calculate utilization for each row
    for row in data:
        row["expected_time_days"] = (row.get("expected_time") or 0) / 8
        row["actual_time_days"] = (row.get("actual_time") or 0) / 8

        row["utilization"] = calculate_utilization(row.get("actual_time"), row.get("expected_time"))

    # Process data for grouping if needed
    if filters.get("group_by_assignee") and data:
        data = process_grouped_data(data)
    
    return data


def get_conditions(filters):
    """Build SQL conditions based on filters"""
    conditions = ""

    # Safe to interpolate: get_date_field() resolves through a whitelist.
    date_field = get_date_field(filters)

    # Date filtering - same approach as HRMS
    if filters.filter_based_on == "Month":
        if filters.month and filters.year:
            # Convert to integers using cint()
            month = cint(filters.month)
            year = cint(filters.year)
            # Get first and last day of the selected month
            first_day = get_first_day(f"{year}-{month:02d}-01")
            last_day = get_last_day(f"{year}-{month:02d}-01")
            conditions += f" AND {date_field} BETWEEN '{first_day}' AND '{last_day}'"
    
    elif filters.filter_based_on == "Date Range":
        if filters.start_date:
            conditions += f" AND {date_field} >= %(start_date)s"
        if filters.end_date:
            conditions += f" AND {date_field} <= %(end_date)s"
    
    # Status filter. "All" is written as an exclusion rather than a list of every
    # status: an inclusion list silently drops any status added to Task later,
    # which is the one failure mode nobody notices.
    if filters.get("status"):
        if filters.status in ("Completed", "Closed"):
            conditions += " AND status = %(status)s"
        elif filters.status == "Both":
            conditions += " AND status IN ('Completed', 'Closed')"
        elif filters.status == "All":
            conditions += " AND status NOT IN ('Cancelled', 'Template')"

    # Only tasks that carry an assignee. Needed for the "All" status option:
    # completed_by / custom_completed_by_employee are only populated once a task
    # reaches Completed or Closed, so they cannot identify the employee on an
    # open task - custom_assign_to_employee can.
    conditions += " AND IFNULL(custom_assign_to_employee, '') != ''"

    # Non-managers can only see their own records. Raw SQL bypasses
    # permission_query_conditions, so the lock must be re-applied here.
    # completed_by holds the Employee ID (set in task.py auto_set_fields_on_todo),
    # so match on the session user's Employee; keep the user email as a
    # fallback for rows where core ERPNext stored the User instead.
    #
    # The assignee arm is required by the "All" status option: completed_by is
    # only filled once a task reaches Completed/Closed, so on its own it hides
    # every open task a non-manager owns - they would see an empty report.
    # custom_assign_to_id holds the User email, not the Employee ID.
    # No widening of access: task_permissions.task_query_conditions already
    # scopes Task visibility to the user's own assignments.
    if not is_manager():
        own_ids = [frappe.session.user]
        employee = frappe.db.get_value(
            "Employee", {"user_id": frappe.session.user}, "name"
        )
        if employee:
            own_ids.append(employee)
        filters.own_ids = own_ids
        filters.own_user = frappe.session.user
        conditions += (
            " AND (completed_by IN %(own_ids)s"
            " OR custom_assign_to_id = %(own_user)s)"
        )

    return conditions


def calculate_utilization(actual_time, expected_time):
    """Calculate utilization percentage"""
    if not expected_time or expected_time == 0:
        return 0
    return (actual_time or 0) / expected_time * 100

def process_grouped_data(data):
    """
    Process data to add tree structure for grouping
    Similar to how HRMS Monthly Attendance Sheet works
    """
    from itertools import groupby
    
    if not data:
        return data
    
    result = []
    
    # Group by the assignee. Was custom_completed_by_employee, which is blank for
    # anything not yet Completed/Closed and so collapsed most rows into one group
    # as soon as the All status filter was used.
    group_key = lambda d: d.get("custom_assign_to_employee") or _("No Assignee")
    
    for assignee_name, rows in groupby(data, key=group_key):
        rows_list = list(rows)

        # Calculate totals for this employee
        total_expected = sum(row.get("expected_time") or 0 for row in rows_list)
        total_actual = sum(row.get("actual_time") or 0 for row in rows_list)
        total_expected_days = total_expected / 8
        total_actual_days = total_actual / 8
        total_utilization = calculate_utilization(total_actual, total_expected)

        # Add parent row (summary)
        parent_row = {
            "custom_assign_to_employee": assignee_name,
            "completed_by": "",
            "custom_completed_by_employee": "",
            "name": "",
            "subject": "",
            "project": "",
            "issue": "",
            "status": "",
            "type": "",
            "is_group": 0,
            "expected_time": total_expected,
            "actual_time": total_actual,
            "expected_time_days": total_expected_days,
            "actual_time_days": total_actual_days,
            "utilization": total_utilization,
            "completed_on": "",
            "exp_start_date": "",
            "indent": 0,
        }
        result.append(parent_row)
        
        # Add child rows
        for row in rows_list:
            row["indent"] = 1
            result.append(row)
    
    return result