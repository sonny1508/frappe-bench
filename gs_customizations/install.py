__version__ = "1.0"

def after_install():
	apply_report_overrides()
	apply_doctype_overrides()

def apply_report_overrides():
	from gs_customizations.overrides.hrms.employee_leave_balance.employee_leave_balance import apply_employee_leave_balance_overrides
	apply_employee_leave_balance_overrides()

	from gs_customizations.overrides.hrms.employee_leave_balance_summary.employee_leave_balance_summary import apply_employee_leave_balance_summary_overrides
	apply_employee_leave_balance_summary_overrides()

def apply_doctype_overrides():
	from gs_customizations.customize.customize_fields import (
		apply_custom_fields,
		apply_custom_properties,
	)