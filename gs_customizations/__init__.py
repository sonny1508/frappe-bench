__version__= "0.4.0"

def apply_report_overrides():
	from gs_customizations.overrides.hrms.employee_leave_balance.employee_leave_balance import apply_employee_leave_balance_overrides
	apply_employee_leave_balance_overrides()

	from gs_customizations.overrides.hrms.employee_leave_balance_summary.employee_leave_balance_summary import apply_employee_leave_balance_summary_overrides
	apply_employee_leave_balance_summary_overrides()

	from gs_customizations.overrides.hrms.report.monthly_attendance_sheet.monthly_attendance_sheet import apply_monthly_attendance_sheet_overrides
	apply_monthly_attendance_sheet_overrides()

	from gs_customizations.overrides.hrms.report.leave_ledger.leave_ledger import apply_leave_ledger_overrides
	apply_leave_ledger_overrides()
	
def apply_desk_overrides():
	from gs_customizations.overrides.frappe.desk.search import apply_search_overrides
	apply_search_overrides()

apply_report_overrides()
# apply_desk_overrides()

# from frappe.custom.doctype.property_setter.property_setter import make_property_setter

# def property_task():	
	
# 	make_property_setter(
# 		"Task",
# 		"status",
# 		"options",
# 		"Open\nWorking\nQA Pending\nQA Reviewing\nQA Feedback\nQA Approved\nDelivered\nClient Feedback\nOverdue\nCompleted\nCancelled\nClosed",
# 		"Text",
# 	),
	
# property_task()