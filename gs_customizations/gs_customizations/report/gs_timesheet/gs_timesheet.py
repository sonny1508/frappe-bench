import frappe
from frappe import _
from frappe.desk.reportview import build_match_conditions
from collections import defaultdict
from gs_customizations.gs_customizations.report.period import set_period_dates
from gs_customizations.validate.permissions import is_manager


def execute(filters=None):
	filters = frappe._dict(filters or {})
	set_period_dates(filters)

	columns = get_column()
	conditions = get_conditions(filters)
	data = get_data(conditions, filters)

	# Add summary rows if checkbox is checked
	if filters.get("summarize_by_activity"):
		data = add_summary_rows(data)

	return columns, data


def get_column():
	return [
		_("Timesheet") + ":Link/Timesheet:120",
		_("Employee") + "::140",
		_("Employee Name") + "::120",
		_("From Datetime") + "::140",
		_("To Datetime") + "::140",
		_("Hours") + "::70",
		_("Activity Type") + "::120",
		_("Project") + "::120",
		_("Task") + ":Link/Task:120",
		_("Task Name") + "::140",
		_("Completed") + "::80",
		_("Issue") + "::120",
		_("Reviewer") + "::140",
		# _("Status") + "::80",
	]


def get_data(conditions, filters):
	# Task Name is read live from `tabTask`.subject rather than the stored
	# custom_task_name snapshot: a submitted timesheet never saves again, so
	# its fetched copy freezes at submit time and goes stale if the task is
	# later renamed. custom_task_name is kept only as a fallback for rows
	# whose Task no longer exists.
	time_sheet = frappe.db.sql(
		"""
		select
		`tabTimesheet`.name, `tabTimesheet`.employee, `tabTimesheet`.employee_name,
		`tabTimesheet Detail`.from_time, `tabTimesheet Detail`.to_time, `tabTimesheet Detail`.hours,
		`tabTimesheet Detail`.activity_type, `tabProject`.project_name,
		`tabTimesheet Detail`.task,
		coalesce(`tabTask`.subject, `tabTimesheet Detail`.custom_task_name) as task_name,
		`tabTimesheet Detail`.completed,
		`tabIssue`.subject as issue_name,
		`tabTask`.custom_reviewer as reviewer_name
		from
			`tabTimesheet Detail`
			inner join `tabTimesheet` on `tabTimesheet Detail`.parent = `tabTimesheet`.name
			left join `tabProject` on `tabTimesheet Detail`.project = `tabProject`.name
			left join `tabTask` on `tabTimesheet Detail`.task = `tabTask`.name
			left join `tabIssue` on `tabTask`.issue = `tabIssue`.name
		where
			%s
		order by
			`tabTimesheet`.employee,
			`tabTimesheet Detail`.from_time
		"""
		% (conditions),
		filters,
		as_list=1,
	)

	# Convert completed field from 0/1 to False/True
	result = []
	for row in time_sheet:
		row = list(row)
		row[10] = "True" if row[10] else "False"
		if row[6] in ["Free", "Documents"]:
			row[11] = "Free"
		result.append(row)

	return result


def get_conditions(filters):
	conditions = (
		"`tabTimesheet`.docstatus = 1"
		" and `tabTimesheet Detail`.from_time >= timestamp(%(start_date)s, '00:00:00')"
		" and `tabTimesheet Detail`.to_time <= timestamp(%(end_date)s, '24:00:00')"
	)

	match_conditions = build_match_conditions("Timesheet")
	if match_conditions:
		conditions += " and %s" % match_conditions

	# Non-managers can only see their own timesheets. Raw SQL bypasses
	# permission_query_conditions, so the lock must be re-applied here.
	# Timesheet.employee holds the Employee ID; owner is kept as a
	# fallback for timesheets not linked to an Employee record.
	if not is_manager():
		filters["session_user"] = frappe.session.user
		own_condition = "`tabTimesheet`.owner = %(session_user)s"
		employee = frappe.db.get_value(
			"Employee", {"user_id": frappe.session.user}, "name"
		)
		if employee:
			filters["session_employee"] = employee
			own_condition = (
				"(`tabTimesheet`.employee = %(session_employee)s"
				" or `tabTimesheet`.owner = %(session_user)s)"
			)
		conditions += " and %s" % own_condition

	return conditions


def add_summary_rows(data):
	"""
	Add summary rows after each employee's detail rows.
	Summary rows show total hours grouped by activity type.
	"""
	if not data:
		return data

	result = []
	current_employee = None
	employee_name = None
	activity_hours = defaultdict(float)

	for row in data:
		# Row structure:
		# [timesheet, employee, employee_name, from_time, to_time, hours,
		#  activity_type, project_name, task, task_name, issue, status, complete]
		employee = row[1]
		emp_name = row[2]
		hours = row[5] or 0
		activity_type = row[6]

		if current_employee and current_employee != employee:
			result.extend(create_summary_rows(current_employee, employee_name, activity_hours))
			activity_hours = defaultdict(float)

		result.append(row)

		current_employee = employee
		employee_name = emp_name
		activity_hours[activity_type] += hours

	if current_employee:
		result.extend(create_summary_rows(current_employee, employee_name, activity_hours))

	return result


def create_summary_rows(employee, employee_name, activity_hours):
	"""
	Create summary rows for an employee, sorted by activity type (ascending).
	"""
	summary_rows = []

	sorted_activities = sorted(activity_hours.items(), key=lambda x: x[0] or "")

	for activity_type, total_hours in sorted_activities:
		summary_row = [
			"",  # Timesheet
			f"<strong>{employee}</strong>" if employee else "",
			f"<b>{employee_name}</b>" if employee_name else "",
			"",  # From Datetime
			"",  # To Datetime
			f"<b>{total_hours}</b>",
			f"<b>{activity_type}</b>" if activity_type else "",
			"",  # Project Name
			"",  # Task
			"",  # Task Name
			"",  # Completed
			"",  # Issue
			"",  # Reviewer
			# "",  # Status
		]
		summary_rows.append(summary_row)

	return summary_rows