from itertools import groupby

import frappe
from frappe import _
from frappe.query_builder.functions import Abs, Sum
from frappe.utils import add_days, cint, flt, getdate

from hrms.hr.report.employee_leave_balance import (
	employee_leave_balance,
)

from hrms.hr.report.employee_leave_balance.employee_leave_balance import (
	get_leave_types,
	get_employees,
	get_allocated_and_expired_leaves,
	get_opening_balance,
)

from gs_customizations.overrides.hrms.leave_application.leave_application import (
	get_leave_balance_on,
	get_leaves_for_period,
)

Filters = frappe._dict

def apply_employee_leave_balance_overrides():
	"""Monkey patch the report functions"""
	employee_leave_balance.get_data = get_data
	employee_leave_balance.get_columns = get_columns
	employee_leave_balance.get_allocated_leaves = get_allocated_leaves
	employee_leave_balance.get_expired_leaves = get_expired_leaves
	employee_leave_balance.get_cf_leaves = get_cf_leaves
	employee_leave_balance.get_dataset_for_chart = get_dataset_for_chart

def get_columns():
	return [
		{
			"label": _("Leave Type"),
			"fieldtype": "Link",
			"fieldname": "leave_type",
			"width": 200,
			"options": "Leave Type",
		},
		{
			"label": _("Employee"),
			"fieldtype": "Link",
			"fieldname": "employee",
			"width": 100,
			"options": "Employee",
		},
		{
			"label": _("Employee Name"),
			"fieldtype": "Dynamic Link",
			"fieldname": "employee_name",
			"width": 100,
			"options": "employee",
		},
		{
			"label": _("Opening Balance"),
			"fieldtype": "Duration",
			"fieldname": "opening_balance",
			"width": 150,
		},
		{
			"label": _("New Leave(s) Allocated"),
			"fieldtype": "Duration",
			"fieldname": "leaves_allocated",
			"width": 200,
		},
		{
			"label": _("Leave(s) Taken"),
			"fieldtype": "Duration",
			"fieldname": "leaves_taken",
			"width": 150,
		},
		{
			"label": _("Leave(s) Expired"),
			"fieldtype": "Duration",
			"fieldname": "leaves_expired",
			"width": 150,
		},
		{
			"label": _("Closing Balance"),
			"fieldtype": "Duration",
			"fieldname": "closing_balance",
			"width": 150,
		},
	]


def get_data(filters: Filters) -> list:
	leave_types = get_leave_types()
	active_employees = get_employees(filters)

	precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))
	consolidate_leave_types = len(active_employees) > 1 and filters.consolidate_leave_types
	row = None

	data = []

	for leave_type in leave_types:
		if consolidate_leave_types:
			data.append({"leave_type": leave_type})
		else:
			row = frappe._dict({"leave_type": leave_type})

		for employee in active_employees:
			if consolidate_leave_types:
				row = frappe._dict()
			else:
				row = frappe._dict({"leave_type": leave_type})

			row.employee = employee.name
			row.employee_name = employee.employee_name

			leaves_taken = (
				get_leaves_for_period(employee.name, leave_type, filters.from_date, filters.to_date) * -1
			)

			new_allocation, expired_leaves, carry_forwarded_leaves = get_allocated_and_expired_leaves(
				filters.from_date, filters.to_date, employee.name, leave_type
			)
			opening = get_opening_balance(employee.name, leave_type, filters, carry_forwarded_leaves)

			row.leaves_allocated = flt(new_allocation, precision)
			row.leaves_expired = flt(expired_leaves, precision)
			row.opening_balance = flt(opening, precision)
			row.leaves_taken = flt(leaves_taken, precision)

			closing = new_allocation + opening - (row.leaves_expired + leaves_taken)
			row.closing_balance = flt(closing, precision)
			row.indent = 1
			data.append(row)

	return data


def get_allocated_leaves(from_date, to_date, employee, leave_type):
	ledger = frappe.qb.DocType("Leave Ledger Entry")
	allocated_leaves = (
		frappe.qb.from_(ledger)
		.select(Sum(ledger.custom_time_leaves))
		.where(
			(ledger.docstatus == 1)
			& (ledger.transaction_type == "Leave Allocation")
			& (ledger.employee == employee)
			& (ledger.leave_type == leave_type)
			& ((ledger.from_date[from_date:to_date]) | (ledger.to_date[from_date:to_date]))
			& ((ledger.is_expired == 0) & (ledger.is_carry_forward == 0))
		)
	).run()[0][0]
	return allocated_leaves if allocated_leaves else 0.0


def get_expired_leaves(from_date, to_date, employee, leave_type):
	ledger = frappe.qb.DocType("Leave Ledger Entry")
	expired_leaves = (
		frappe.qb.from_(ledger)
		.select(Abs(Sum(ledger.custom_time_leaves)))
		.where(
			(ledger.docstatus == 1)
			& (ledger.transaction_type == "Leave Allocation")
			& (ledger.employee == employee)
			& (ledger.leave_type == leave_type)
			& ((ledger.from_date[from_date:to_date]) | (ledger.to_date[from_date:to_date]))
			& (ledger.is_expired == 1)
		)
	).run()[0][0]
	return expired_leaves if expired_leaves else 0.0


def get_cf_leaves(from_date, to_date, employee, leave_type):
	ledger = frappe.qb.DocType("Leave Ledger Entry")
	cf_leaves = (
		frappe.qb.from_(ledger)
		.select(Sum(ledger.custom_time_leaves))
		.where(
			(ledger.docstatus == 1)
			& (ledger.transaction_type == "Leave Allocation")
			& (ledger.employee == employee)
			& (ledger.leave_type == leave_type)
			& ((ledger.from_date[from_date:to_date]) | (ledger.to_date[from_date:to_date]))
			& ((ledger.is_expired == 0) & (ledger.is_carry_forward == 1))
		)
	).run()[0][0]
	return cf_leaves if cf_leaves else 0.0

# override to convert seconds to hours
def get_dataset_for_chart(employee_data: list, datasets: list, labels: list) -> list:
	leaves = []
	employee_data = sorted(employee_data, key=lambda k: k["employee_name"])

	for key, group in groupby(employee_data, lambda x: x["employee_name"]):
		for grp in group:
			if grp.closing_balance:
				leaves.append(
					frappe._dict({"leave_type": grp.leave_type, "closing_balance": grp.closing_balance})
				)

		if leaves:
			labels.append(key)

	for leave in leaves:
		datasets.append({"name": leave.leave_type, "values": [leave.closing_balance / 3600]})