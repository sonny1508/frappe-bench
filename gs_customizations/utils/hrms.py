import frappe

from hrms.hr.utils import (
    get_earned_leaves,
	get_leave_allocations,
	check_effective_date,
	get_monthly_earned_leave,
)

from frappe.utils import (
	add_days,
	add_months,
	comma_and,
	cstr,
	flt,
	format_datetime,
	formatdate,
	get_datetime,
	get_first_day,
	get_last_day,
	get_link_to_form,
	get_number_format_info,
	get_quarter_ending,
	get_quarter_start,
	get_year_ending,
	get_year_start,
	getdate,
	nowdate,
)

def allocate_earned_leaves():
	"""Allocate earned leaves to Employees"""
	e_leave_types = get_earned_leaves()
	today = frappe.flags.current_date or getdate()

	for e_leave_type in e_leave_types:
		leave_allocations = get_leave_allocations(today, e_leave_type.name)
		for allocation in leave_allocations:
			if not allocation.leave_policy_assignment and not allocation.leave_policy:
				continue

			leave_policy = (
				allocation.leave_policy
				if allocation.leave_policy
				else frappe.db.get_value(
					"Leave Policy Assignment", allocation.leave_policy_assignment, ["leave_policy"]
				)
			)

			annual_allocation = frappe.db.get_value(
				"Leave Policy Detail",
				filters={"parent": leave_policy, "leave_type": e_leave_type.name},
				fieldname=["annual_allocation"],
			)
			date_of_joining = frappe.db.get_value("Employee", allocation.employee, "date_of_joining")

			from_date = allocation.from_date

			if e_leave_type.allocate_on_day == "Date of Joining":
				from_date = date_of_joining

			if check_effective_date(
				from_date, today, e_leave_type.earned_leave_frequency, e_leave_type.allocate_on_day
			):
				update_previous_leave_allocation(allocation, annual_allocation, e_leave_type, date_of_joining)
				
def update_previous_leave_allocation(allocation, annual_allocation, e_leave_type, date_of_joining):
	allocation = frappe.get_doc("Leave Allocation", allocation.name)
	annual_allocation = flt(annual_allocation, allocation.precision("custom_total_time_leaves_allocated"))

	earned_leaves = get_monthly_earned_leave(
		date_of_joining,
		annual_allocation,
		e_leave_type.earned_leave_frequency,
		e_leave_type.rounding,
	)

	new_allocation = flt(allocation.custom_total_time_leaves_allocated) + flt(earned_leaves)
	new_allocation_without_cf = flt(
		flt(allocation.get_existing_leave_count()) + flt(earned_leaves),
		allocation.precision("custom_total_time_leaves_allocated"),
	)

	if new_allocation > e_leave_type.max_leaves_allowed and e_leave_type.max_leaves_allowed > 0:
		new_allocation = e_leave_type.max_leaves_allowed

	if (
		new_allocation != allocation.custom_total_time_leaves_allocated
		# annual allocation as per policy should not be exceeded except for yearly leaves
		and (
			new_allocation_without_cf <= annual_allocation or e_leave_type.earned_leave_frequency == "Yearly"
		)
	):
		today_date = frappe.flags.current_date or getdate()

		allocation.db_set("custom_total_time_leaves_allocated", new_allocation, update_modified=False)
		create_additional_leave_ledger_entry(allocation, earned_leaves, today_date)

		if e_leave_type.allocate_on_day:
			text = _(
				"Allocated {0} leave(s) via scheduler on {1} based on the 'Allocate on Day' option set to {2}"
			).format(
				frappe.bold(earned_leaves), frappe.bold(formatdate(today_date)), e_leave_type.allocate_on_day
			)

		allocation.add_comment(comment_type="Info", text=text)
		
def create_additional_leave_ledger_entry(allocation, leaves, date):
	"""Create leave ledger entry for leave types"""
	allocation.custom_new_time_leaves_allocated = leaves
	allocation.from_date = date
	allocation.custom_unused_time_leaves = 0
	allocation.create_leave_ledger_entry()