"""GS Task Pool: unfinished tasks nobody is assigned to yet.

The other half of GS Workload Sheet: the work waiting to be handed out. Like it,
it has no period and always shows the current state.

This can't be part of GS Task Sheet: that report always filters on completed_on
or exp_start_date, and an unassigned task has neither (exp_start_date is stamped
when someone is assigned), so it would never show up there.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today

from gs_customizations.overrides.erpnext.task.overdue_priority import (
	FINISHED_STATUSES,
	is_past_deadline,
)
from gs_customizations.validate.permissions import is_manager


def execute(filters=None):
	if not is_manager():
		frappe.throw(_("Only managers can view this report."), frappe.PermissionError)

	filters = frappe._dict(filters or {})

	return get_columns(), get_pool_tasks(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("ID"), "fieldtype": "Link", "options": "Task", "width": 150},
		{"fieldname": "subject", "label": _("Subject"), "fieldtype": "Data", "width": 220},
		{"fieldname": "project_name", "label": _("Project"), "fieldtype": "Data", "width": 160},
		{"fieldname": "type", "label": _("Type"), "fieldtype": "Link", "options": "Task Type", "width": 110},
		{"fieldname": "priority", "label": _("Priority"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "expected_time",
			"label": _("Expected Time (In Hours)"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 170,
		},
		{"fieldname": "exp_start_date", "label": _("Expected Start Date"), "fieldtype": "Date", "width": 140},
		{"fieldname": "exp_end_date", "label": _("Expected End Date"), "fieldtype": "Date", "width": 140},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int", "width": 90},
	]


def get_pool_tasks(filters=None):
	"""Unfinished tasks with no open assignment. Soonest deadline first.

	Group (parent) tasks are left out, as in GS Workload Sheet: the work to hand
	out is on their child tasks.
	"""
	filters = frappe._dict(filters or {})
	conditions = ""

	if filters.get("project"):
		conditions += " AND task.project = %(project)s"

	rows = frappe.db.sql(
		f"""
		SELECT
			task.name,
			task.subject,
			project.project_name,
			task.type,
			task.priority,
			task.status,
			task.expected_time,
			task.exp_start_date,
			task.exp_end_date
		FROM `tabTask` task
		LEFT JOIN `tabProject` project ON project.name = task.project
		WHERE task.status NOT IN %(finished)s
			AND task.is_group = 0
			AND task.is_template = 0
			AND NOT EXISTS (
				SELECT 1 FROM `tabToDo` todo
				WHERE todo.reference_type = 'Task'
					AND todo.reference_name = task.name
					AND todo.status = 'Open'
			)
			{conditions}
		ORDER BY task.exp_end_date IS NULL, task.exp_end_date, task.name
		""",
		{"finished": FINISHED_STATUSES, "project": filters.get("project")},
		as_dict=True,
	)

	for row in rows:
		row.expected_time = flt(row.expected_time)
		# Negative once the deadline has passed.
		row.days_left = date_diff(row.exp_end_date, today()) if row.exp_end_date else None
		row.is_overdue = is_past_deadline(row.exp_end_date, row.status)

	return rows
