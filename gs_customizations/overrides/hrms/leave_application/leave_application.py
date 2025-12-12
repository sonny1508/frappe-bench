import datetime

import frappe

from datetime import datetime as dt
from frappe import _
from frappe.query_builder.functions import Max, Min, Sum
from frappe.utils import (
	add_days,
	cint,
	cstr,
	date_diff,
	flt,
	formatdate,
	get_fullname,
	get_link_to_form,
	getdate,
	nowdate,

	format_duration,
	get_time,
	now_datetime,
	time_diff_in_hours,
	time_diff_in_seconds,
)

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

import hrms
from hrms.hr.doctype.leave_application.leave_application import (
	LeaveApplication,
	get_allocation_expiry_for_cf_leaves,
	get_holidays,
	get_leave_approver,
	is_lwp,
)
from gs_customizations.overrides.hrms.leave_ledger_entry.leave_ledger_entry import create_leave_ledger_entry
from hrms.hr.utils import (
	get_holiday_dates_for_employee,
	get_leave_period,
	set_employee_name,
	share_doc_with_approver,
	validate_active_employee,
)


def get_working_hours_in_seconds(employee):
	"""Get working hours from Company (Duration field in seconds)"""
	company = frappe.db.get_value("Employee", employee, "company")
	company_doc = frappe.get_cached_doc("Company", company)
	if company_doc.get("custom_total_working_hours"):
		return flt(company_doc.custom_total_working_hours)
	else:
		return 28800.0  # 8 hours default (28800 seconds)

class CustomLeaveApplication(LeaveApplication):
	def validate(self):
		"""Main validation - handles both hours and days mode"""
		# default validations
		validate_active_employee(self.employee)
		set_employee_name(self)
		self.validate_dates()
		self.validate_balance_leaves()
		self.validate_leave_overlap()
		self.validate_max_time()
		self.show_block_day_warning()
		self.validate_block_days()
		self.validate_salary_processed_days()
		self.validate_attendance()
		self.set_half_day_date()
		if frappe.db.get_value("Leave Type", self.leave_type, "is_optional_leave"):
				self.validate_optional_leave()
		self.validate_applicable_after()
		
		# Single Date: specific date with time range
		if self.custom_use_single_date:
			self.validate_times_within_working_hours()
			self.validate_times_order()
			self.validate_times_hours()
	
	def validate_times_within_working_hours(self):
		"""Validate that custom_from_time and custom_to_time are within company working hours"""
		company_doc = frappe.get_cached_doc("Company", self.company)
		
		if not hasattr(company_doc, 'custom_start_working_hour') or not hasattr(company_doc, 'custom_end_working_hour'):
			return  # Skip validation if fields don't exist
		
		start_work = get_time(company_doc.custom_start_working_hour)
		end_work = get_time(company_doc.custom_end_working_hour)
		custom_from_time = get_time(self.custom_from_time)
		custom_to_time = get_time(self.custom_to_time)
		
		if custom_from_time < start_work or custom_from_time > end_work:
			frappe.throw(
				_("From Time ({0}) must be between working hours {1} and {2}").format(
					self.custom_from_time,
					company_doc.custom_start_working_hour,
					company_doc.custom_end_working_hour
				)
			)
		
		if custom_to_time < start_work or custom_to_time > end_work:
			frappe.throw(
				_("To Time ({0}) must be between working hours {1} and {2}").format(
					self.custom_to_time,
					company_doc.custom_start_working_hour,
					company_doc.custom_end_working_hour
				)
			)

	def validate_times_order(self):
		"""Validate that custom_from_time must always starts before custom_to_time"""
		custom_from_time = get_time(self.custom_from_time)
		custom_to_time = get_time(self.custom_to_time)

		if custom_from_time > custom_to_time:
			frappe.throw(
				_("From Time ({0}) must starts before To Time ({1})").format(
					self.custom_from_time,
					self.custom_to_time
				)
			)

	def validate_times_hours(self):
		"""Validate that custom_from_time and custom_to_time are whole hours (no minutes or seconds)"""
		custom_from_time = get_time(self.custom_from_time)
		custom_to_time = get_time(self.custom_to_time)
		
		if custom_from_time.minute != 0 or custom_from_time.second != 0:
			frappe.throw(
				_("From Time ({0}) must be a whole hour (no minutes or seconds)").format(
					self.custom_from_time
				)
			)
		
		if custom_to_time.minute != 0 or custom_to_time.second != 0:
			frappe.throw(
				_("To Time ({0}) must be a whole hour (no minutes or seconds)").format(
					self.custom_to_time
				)
			)

	# override to use custom_total_leave_time instead of total_leave_days
	def validate_balance_leaves(self):
		if self.from_date and self.to_date:
			if self.custom_use_single_date and self.custom_from_time and self.custom_to_time:
				total_leave_time = get_amount_of_leave_time(
					self.employee,
					self.custom_from_time,
					self.custom_to_time,
				)
			else:
				total_leave_time = get_number_of_leave_days_in_seconds(
					self.employee,
					self.leave_type,
					self.from_date,
					self.to_date,
				)

			if total_leave_time <= 0:
				frappe.throw(
					_(
						"The day(s) on which you are applying for leave are holidays. You need not apply for leave."
					)
				)

			if not is_lwp(self.leave_type):
				leave_balance = get_leave_balance_on(
					self.employee,
					self.leave_type,
					self.from_date,
					self.to_date,
					consider_all_leaves_in_the_allocation_period=True,
					for_consumption=True,
				)
				leave_balance_for_consumption = flt(
					leave_balance.get("leave_balance_for_consumption")
				)
				if self.status != "Rejected" and (
					leave_balance_for_consumption < total_leave_time or not leave_balance_for_consumption
				):
					self.show_insufficient_balance_message(leave_balance_for_consumption)

	def validate_leave_overlap(self):
		if not self.name:
			# hack! if name is null, it could cause problems with !=
			self.name = "New Leave Application"

		for d in frappe.db.sql(
			"""
			select
				name, leave_type, posting_date, from_date, to_date, custom_total_leave_time
			from `tabLeave Application`
			where employee = %(employee)s and docstatus < 2 and status in ('Open', 'Approved')
			and to_date >= %(from_date)s and from_date <= %(to_date)s
			and name != %(name)s""",
			{
				"employee": self.employee,
				"from_date": self.from_date,
				"to_date": self.to_date,
				"name": self.name,
			},
			as_dict=1,
		):
			if (
				getdate(self.from_date) == getdate(d.to_date)
				or getdate(self.to_date) == getdate(d.from_date)
			):
				self.throw_overlap_error(d)

	# custom validate_max_time to override validate_max_days
	def validate_max_time(self):
		max_time = frappe.db.get_value("Leave Type", self.leave_type, "custom_max_continuous_time_allowed")
		if not max_time:
			return

		details = self.get_consecutive_leave_details()

		if details.total_consecutive_leaves > max_time:
			msg = _("Leave of type {0} cannot be longer than {1}.").format(
				get_link_to_form("Leave Type", self.leave_type), max_time
			)
			if details.leave_applications:
				msg += "<br><br>" + _("Reference: {0}").format(
					", ".join(
						get_link_to_form("Leave Application", name) for name in details.leave_applications
					)
				)

			frappe.throw(msg, title=_("Maximum Continuous Time Leaves Exceeded"))

	def get_consecutive_leave_details(self) -> dict:
		leave_applications = set()

		def _get_first_from_date(reference_date):
			"""gets `from_date` of first leave application from previous consecutive leave applications"""
			prev_date = add_days(reference_date, -1)
			application = frappe.db.get_value(
				"Leave Application",
				{
					"employee": self.employee,
					"leave_type": self.leave_type,
					"to_date": prev_date,
					"docstatus": ["!=", 2],
					"status": ["in", ["Open", "Approved"]],
				},
				["name", "from_date"],
				as_dict=True,
			)
			if application:
				leave_applications.add(application.name)
				return _get_first_from_date(application.from_date)
			return reference_date

		def _get_last_to_date(reference_date):
			"""gets `to_date` of last leave application from following consecutive leave applications"""
			next_date = add_days(reference_date, 1)
			application = frappe.db.get_value(
				"Leave Application",
				{
					"employee": self.employee,
					"leave_type": self.leave_type,
					"from_date": next_date,
					"docstatus": ["!=", 2],
					"status": ["in", ["Open", "Approved"]],
				},
				["name", "to_date"],
				as_dict=True,
			)
			if application:
				leave_applications.add(application.name)
				return _get_last_to_date(application.to_date)
			return reference_date

		first_from_date = _get_first_from_date(self.from_date)
		last_to_date = _get_last_to_date(self.to_date)

		total_consecutive_leaves = get_number_of_leave_days_in_seconds(
			self.employee, self.leave_type, first_from_date, last_to_date
		)

		return frappe._dict(
			{
				"total_consecutive_leaves": total_consecutive_leaves,
				"leave_applications": leave_applications,
			}
		)

	def calculate_break_overlap(self, custom_from_time, custom_to_time):
		"""Calculate the overlap between leave time and break time"""
		return calculate_break_overlap(self.company, custom_from_time, custom_to_time)
	
	def get_working_hours_in_seconds(self):
		"""Get working hours from Company (Duration field in seconds)"""
		return get_working_hours_in_seconds(self.employee)

	def create_leave_ledger_entry(self, submit=True):
		if self.status != "Approved" and submit:
			return

		expiry_date = get_allocation_expiry_for_cf_leaves(
			self.employee, self.leave_type, self.to_date, self.from_date
		)
		lwp = frappe.db.get_value("Leave Type", self.leave_type, "is_lwp")

		if expiry_date:
			self.create_ledger_entry_for_intermediate_allocation_expiry(expiry_date, submit, lwp)
		else:
			alloc_on_from_date, alloc_on_to_date = self.get_allocation_based_on_application_dates()
			if self.is_separate_ledger_entry_required(alloc_on_from_date, alloc_on_to_date):
				# required only if negative balance is allowed for leave type
				# else will be stopped in validation itself
				self.create_separate_ledger_entries(alloc_on_from_date, alloc_on_to_date, submit, lwp)
			else:
				raise_exception = False if frappe.flags.in_patch else True
				args = dict(
					# self.total_leave_days -> self.custom_total_leave_time
					custom_time_leaves=self.custom_total_leave_time * -1,
					from_date=self.from_date,
					to_date=self.to_date,
					is_lwp=lwp,
					holiday_list=get_holiday_list_for_employee(self.employee, raise_exception=raise_exception)
					or "",
				)
				create_leave_ledger_entry(self, args, submit)
	
	def create_separate_ledger_entries(self, alloc_on_from_date, alloc_on_to_date, submit, lwp):
		"""Creates separate ledger entries for application period falling into separate allocations"""
		# for creating separate ledger entries existing allocation periods should be consecutive
		if (
			submit
			and alloc_on_from_date
			and alloc_on_to_date
			and add_days(alloc_on_from_date.to_date, 1) != alloc_on_to_date.from_date
		):
			frappe.throw(
				_(
					"Leave Application period cannot be across two non-consecutive leave allocations {0} and {1}."
				).format(
					get_link_to_form("Leave Allocation", alloc_on_from_date.name),
					get_link_to_form("Leave Allocation", alloc_on_to_date),
				)
			)

		raise_exception = False if frappe.flags.in_patch else True

		if alloc_on_from_date:
			first_alloc_end = alloc_on_from_date.to_date
			second_alloc_start = add_days(alloc_on_from_date.to_date, 1)
		else:
			first_alloc_end = add_days(alloc_on_to_date.from_date, -1)
			second_alloc_start = alloc_on_to_date.from_date

		leaves_in_first_alloc = get_number_of_leave_days_in_seconds(
			self.employee,
			self.leave_type,
			self.from_date,
			first_alloc_end,
		)
		leaves_in_second_alloc = get_number_of_leave_days_in_seconds(
			self.employee,
			self.leave_type,
			second_alloc_start,
			self.to_date,
		)

		args = dict(
			is_lwp=lwp,
			holiday_list=get_holiday_list_for_employee(self.employee, raise_exception=raise_exception) or "",
		)

		if leaves_in_first_alloc:
			args.update(
				dict(from_date=self.from_date, to_date=first_alloc_end, custom_time_leaves=leaves_in_first_alloc * -1)
			)
			create_leave_ledger_entry(self, args, submit)

		if leaves_in_second_alloc:
			args.update(
				dict(from_date=second_alloc_start, to_date=self.to_date, custom_time_leaves=leaves_in_second_alloc * -1)
			)
			create_leave_ledger_entry(self, args, submit)

	def create_ledger_entry_for_intermediate_allocation_expiry(self, expiry_date, submit, lwp):
		"""Splits leave application into two ledger entries to consider expiry of allocation"""
		raise_exception = False if frappe.flags.in_patch else True

		leaves = get_number_of_leave_days_in_seconds(
			self.employee, self.leave_type, self.from_date, expiry_date
		)

		if leaves:
			args = dict(
				from_date=self.from_date,
				to_date=expiry_date,
				custom_time_leaves=leaves * -1,
				is_lwp=lwp,
				holiday_list=get_holiday_list_for_employee(self.employee, raise_exception=raise_exception)
				or "",
			)
			create_leave_ledger_entry(self, args, submit)

		if getdate(expiry_date) != getdate(self.to_date):
			start_date = add_days(expiry_date, 1)
			leaves = get_number_of_leave_days_in_seconds(
				self.employee, self.leave_type, start_date, self.to_date
			)

			if leaves:
				args.update(dict(from_date=start_date, to_date=self.to_date, custom_time_leaves=leaves * -1))
				create_leave_ledger_entry(self, args, submit)

def calculate_break_overlap(company: str, custom_from_time, custom_to_time):
	"""Calculate the overlap between leave time and break time"""
	company_doc = frappe.get_cached_doc("Company", company)
		
	lunch_start = company_doc.custom_start_lunch_hour
	lunch_end = company_doc.custom_end_lunch_hour
	if not lunch_start or not lunch_end:
		return 0.0
	
	# Convert time objects to datetime objects (using today's date as base)
	base_date = now_datetime().date()
	
	working_start_time = get_time(custom_from_time)
	working_end_time = get_time(custom_to_time)
	lunch_start_time = get_time(lunch_start)
	lunch_end_time = get_time(lunch_end)
	
	# Combine date + time to create datetime objects
	working_start_dt = dt.combine(base_date, working_start_time)
	working_end_dt = dt.combine(base_date, working_end_time)
	lunch_start_dt = dt.combine(base_date, lunch_start_time)
	lunch_end_dt = dt.combine(base_date, lunch_end_time)
	
	# Calculate overlap
	if working_start_dt >= lunch_end_dt or working_end_dt <= lunch_start_dt:
		return 0.0
	
	overlap_start = max(working_start_dt, lunch_start_dt)
	overlap_end = min(working_end_dt, lunch_end_dt)
	
	break_overlap = time_diff_in_seconds(overlap_end, overlap_start)
	return max(break_overlap, 0.0)  # Ensure non-negative result


@frappe.whitelist()
def get_number_of_leave_days_in_seconds(
	employee: str,
	leave_type: str,
	from_date: datetime.date,
	to_date: datetime.date,
	holiday_list: str | None = None,
) -> float:
	"""Returns number of leave days between 2 dates after considering and holidays
	(Based on the include_holiday setting in Leave Type)"""
	number_of_days = 0
	number_of_days = date_diff(to_date, from_date) + 1

	if not frappe.db.get_value("Leave Type", leave_type, "include_holiday"):
		number_of_days = flt(number_of_days) - flt(
			get_holidays(employee, from_date, to_date, holiday_list=holiday_list)
		)
	return number_of_days * get_working_hours_in_seconds(employee)


@frappe.whitelist()
def get_amount_of_leave_time(
	employee: str,
	# custom_single_date: datetime.date,
	# leave_type: str,
	# custom_single_date: datetime.date,
	custom_from_time,
	custom_to_time,
) -> float:
	"""Returns the amount of leave time in seconds between two times, minus lunch break"""
	# get company from employee
	company = frappe.db.get_value("Employee", employee, "company")
	 
	custom_total_leave_time = 1
	if custom_from_time != custom_to_time:
		custom_total_leave_time = abs(time_diff_in_seconds(custom_to_time, custom_from_time))

		# calculate break overlap in hours
		break_overlap = calculate_break_overlap(company, custom_from_time, custom_to_time)

		custom_total_leave_time -= break_overlap

	return custom_total_leave_time


@frappe.whitelist()
def get_leave_details(employee, date, for_salary_slip=False):
	allocation_records = get_leave_allocation_records(employee, date)

	leave_allocation = {}

	for d in allocation_records:
		allocation = allocation_records.get(d, frappe._dict())
		to_date = date if for_salary_slip else allocation.to_date
		remaining_leaves = get_leave_balance_on(
			employee,
			d,
			date,
			to_date=to_date,
			consider_all_leaves_in_the_allocation_period=False if for_salary_slip else True,
		)

		leaves_taken = get_leaves_for_period(employee, d, allocation.from_date, to_date) * -1
		leaves_pending = get_leaves_pending_approval_for_period(employee, d, allocation.from_date, to_date)
		expired_leaves = allocation.total_leaves_allocated - (remaining_leaves + leaves_taken)

		leave_allocation[d] = {
			"total_leaves": format_duration(flt(allocation.total_leaves_allocated)),
			"expired_leaves": format_duration(flt(expired_leaves)) if expired_leaves > 0 else 0,
			"leaves_taken": format_duration(flt(leaves_taken)),
			"leaves_pending_approval": format_duration(flt(leaves_pending)),
			"remaining_leaves": format_duration(flt(remaining_leaves)),
		}

	# is used in set query
	lwp = frappe.get_list("Leave Type", filters={"is_lwp": 1}, pluck="name")

	return {
		"leave_allocation": leave_allocation,
		"leave_approver": get_leave_approver(employee),
		"lwps": lwp,
	}


# override so that it targets the correct get_leave_allocation_records
@frappe.whitelist()
def get_leave_balance_on(
	employee: str,
	leave_type: str,
	date: datetime.date,
	to_date: datetime.date | None = None,
	consider_all_leaves_in_the_allocation_period: bool = False,
	for_consumption: bool = False,
):
	"""
	Returns leave balance till date
	:param employee: employee name
	:param leave_type: leave type
	:param date: date to check balance on
	:param to_date: future date to check for allocation expiry
	:param consider_all_leaves_in_the_allocation_period: consider all leaves taken till the allocation end date
	:param for_consumption: flag to check if leave balance is required for consumption or display
			eg: employee has leave balance = 10 but allocation is expiring in 1 day so employee can only consume 1 leave
			in this case leave_balance = 10 but leave_balance_for_consumption = 1
			if True, returns a dict eg: {'leave_balance': 10, 'leave_balance_for_consumption': 1}
			else, returns leave_balance (in this case 10)
	"""

	if not to_date:
		to_date = nowdate()

	allocation_records = get_leave_allocation_records(employee, date, leave_type)
	allocation = allocation_records.get(leave_type, frappe._dict())

	end_date = allocation.to_date if cint(consider_all_leaves_in_the_allocation_period) else date
	cf_expiry = get_allocation_expiry_for_cf_leaves(employee, leave_type, to_date, allocation.from_date)

	leaves_taken = get_leaves_for_period(employee, leave_type, allocation.from_date, end_date)

	manually_expired_leaves = get_manually_expired_leaves(
		employee, leave_type, allocation.from_date, end_date
	)

	remaining_leaves = get_remaining_leaves(
		allocation, leaves_taken, date, cf_expiry, manually_expired_leaves, employee
	)

	if for_consumption:
		return remaining_leaves
	else:
		return remaining_leaves.get("leave_balance")
	 

def get_leave_allocation_records(employee, date, leave_type=None):
	"""Returns the total allocated leaves and carry forwarded leaves based on ledger entries"""
	Ledger = frappe.qb.DocType("Leave Ledger Entry")
	LeaveAllocation = frappe.qb.DocType("Leave Allocation")

	cf_leave_case = frappe.qb.terms.Case().when(Ledger.is_carry_forward == "1", Ledger.custom_time_leaves).else_(0)
	sum_cf_leaves = Sum(cf_leave_case).as_("cf_leaves")

	new_leaves_case = frappe.qb.terms.Case().when(Ledger.is_carry_forward == "0", Ledger.custom_time_leaves).else_(0)
	 
	sum_new_leaves = Sum(new_leaves_case).as_("new_leaves")

	query = (
		frappe.qb.from_(Ledger)
		.inner_join(LeaveAllocation)
		.on(Ledger.transaction_name == LeaveAllocation.name)
		.select(
			sum_cf_leaves,
			sum_new_leaves,
			Min(Ledger.from_date).as_("from_date"),
			Max(Ledger.to_date).as_("to_date"),
			Ledger.leave_type,
			Ledger.employee,
		)
		.where(
			(Ledger.from_date <= date)
			& (Ledger.docstatus == 1)
			& (Ledger.transaction_type == "Leave Allocation")
			& (Ledger.employee == employee)
			& (Ledger.is_expired == 0)
			& (Ledger.is_lwp == 0)
			& (
				# newly allocated leave's end date is same as the leave allocation's to date
				((Ledger.is_carry_forward == 0) & (Ledger.to_date >= date))
				# carry forwarded leave's end date won't be same as the leave allocation's to date
				# it's between the leave allocation's from and to date
				| (
					(Ledger.is_carry_forward == 1)
					& (Ledger.to_date.between(LeaveAllocation.from_date, LeaveAllocation.to_date))
					# only consider cf leaves from current allocation
					& (LeaveAllocation.from_date <= date)
					& (date <= LeaveAllocation.to_date)
				)
			)
		)
	)

	if leave_type:
		query = query.where(Ledger.leave_type == leave_type)
	query = query.groupby(Ledger.employee, Ledger.leave_type)

	allocation_details = query.run(as_dict=True)

	allocated_leaves = frappe._dict()
	for d in allocation_details:
		allocated_leaves.setdefault(
			d.leave_type,
			frappe._dict(
				{
					"from_date": d.from_date,
					"to_date": d.to_date,
					"total_leaves_allocated": flt(d.cf_leaves) + flt(d.new_leaves),
					"unused_leaves": d.cf_leaves,
					"new_leaves_allocated": d.new_leaves,
					"leave_type": d.leave_type,
					"employee": d.employee,
				}
			),
		)
	return allocated_leaves


def get_leaves_pending_approval_for_period(
	employee: str, leave_type: str, from_date: datetime.date, to_date: datetime.date
) -> float:
	"""Returns leaves that are pending for approval"""
	leaves = frappe.get_all(
		"Leave Application",
		filters={"employee": employee, "leave_type": leave_type, "status": "Open"},
		or_filters={
			"from_date": ["between", (from_date, to_date)],
			"to_date": ["between", (from_date, to_date)],
		},
		# total_leave_days -> custom_total_leave_time
		fields=["SUM(custom_total_leave_time) as leaves"],
	)[0]
	return leaves["leaves"] if leaves["leaves"] else 0.0


def get_remaining_leaves(
	allocation: dict, 
	leaves_taken: float, 
	date: str, 
	cf_expiry: str, 
	manually_expired_leaves: float,
	employee: str = None,
) -> dict[str, float]:
	"""Returns a dict of leave_balance and leave_balance_for_consumption (in seconds)
	leave_balance returns the available leave balance
	leave_balance_for_consumption returns the minimum leaves remaining after comparing with remaining time for allocation expiry
	"""
	
	# Get working seconds per day for time-based calculation
	if employee:
		working_seconds_per_day = get_working_hours_in_seconds(employee)
	else:
		working_seconds_per_day = 28800.0  # 8 hours default

	def _get_remaining_leaves(remaining_leaves, end_date):
		"""Returns minimum leaves remaining after comparing with remaining time for allocation expiry"""
		if remaining_leaves > 0:
			remaining_days = date_diff(end_date, date) + 1
			remaining_time = remaining_days * working_seconds_per_day
			remaining_leaves = min(remaining_time, remaining_leaves)
		return remaining_leaves

	if cf_expiry and allocation.unused_leaves:
		# allocation contains both carry forwarded and new leaves
		new_leaves_taken, cf_leaves_taken = get_new_and_cf_leaves_taken(allocation, cf_expiry)

		if getdate(date) > getdate(cf_expiry):
			# carry forwarded leaves have expired
			cf_leaves = remaining_cf_leaves = 0
		else:
			cf_leaves = flt(allocation.unused_leaves) + flt(cf_leaves_taken)
			remaining_cf_leaves = _get_remaining_leaves(cf_leaves, cf_expiry)

		# new leaves allocated - new leaves taken + cf leave balance
		# Note: `new_leaves_taken` is added here because its already a -ve number in the ledger
		leave_balance = (
			(flt(allocation.new_leaves_allocated) + flt(new_leaves_taken))
			+ flt(cf_leaves)
			+ flt(manually_expired_leaves)
		)
		leave_balance_for_consumption = (
			(flt(allocation.new_leaves_allocated) + flt(new_leaves_taken))
			+ flt(remaining_cf_leaves)
			+ flt(manually_expired_leaves)
		)
	else:
		# allocation only contains newly allocated leaves
		leave_balance = leave_balance_for_consumption = (
			flt(allocation.total_leaves_allocated) + flt(leaves_taken) + flt(manually_expired_leaves)
		)

	remaining_leaves = _get_remaining_leaves(leave_balance_for_consumption, allocation.to_date)
	return frappe._dict(leave_balance=leave_balance, leave_balance_for_consumption=remaining_leaves)


def get_manually_expired_leaves(
	employee: str, leave_type: str, from_date: datetime.date, end_date: datetime.date
):
	ledger = frappe.qb.DocType("Leave Ledger Entry")

	leaves = (
		frappe.qb.from_(ledger)
		# leaves -> custom_time_leaves
		.select(ledger.custom_time_leaves)
		.where(
			(ledger.docstatus == 1)
			& (ledger.employee == employee)
			& (ledger.leave_type == leave_type)
			& (ledger.from_date >= from_date)
			& (ledger.to_date <= end_date)
			& (ledger.transaction_type == "Leave Allocation")
			& ((ledger.is_expired == 1) & (ledger.is_carry_forward == 0))
		)
	).run()
	return leaves[0][0] if leaves else 0.0


# override so that is uses the custom get_leaves_for_period
def get_new_and_cf_leaves_taken(allocation: dict, cf_expiry: str) -> tuple[float, float]:
    """Returns new leaves taken and carry forwarded leaves taken within an allocation period based on cf leave expiry"""
    cf_leaves_taken = get_leaves_for_period(
        allocation.employee, allocation.leave_type, allocation.from_date, cf_expiry
    )
    new_leaves_taken = get_leaves_for_period(
        allocation.employee, allocation.leave_type, add_days(cf_expiry, 1), allocation.to_date
    )

    # using abs because leaves taken is a -ve number in the ledger
    if abs(cf_leaves_taken) > allocation.unused_leaves:
        # adjust the excess leaves in new_leaves_taken
        new_leaves_taken += -(abs(cf_leaves_taken) - allocation.unused_leaves)
        cf_leaves_taken = -allocation.unused_leaves

    return new_leaves_taken, cf_leaves_taken


# exist so that it uses the custom get_leave_entries
def get_leaves_for_period(
	employee: str,
	leave_type: str,
	from_date: datetime.date,
	to_date: datetime.date,
	skip_expired_leaves: bool = True,
) -> float:
	leave_entries = get_leave_entries(employee, leave_type, from_date, to_date)
	leave_time = 0

	for leave_entry in leave_entries:
		inclusive_period = leave_entry.from_date >= getdate(from_date) and leave_entry.to_date <= getdate(
			to_date
		)

		if inclusive_period and leave_entry.transaction_type == "Leave Encashment":
			# .leaves -> .custom_time_leaves
			leave_time += leave_entry.custom_time_leaves

		elif (
			inclusive_period
			and leave_entry.transaction_type == "Leave Allocation"
			and leave_entry.is_expired
			and not skip_expired_leaves
		):
			# .leaves -> .custom_time_leaves
			leave_time += leave_entry.custom_time_leaves

		elif leave_entry.transaction_type == "Leave Application":
			inclusive_period = leave_entry.from_date >= getdate(from_date) and leave_entry.to_date <= getdate(to_date)
			
			if inclusive_period:
				# Fully within query period - use stored value directly
				leave_time += leave_entry.custom_time_leaves
			else:
				# Partial overlap - recalculate for trimmed period
				trimmed_from = leave_entry.from_date
				trimmed_to = leave_entry.to_date
				
				if trimmed_from < getdate(from_date):
					trimmed_from = from_date
				if trimmed_to > getdate(to_date):
					trimmed_to = to_date
				
				leave_time += (
					get_number_of_leave_days_in_seconds(
						employee,
						leave_type,
						trimmed_from,
						trimmed_to,
						holiday_list=leave_entry.holiday_list,
					)
					* -1
				)

	return leave_time

def get_leave_entries(employee, leave_type, from_date, to_date):
	"""Returns leave entries between from_date and to_date."""
	# AND (leaves<0) -> AND (custom_time_leaves<0)
	return frappe.db.sql(
		"""
		SELECT
			employee, leave_type, from_date, to_date, custom_time_leaves, transaction_name, transaction_type, holiday_list,
			is_carry_forward, is_expired
		FROM `tabLeave Ledger Entry`
		WHERE employee=%(employee)s AND leave_type=%(leave_type)s
			AND docstatus=1
			AND (custom_time_leaves<0
				OR is_expired=1)
			AND (from_date between %(from_date)s AND %(to_date)s
				OR to_date between %(from_date)s AND %(to_date)s
				OR (from_date < %(from_date)s AND to_date > %(to_date)s))
	""",
		{"from_date": from_date, "to_date": to_date, "employee": employee, "leave_type": leave_type},
		as_dict=1,
	)

# override for total_leave_days -> custom_total_leave_time
def get_approved_leaves_for_period(employee, leave_type, from_date, to_date):
	LeaveApplication = frappe.qb.DocType("Leave Application")
	query = (
		frappe.qb.from_(LeaveApplication)
		.select(
			LeaveApplication.employee,
			LeaveApplication.leave_type,
			LeaveApplication.from_date,
			LeaveApplication.to_date,
			LeaveApplication.custom_total_leave_time,
		)
		.where(
			(LeaveApplication.employee == employee)
			& (LeaveApplication.docstatus == 1)
			& (LeaveApplication.status == "Approved")
			& (
				(LeaveApplication.from_date.between(from_date, to_date))
				| (LeaveApplication.to_date.between(from_date, to_date))
				| ((LeaveApplication.from_date < from_date) & (LeaveApplication.to_date > to_date))
			)
		)
	)

	if leave_type:
		query = query.where(LeaveApplication.leave_type == leave_type)

	leave_applications = query.run(as_dict=True)

	leave_days = 0
	for leave_app in leave_applications:
		if leave_app.from_date >= getdate(from_date) and leave_app.to_date <= getdate(to_date):
			leave_days += leave_app.custom_total_leave_time
		else:
			if leave_app.from_date < getdate(from_date):
				leave_app.from_date = from_date
			if leave_app.to_date > getdate(to_date):
				leave_app.to_date = to_date

			leave_days += get_number_of_leave_days_in_seconds(
				employee, leave_type, leave_app.from_date, leave_app.to_date
			)

	return leave_days