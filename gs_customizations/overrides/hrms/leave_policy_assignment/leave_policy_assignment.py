import json

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils import (
	add_months,
	cint,
	comma_and,
	date_diff,
	flt,
	formatdate,
	get_first_day,
	get_last_day,
	get_link_to_form,
	get_quarter_ending,
	get_quarter_start,
	get_year_ending,
	get_year_start,
	getdate,
	rounded,
)

from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
    LeavePolicyAssignment,
	calculate_pro_rated_leaves,
)

class CustomLeavePolicyAssignment(LeavePolicyAssignment):

	def create_leave_allocation(self, annual_allocation, leave_details, date_of_joining):
		# Creates leave allocation for the given employee in the provided leave period
		carry_forward = self.carry_forward
		if self.carry_forward and not leave_details.is_carry_forward:
			carry_forward = 0

		new_leaves_allocated = self.get_new_leaves(annual_allocation, leave_details, date_of_joining)

		allocation = frappe.get_doc(
			dict(
				doctype="Leave Allocation",
				employee=self.employee,
				leave_type=leave_details.name,
				from_date=self.effective_from,
				to_date=self.effective_to,
				custom_new_time_leaves_allocated=new_leaves_allocated,
				leave_period=self.leave_period if self.assignment_based_on == "Leave Policy" else "",
				leave_policy_assignment=self.name,
				leave_policy=self.leave_policy,
				carry_forward=carry_forward,
			)
		)
		allocation.save(ignore_permissions=True)
		allocation.submit()
		return allocation.name, new_leaves_allocated

	def get_new_leaves(self, annual_allocation, leave_details, date_of_joining):
		current_date = getdate(frappe.flags.current_date) or getdate()
		# Earned Leaves and Compensatory Leaves are allocated by scheduler, initially allocate 0
		if leave_details.is_compensatory:
			new_leaves_allocated = 0
		# if earned leave is being allocated after the effective period, then let them be calculated pro-rata
		elif leave_details.is_earned_leave and current_date < getdate(self.effective_to):
			new_leaves_allocated = self.get_leaves_for_passed_period(
				annual_allocation, leave_details, date_of_joining
			)
		else:
			# calculate pro-rated leaves for other leave types
			new_leaves_allocated = calculate_pro_rated_leaves(
				annual_allocation,
				date_of_joining,
				self.effective_from,
				self.effective_to,
				is_earned_leave=False,
			)

		# leave allocation should not exceed annual allocation as per policy assignment expect when allocation is of earned type and yearly
		if new_leaves_allocated > annual_allocation and not (
			leave_details.is_earned_leave and leave_details.earned_leave_frequency == "Yearly"
		):
			new_leaves_allocated = annual_allocation

		return flt(new_leaves_allocated)