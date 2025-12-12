import frappe
from frappe import _

from gs_customizations.overrides.hrms.leave_application.leave_application import get_leave_details

from hrms.hr.report.employee_leave_balance_summary import (
	employee_leave_balance_summary,
)

from hrms.hr.report.employee_leave_balance_summary.employee_leave_balance_summary import (
    get_conditions,
)

def apply_employee_leave_balance_summary_overrides():
	"""Monkey patch the report functions"""
	employee_leave_balance_summary.get_data = get_data

def get_data(filters, leave_types):
	conditions = get_conditions(filters)

	active_employees = frappe.get_list(
		"Employee",
		filters=conditions,
		fields=["name", "employee_name", "department", "user_id"],
	)

	data = []
	for employee in active_employees:
		row = [employee.name, employee.employee_name, employee.department]
		available_leave = get_leave_details(employee.name, filters.date)
		for leave_type in leave_types:
			remaining = 0
			if leave_type in available_leave["leave_allocation"]:
				# opening balance
				remaining = available_leave["leave_allocation"][leave_type]["remaining_leaves"]

			row += [remaining]

		data.append(row)

	return data