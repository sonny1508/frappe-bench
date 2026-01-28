import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
	add_days,
	cint,
	cstr,
	format_date,
	get_datetime,
	get_link_to_form,
	getdate,
	nowdate,
)

from hrms.hr.doctype.attendance.attendance import Attendance

from hrms.hr.utils import (
	# get_holiday_dates_for_employee,
	# get_holidays_for_employee,
	validate_active_employee,
)

class CustomAttendance(Attendance):
	def validate(self):
		from erpnext.controllers.status_updater import validate_status

		# Your custom status list
		validate_status(self.status, [
			"Present", "Absent", "On Leave", "Half Day", "Work From Home",
			"Hours Leave"  # modified
		])
		
		# Call the rest of the validations
		validate_active_employee(self.employee)
		self.validate_attendance_date()
		self.validate_duplicate_record()
		self.validate_overlapping_shift_attendance()
		self.validate_employee_status()
		self.check_leave_record()

	def check_leave_record(self):
		LeaveApplication = frappe.qb.DocType("Leave Application")
		leave_record = (
			frappe.qb.from_(LeaveApplication)
			.select(
				LeaveApplication.leave_type,
				LeaveApplication.custom_use_single_date, # modified
				LeaveApplication.custom_single_date, # modified
				LeaveApplication.custom_total_leave_time, # modified
				LeaveApplication.name,
			)
			.where(
				(LeaveApplication.employee == self.employee)
				& (self.attendance_date >= LeaveApplication.from_date)
				& (self.attendance_date <= LeaveApplication.to_date)
				& (LeaveApplication.status == "Approved")
				& (LeaveApplication.docstatus == 1)
			)
		).run(as_dict=True)

		if leave_record:
			for d in leave_record:
				self.leave_type = d.leave_type
				self.leave_application = d.name
				self.custom_total_leave_time = d.custom_total_leave_time
				if (d.custom_single_date == getdate(self.attendance_date)) and d.custom_use_single_date == 1: # modified
					self.status = "Hours Leave" # modified
					frappe.msgprint(
						_("Employee {0} on Hours Leave on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)
				else:
					self.status = "On Leave"
					frappe.msgprint(
						_("Employee {0} is on Leave on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)

		if self.status in ("On Leave", "Hours Leave"):
			if not leave_record:
				self.modify_half_day_status = 0
				self.half_day_status = "Absent"
				frappe.msgprint(
					_("No leave record found for employee {0} on {1}").format(
						self.employee, format_date(self.attendance_date)
					),
					alert=1,
				)
		elif self.leave_type:
			self.leave_type = None
			self.leave_application = None