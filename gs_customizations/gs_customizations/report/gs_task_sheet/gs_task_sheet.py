import frappe
from frappe import _
from frappe.utils import cint, getdate, get_first_day, get_last_day

def execute(filters=None):
    """
    Main execution function for the GS Task Sheet Report
    """
    filters = frappe._dict(filters or {})
    
    # Validate filters
    if not filters.filter_based_on:
        frappe.throw(_("Please select Filter Based On"))
    
    if filters.filter_based_on == "Month" and not (filters.month and filters.year):
        frappe.throw(_("Please select month and year."))
    
    if filters.filter_based_on == "Date Range":
        if not (filters.start_date and filters.end_date):
            frappe.throw(_("Please set the date range."))
        if getdate(filters.start_date) > getdate(filters.end_date):
            frappe.throw(_("Start date cannot be greater than end date."))
    
    columns = get_columns(filters)
    data = get_data(filters)
    
    if not data:
        frappe.msgprint(_("No task records found for this criteria."), alert=True, indicator="orange")
        return columns, [], None, None
    
    return columns, data, None, None


def get_columns(filters):
    """Define report columns based on filters"""
    columns = []
    
    # Add grouping column if group_by_employee is selected
    if filters.get("group_by_employee"):
        columns.append(
            {
                "fieldname": "completed_by",
                "label": _("Completed By"),
                "fieldtype": "Data",
                "width": 150
            }
        ),
        columns.append(
            {
                "fieldname": "custom_completed_by_employee",
                "label": _("Completed By Employee"),
                "fieldtype": "Data",
                "width": 140
            }
        )
    
    # Add standard columns
    columns.extend([
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
        }
    ])

    # Don't duplicate the employee column if we're grouping
    if not filters.get("group_by_employee"):
        columns.append(
            {
                "fieldname": "completed_by",
                "label": _("Completed By"),
                "fieldtype": "Link",
                "options": "User",
                "width": 150
            }
        ),
        columns.append(
            {
                "fieldname": "custom_completed_by_employee",
                "label": _("Completed By Employee"),
                "fieldtype": "Data",
                "width": 140
            }
        )

    
    # Add time columns
    columns.extend([
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
    ])
    
    return columns


def get_data(filters):
    """Fetch and return report data"""
    conditions = get_conditions(filters)
    
    # Determine order by clause
    order_by = "completed_by DESC, name DESC"
    if filters.get("group_by_employee"):
        order_by = "completed_by, name DESC"
    
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
    if filters.get("group_by_employee") and data:
        data = process_grouped_data(data)
    
    return data


def get_conditions(filters):
    """Build SQL conditions based on filters"""
    conditions = ""
    
    # Date filtering - same approach as HRMS
    if filters.filter_based_on == "Month":
        if filters.month and filters.year:
            # Convert to integers using cint()
            month = cint(filters.month)
            year = cint(filters.year)
            # Get first and last day of the selected month
            first_day = get_first_day(f"{year}-{month:02d}-01")
            last_day = get_last_day(f"{year}-{month:02d}-01")
            conditions += f" AND completed_on BETWEEN '{first_day}' AND '{last_day}'"
    
    elif filters.filter_based_on == "Date Range":
        if filters.start_date:
            conditions += " AND completed_on >= %(start_date)s"
        if filters.end_date:
            conditions += " AND completed_on <= %(end_date)s"
    
    # Project filter
    if filters.get("project"):
        conditions += " AND project = %(project)s"
    
    # Status filter - handle "Closed" vs "Completed"
    if filters.get("status"):
        if filters.status == "Completed":
            conditions += " AND status = 'Completed'"
        elif filters.status == "Closed":
            conditions += " AND status = 'Closed'"
        elif filters.status == "Both":
            conditions += "And status IN ('Completed', 'Closed')"
    
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
    
    # Group by employee
    group_key = lambda d: d.get("custom_completed_by_employee") or _("No Employee")
    
    for employee_name, rows in groupby(data, key=group_key):
        rows_list = list(rows)

        # Calculate totals for this employee
        total_expected = sum(row.get("expected_time") or 0 for row in rows_list)
        total_actual = sum(row.get("actual_time") or 0 for row in rows_list)
        total_expected_days = total_expected / 8
        total_actual_days = total_actual / 8
        total_utilization = calculate_utilization(total_actual, total_expected)

        completed_by = rows_list[0].get("completed_by") if rows_list else ""
        
        # Add parent row (summary)
        parent_row = {
            "completed_by": completed_by,
            "custom_completed_by_employee": employee_name,
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
            "indent": 0,
        }
        result.append(parent_row)
        
        # Add child rows
        for row in rows_list:
            row["indent"] = 1
            result.append(row)
    
    return result