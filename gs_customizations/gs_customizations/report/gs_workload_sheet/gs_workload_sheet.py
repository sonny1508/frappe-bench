"""GS Workload Sheet: who is carrying which tasks right now.

The people view of task assignments: one row per employee, expanding to the
tasks assigned to them. Unlike the other GS reports it has no period. It always
shows the current state, so a manager can see who has room for more work.

Assignments come from ToDo and are matched to the Employee through user_id.
Task.custom_assign_to_employee is only a display name, so it is not used here.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from gs_customizations.gs_customizations.report.gs_task_pool.gs_task_pool import get_pool_tasks
from gs_customizations.overrides.erpnext.task.overdue_priority import (
	FINISHED_STATUSES,
	is_past_deadline,
)
from gs_customizations.validate.permissions import is_manager

# The role tasks are assigned to. Employees holding it are listed even with no
# tasks - an artist with nothing on is exactly who a manager is looking for.
# Anyone else is listed only while they hold a task.
ASSIGNABLE_ROLE = "GS - Projects User"

# Tasks the artist has handed in: waiting on QA, approved, or with the client.
# Every other unfinished task counts as active - including QA Feedback and
# Client Feedback, which come back to the artist to work on, and any status
# added later.
SUBMITTED_STATUSES = ("QA Pending", "QA Reviewing", "QA Approved", "Delivered")


def execute(filters=None):
	if not is_manager():
		frappe.throw(_("Only managers can view this report."), frappe.PermissionError)

	filters = frappe._dict(filters or {})

	tasks_by_user = get_current_tasks()
	employees = get_employees(filters, list(tasks_by_user))

	# "Active Tasks Fewer Than": 1 keeps employees with no active task at all.
	active_below = cint(filters.get("active_below"))

	data = []
	for employee in employees:
		tasks = tasks_by_user.get(employee.user_id, [])
		employee_row = get_employee_row(employee, tasks)

		if active_below and employee_row["active_count"] >= active_below:
			continue

		data.append(employee_row)
		data.extend(tasks)

	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	"""One column set for both row types: the employee columns are blank on task
	rows and the task columns blank on employee rows.

	Labels follow the Task field each column comes from. Only the employee totals
	keep their column menu, because sorting is by employee (see SORT_COLUMNS in
	gs_workload_sheet.js). On any other column it would split the tasks from
	their employee.
	"""
	return [
		{
			"fieldname": "id",
			"label": _("ID"),
			"fieldtype": "Dynamic Link",
			"options": "row_doctype",
			"width": 160,
			"dropdown": False,
		},
		{"fieldname": "title", "label": _("Name"), "fieldtype": "Data", "width": 220, "dropdown": False},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 150,
			"dropdown": False,
		},
		{
			"fieldname": "grade",
			"label": _("Grade"),
			"fieldtype": "Link",
			"options": "Employee Grade",
			"width": 90,
			"dropdown": False,
		},
		{"fieldname": "active_count", "label": _("Active Tasks"), "fieldtype": "Int", "width": 100},
		{"fieldname": "submitted_count", "label": _("Submitted Tasks"), "fieldtype": "Int", "width": 120},
		{"fieldname": "overdue_count", "label": _("Overdue Tasks"), "fieldtype": "Int", "width": 110},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Data", "width": 160, "dropdown": False},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120, "dropdown": False},
		{
			"fieldname": "exp_start_date",
			"label": _("Expected Start Date"),
			"fieldtype": "Date",
			"width": 140,
			"dropdown": False,
		},
		{
			"fieldname": "exp_end_date",
			"label": _("Expected End Date"),
			"fieldtype": "Date",
			"width": 140,
			"dropdown": False,
		},
		{
			"fieldname": "expected_time",
			"label": _("Expected Time (In Hours)"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 170,
		},
		{
			"fieldname": "utilization",
			"label": _("Utilization"),
			"fieldtype": "Percent",
			"precision": 1,
			"width": 110,
		},
	]


def get_current_tasks():
	"""Unfinished tasks with an open assignment, as report rows keyed by the
	assignee's user. Active tasks come before submitted ones, then the soonest
	deadline first, so an employee's tasks read in the same order as the counts.

	Group (parent) tasks are left out: they only hold their child tasks, and the
	hours sit on those.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			todo.allocated_to,
			task.name AS id,
			task.subject AS title,
			project.project_name AS project,
			task.status,
			task.exp_start_date,
			task.exp_end_date,
			task.expected_time
		FROM `tabToDo` todo
		INNER JOIN `tabTask` task ON task.name = todo.reference_name
		LEFT JOIN `tabProject` project ON project.name = task.project
		WHERE todo.reference_type = 'Task'
			AND todo.status = 'Open'
			AND task.status NOT IN %(finished)s
			AND task.is_group = 0
			AND task.is_template = 0
		ORDER BY
			task.status IN %(submitted)s,
			task.exp_end_date IS NULL,
			task.exp_end_date,
			task.name
		""",
		{"finished": FINISHED_STATUSES, "submitted": SUBMITTED_STATUSES},
		as_dict=True,
	)

	logged_hours = get_logged_hours([row.id for row in rows])

	tasks_by_user = {}
	for row in rows:
		row.row_doctype = "Task"
		row.indent = 1
		row.expected_time = flt(row.expected_time)
		row.logged_hours = flt(logged_hours.get(row.id))
		row.utilization = get_utilization(row.logged_hours, row.expected_time)
		row.is_overdue = is_past_deadline(row.exp_end_date, row.status)
		row.is_submitted = row.status in SUBMITTED_STATUSES

		tasks_by_user.setdefault(row.pop("allocated_to"), []).append(row)

	return tasks_by_user


def get_logged_hours(task_names):
	"""Hours logged against each task so far, draft timesheets included.

	Task.actual_time counts submitted timesheets only, and a timesheet stays in
	draft until its week is submitted, so it misses most of the recent work.
	"""
	if not task_names:
		return {}

	return dict(
		frappe.db.sql(
			"""
			SELECT detail.task, SUM(detail.hours)
			FROM `tabTimesheet Detail` detail
			INNER JOIN `tabTimesheet` timesheet ON timesheet.name = detail.parent
			WHERE timesheet.docstatus < 2
				AND detail.task IN %(tasks)s
			GROUP BY detail.task
			""",
			{"tasks": task_names},
		)
	)


def get_employees(filters, assignees):
	"""Active employees who can be assigned tasks, or who hold one now."""
	conditions = ""

	if filters.get("department"):
		conditions += " AND employee.department = %(department)s"

	if filters.get("grade"):
		conditions += " AND employee.grade = %(grade)s"

	return frappe.db.sql(
		f"""
		SELECT
			employee.name,
			employee.employee_name,
			employee.department,
			employee.grade,
			employee.user_id
		FROM `tabEmployee` employee
		WHERE employee.status = 'Active'
			AND IFNULL(employee.user_id, '') != ''
			AND (
				employee.user_id IN %(assignees)s
				OR EXISTS (
					SELECT 1 FROM `tabHas Role` has_role
					WHERE has_role.parenttype = 'User'
						AND has_role.parent = employee.user_id
						AND has_role.role = %(role)s
				)
			)
			{conditions}
		ORDER BY employee.department, employee.employee_name
		""",
		{
			"department": filters.get("department"),
			"grade": filters.get("grade"),
			# An empty IN () is invalid SQL.
			"assignees": assignees or [""],
			"role": ASSIGNABLE_ROLE,
		},
		as_dict=True,
	)


def get_employee_row(employee, tasks):
	expected_time = sum(task.expected_time for task in tasks)
	logged_hours = sum(task.logged_hours for task in tasks)

	return {
		"row_doctype": "Employee",
		"id": employee.name,
		"title": employee.employee_name,
		"department": employee.department,
		"grade": employee.grade,
		"active_count": sum(1 for task in tasks if not task.is_submitted),
		"submitted_count": sum(1 for task in tasks if task.is_submitted),
		"overdue_count": sum(1 for task in tasks if task.is_overdue),
		"expected_time": expected_time,
		"utilization": get_utilization(logged_hours, expected_time),
		"indent": 0,
	}


def get_utilization(logged_hours, expected_time):
	"""Hours logged as a share of hours estimated. Blank when nothing is estimated."""
	if not expected_time:
		return None

	return flt(logged_hours) / expected_time * 100


def get_summary(data):
	employees = [row for row in data if row["indent"] == 0]
	pool = get_pool_tasks()

	return [
		{
			"value": len(employees),
			"label": _("Employees"),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"value": sum(1 for row in employees if not row["active_count"]),
			"label": _("With No Active Tasks"),
			"datatype": "Int",
			"indicator": "Orange",
		},
		{
			"value": sum(row["overdue_count"] for row in employees),
			"label": _("Overdue Tasks"),
			"datatype": "Int",
			"indicator": "Red",
		},
		{
			"value": len(pool),
			"label": _("Unassigned Tasks"),
			"datatype": "Int",
			"indicator": "Blue",
		},
	]
