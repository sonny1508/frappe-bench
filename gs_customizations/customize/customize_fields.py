from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

def apply_custom_fields():
	custom_company()

	custom_leave_allocation()
	custom_leave_application()
	custom_leave_ledger_entry()
	custom_leave_type()

	custom_employee()
	custom_task()

def apply_custom_properties():
	property_company()

	property_leave_allocation()
	property_leave_application()
	property_leave_ledger_entry()
	property_leave_type()
	property_leave_policy_detail()

	property_task()
	property_task_type()
	property_timesheet()

	property_attendance()

# FRAPPE APP

# =============== COMPANY DOCTYPE ===============

def custom_company():
	create_custom_fields({
		"Company": [
			{
				"fieldname": "custom_start_working_hour",
				"fieldtype": "Time",
				"insert_after": "hr_settings_section",
				"is_system_generated": 0,
				"label": "Start Working Hour",
			},
			{
				"fieldname": "custom_end_working_hour",
				"fieldtype": "Time",
				"insert_after": "custom_start_working_hour",
				"is_system_generated": 0,
				"label": "End Working Hour",
			},
			{
				"depends_on": "eval:doc.custom_start_working_hour && doc.custom_end_working_hour && (doc.custom_start_working_hour != doc.custom_end_working_hour)",
				"fieldname": "custom_total_working_hours",
				"fieldtype": "Duration",
				"insert_after": "custom_end_working_hour",
				"is_system_generated": 0,
				"label": "Total Working Hours",
				"read_only": 1,
			},
			{
				"fieldname": "custom_start_lunch_hour",
				"fieldtype": "Time",
				"insert_after": "custom_total_working_hours",
				"is_system_generated": 0,
				"label": "Start Lunch Hour",
			},
			{
				"fieldname": "custom_end_lunch_hour",
				"fieldtype": "Time",
				"insert_after": "custom_start_lunch_hour",
				"is_system_generated": 0,
				"label": "End Lunch Hour",
			},
			{
				"depends_on": "eval:doc.custom_start_lunch_hour && doc.custom_end_lunch_hour && (doc.custom_start_lunch_hour != doc.custom_end_lunch_hour)",
				"fieldname": "custom_total_lunch_hours",
				"fieldtype": "Duration",
				"insert_after": "custom_end_lunch_hour",
				"is_system_generated": 0,
				"label": "Total Lunch Hours",
				"read_only": 1,
			},
		]
	})

def property_company():
	make_property_setter(
		"Company",
		"default_expense_claim_payable_account",
		"insert_after",
		"hr_settings_section",
		"Data",
	),
	make_property_setter(
		"Company",
		"default_employee_advance_account",
		"insert_after",
		"default_expense_claim_payable_account",
		"Text",
	),
	make_property_setter(
		"Company",
		"default_payroll_payable_account",
		"insert_after",
		"default_employee_advance_account",
		"Text",
	),
	make_property_setter(
		doctype="Company",
		fieldname="",
		property="field_order",
		value="[\"details\", \"company_name\", \"abbr\", \"default_currency\", \"country\", \"is_group\", \"default_holiday_list\", \"cb0\", \"default_letter_head\", \"tax_id\", \"domain\", \"date_of_establishment\", \"parent_company\", \"company_info\", \"company_logo\", \"date_of_incorporation\", \"phone_no\", \"email\", \"company_description\", \"column_break1\", \"date_of_commencement\", \"fax\", \"website\", \"address_html\", \"registration_info\", \"registration_details\", \"lft\", \"rgt\", \"old_parent\", \"accounts_tab\", \"section_break_28\", \"create_chart_of_accounts_based_on\", \"existing_company\", \"column_break_26\", \"chart_of_accounts\", \"default_settings\", \"default_bank_account\", \"default_cash_account\", \"default_receivable_account\", \"default_payable_account\", \"write_off_account\", \"unrealized_profit_loss_account\", \"column_break0\", \"allow_account_creation_against_child_company\", \"default_expense_account\", \"default_income_account\", \"default_discount_account\", \"payment_terms\", \"cost_center\", \"default_finance_book\", \"exchange_gain__loss_section\", \"exchange_gain_loss_account\", \"column_break_sttp\", \"unrealized_exchange_gain_loss_account\", \"round_off_section\", \"round_off_account\", \"round_off_cost_center\", \"column_break_jqfo\", \"round_off_for_opening\", \"deferred_accounting_section\", \"default_deferred_revenue_account\", \"column_break_dcdl\", \"default_deferred_expense_account\", \"advance_payments_section\", \"book_advance_payments_in_separate_party_account\", \"reconcile_on_advance_payment_date\", \"reconciliation_takes_effect_on\", \"column_break_fwcf\", \"default_advance_received_account\", \"default_advance_paid_account\", \"exchange_rate_revaluation_settings_section\", \"auto_exchange_rate_revaluation\", \"auto_err_frequency\", \"submit_err_jv\", \"budget_detail\", \"exception_budget_approver_role\", \"fixed_asset_defaults\", \"accumulated_depreciation_account\", \"depreciation_expense_account\", \"series_for_depreciation_entry\", \"expenses_included_in_asset_valuation\", \"column_break_40\", \"disposal_account\", \"depreciation_cost_center\", \"capital_work_in_progress_account\", \"asset_received_but_not_billed\", \"buying_and_selling_tab\", \"sales_settings\", \"default_buying_terms\", \"sales_monthly_history\", \"monthly_sales_target\", \"total_monthly_sales\", \"column_break_goals\", \"default_selling_terms\", \"default_warehouse_for_sales_return\", \"credit_limit\", \"hr_and_payroll_tab\", \"hr_settings_section\", \"custom_start_working_hour\", \"custom_end_working_hour\", \"custom_total_working_hours\", \"custom_start_lunch_hour\", \"custom_end_lunch_hour\", \"custom_total_lunch_hours\", \"column_break_10\", \"default_expense_claim_payable_account\", \"default_employee_advance_account\", \"default_payroll_payable_account\", \"transactions_annual_history\", \"stock_tab\", \"auto_accounting_for_stock_settings\", \"enable_perpetual_inventory\", \"enable_provisional_accounting_for_non_stock_items\", \"default_inventory_account\", \"stock_adjustment_account\", \"default_in_transit_warehouse\", \"column_break_32\", \"stock_received_but_not_billed\", \"default_provisional_account\", \"expenses_included_in_valuation\", \"manufacturing_section\", \"default_operating_cost_account\", \"dashboard_tab\"]",
		property_type="Data",
	),

# HRMS APP

# =============== EMPLOYEE DOCTYPE ===============

def custom_employee():
	create_custom_fields({
		"Employee": [
			{
				"default": "0",
				"fieldname": "custom_enable_timesheet_checkin",
				"fieldtype": "Check",
				"insert_after": "status",
				"is_system_generated": 0,
				"label": "Enable Timesheet Check-in Enforcement",
				"description": "When enabled, this employee will be redirected to the Timesheet Check-in page if they have unfilled timesheets for the current week.",
			},
			{
				"default": "0",
				"fieldname": "custom_enable_matrix_notifications",
				"fieldtype": "Check",
				"insert_after": "custom_enable_timesheet_checkin",
				"is_system_generated": 0,
				"label": "Enable Matrix Notifications",
				"description": "When enabled, this employee will receive task notifications via Element/Matrix.",
			},
		]
	})

# =============== LEAVE ALLOCATION DOCTYPE ===============

def custom_leave_allocation():
	create_custom_fields({
		"Leave Allocation": [
			{
				"allow_on_submit": 1,
  				"bold": 1,
				"fieldname": "custom_new_time_leaves_allocated",
				"fieldtype": "Duration",
				"hide_days": 1,
				"hide_seconds": 1,
				"insert_after": "new_leaves_allocated",
				"is_system_generated": 0,
				"label": "New Time Leaves Allocated",
			},
			{
				"depends_on": "carry_forward",
				"fieldname": "custom_unused_time_leaves",
				"fieldtype": "Duration",
				"hide_days": 1,
				"hide_seconds": 1,
				"insert_after": "unused_leaves",
				"is_system_generated": 0,
				"label": "Unused Time Leaves",
				"read_only": 1,
			},
			{
				"allow_on_submit": 1,
				"fieldname": "custom_total_time_leaves_allocated",
				"fieldtype": "Duration",
				"hide_days": 1,
				"hide_seconds": 1,
				"insert_after": "total_leaves_allocated",
				"is_system_generated": 0,
				"label": "Total Time Leaves Allocated",
				"read_only": 1,
				"reqd": 1,
			},
			{
				"depends_on": "eval:doc.total_leaves_encashed>0",
				"fieldname": "custom_total_time_leaves_encashed",
				"fieldtype": "Duration",
				"hide_days": 1,
				"hide_seconds": 1,
				"insert_after": "total_leaves_encashed",
				"is_system_generated": 0,
				"label": "Total Time Leaves Encashed",
				"read_only": 1,
			},
		]
	})

def property_leave_allocation():
	make_property_setter(
		"Leave Allocation",
		"new_leaves_allocated",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Allocation",
		"unused_leaves",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Allocation",
		"total_leaves_allocated",
		"reqd",
		"0",
		"Check",
	),
	make_property_setter(
		"Leave Allocation",
		"total_leaves_allocated",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Allocation",
		"total_leaves_encashed",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		doctype="Leave Allocation",
		fieldname="",
		property="field_order",
		value="[\"naming_series\", \"employee\", \"employee_name\", \"department\", \"company\", \"column_break1\", \"leave_type\", \"from_date\", \"to_date\", \"section_break_6\", \"new_leaves_allocated\", \"custom_new_time_leaves_allocated\", \"carry_forward\", \"unused_leaves\", \"custom_unused_time_leaves\", \"total_leaves_allocated\", \"custom_total_time_leaves_allocated\", \"total_leaves_encashed\", \"custom_total_time_leaves_encashed\", \"column_break_10\", \"compensatory_request\", \"leave_period\", \"leave_policy\", \"leave_policy_assignment\", \"carry_forwarded_leaves_count\", \"expired\", \"amended_from\", \"notes\", \"description\"]",
		property_type="Data",
	),

# =============== LEAVE APPLICATION DOCTYPE ===============

def custom_leave_application():
	create_custom_fields({
		"Leave Application": [
			{
				"allow_on_submit": 1,
				"fieldname": "workflow_state",
				"fieldtype": "Link",
				"hidden": 1,
				"is_system_generated": 0,
				"label": "Workflow State",
				"no_copy": 1,
				"options": "Workflow State",
			},
			{
				"default": "0",
				"fieldname": "custom_use_single_date",
				"fieldtype": "Check",
				"insert_after": "section_break_5",
				"is_system_generated": 0,
				"label": "Use Hours In A Single Date",
			},
			{
				"depends_on": "eval:doc.custom_use_single_date",
				"fieldname": "custom_single_date",
				"fieldtype": "Date",
				"insert_after": "custom_use_single_date",
				"is_system_generated": 0,
				"label": "Single Date",
				"mandatory_depends_on": "eval:doc.custom_use_single_date",
				"reqd": 1,
			},
			{
				"depends_on": "eval:doc.custom_use_single_date == 1",
				"fieldname": "custom_from_time",
				"fieldtype": "Time",
				"insert_after": "to_date",
				"is_system_generated": 0,
				"label": "From Time",
				"mandatory_depends_on": "eval:doc.custom_use_single_date == 1",
				"read_only": 0,
			},
			{
				"depends_on": "eval:doc.custom_use_single_date == 1",
				"fieldname": "custom_to_time",
				"fieldtype": "Time",
				"insert_after": "custom_from_time",
				"is_system_generated": 0,
				"label": "To Time",
				"mandatory_depends_on": "eval:doc.custom_use_single_date == 1",
				"read_only": 0,
			},
			{
				"fieldname": "custom_total_leave_time",
				"fieldtype": "Duration",
				"hide_seconds": 1,
				"in_list_view": 1,
				"insert_after": "total_leave_days",
				"is_system_generated": 0,
				"label": "Total Leave Time",
				"no_copy": 1,
				"read_only": 1,
			},
			{
				"fieldname": "custom_leave_balance_before_application",
				"fieldtype": "Duration",
				"hide_seconds": 1,
				"insert_after": "leave_balance",
				"is_system_generated": 0,
				"label": "Leave Balance Before Application",
				"no_copy": 1,
				"read_only": 1,
			},
		]
	})

def property_leave_application():
	make_property_setter(
		"Leave Application",
		"leave_balance",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Application",
		"from_date",
		"depends_on",
		"eval:doc.custom_use_single_date == 0",
		"Data",
	),
	make_property_setter(
		"Leave Application",
		"to_date",
		"depends_on",
		"eval:doc.custom_use_single_date == 0",
		"Data",
	),
	make_property_setter(
		"Leave Application",
		"from_date",
		"mandatory_depends_on",
		"eval:doc.custom_use_single_date == 0",
		"Data",
	),
	make_property_setter(
		"Leave Application",
		"to_date",
		"mandatory_depends_on",
		"eval:doc.custom_use_single_date == 0",
		"Data",
	),
	make_property_setter(
		"Leave Application",
		"total_leave_days",
		"hidden",
		"1",
		"check",
	),
	make_property_setter(
		"Leave Application",
		"total_leave_days",
		"in_list_view",
		"0",
		"check",
	),
	make_property_setter(
		"Leave Application",
		"half_day",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		doctype="Leave Application",
		fieldname="",
		property="field_order",
		value="[\"workflow_state\", \"naming_series\", \"employee\", \"employee_name\", \"column_break_4\", \"leave_type\", \"company\", \"department\", \"section_break_5\", \"custom_use_single_date\", \"custom_single_date\", \"from_date\", \"to_date\", \"custom_from_time\", \"custom_to_time\", \"half_day\", \"half_day_date\", \"total_leave_days\", \"custom_total_leave_time\", \"column_break1\", \"description\", \"leave_balance\", \"custom_leave_balance_before_application\", \"section_break_7\", \"leave_approver\", \"leave_approver_name\", \"follow_via_email\", \"column_break_18\", \"posting_date\", \"status\", \"sb_other_details\", \"salary_slip\", \"color\", \"column_break_17\", \"letter_head\", \"amended_from\"]",
		property_type="Data"
	),

# =============== LEAVE LEDGER ENTRY DOCTYPE ===============

def custom_leave_ledger_entry():
	create_custom_fields({
		"Leave Ledger Entry": [
			{
				"fieldname": "custom_time_leaves",
				"fieldtype": "Duration",
				"hide_seconds": 1,
				"in_list_view": 1,
				"insert_after": "leaves",
				"is_system_generated": 0,
				"label": "Time Leaves",
			},
		]
	})

def property_leave_ledger_entry():
	make_property_setter(
		"Leave Ledger Entry",
		"leaves",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Ledger Entry",
		"leaves",
		"in_list_view",
		"0",
		"Check",
	),
	make_property_setter(
		doctype="Leave Ledger Entry",
		fieldname="",
		property="field_order",
  		value="[\"employee\", \"employee_name\", \"leave_type\", \"transaction_type\", \"transaction_name\", \"company\", \"leaves\", \"custom_time_leaves\", \"column_break_7\", \"from_date\", \"to_date\", \"holiday_list\", \"is_carry_forward\", \"is_expired\", \"is_lwp\", \"amended_from\"]",
		property_type="Data",
	)

# =============== LEAVE TYPE DOCTYPE ===============

def custom_leave_type():
	create_custom_fields({
		"Leave Type": [
			{
				"fieldname": "custom_max_continuous_time_allowed",
				"fieldtype": "Duration",
				"hide_days": 1,
				"hide_seconds": 1,
				"in_list_view": 1,
				"insert_after": "max_continuous_days_allowed",
				"is_system_generated": 0,
				"label": "Maximum Continuous Time Leaves Allowed",
			},
		]
	})

def property_leave_type():
	make_property_setter(
		"Leave Type",
		"max_continuous_days_allowed",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Type",
		"max_continuous_days_allowed",
		"in_list_view",
		"0",
		"Check",
	),
	make_property_setter(
		"Leave Type",
		"max_leaves_allowed",
		"fieldtype",
		"Duration",
		"Data",
	),
	make_property_setter(
		"Leave Type",
		"max_leaves_allowed",
		"hide_seconds",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Type",
		"max_leaves_allowed",
		"hide_days",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Type",
		"maximum_carry_forwarded_leaves",
		"fieldtype",
		"Duration",
		"Data",
	),
	make_property_setter(
		doctype="Leave Type",
		fieldname="",
		property="field_order",
  		value="[\"leave_type_name\", \"max_leaves_allowed\", \"applicable_after\", \"max_continuous_days_allowed\", \"custom_max_continuous_time_allowed\", \"column_break_3\", \"is_carry_forward\", \"is_lwp\", \"is_ppl\", \"fraction_of_daily_salary_per_leave\", \"is_optional_leave\", \"allow_negative\", \"allow_over_allocation\", \"include_holiday\", \"is_compensatory\", \"carry_forward_section\", \"maximum_carry_forwarded_leaves\", \"expire_carry_forwarded_leaves_after_days\", \"encashment\", \"allow_encashment\", \"max_encashable_leaves\", \"non_encashable_leaves\", \"column_break_17\", \"earning_component\", \"earned_leave\", \"is_earned_leave\", \"earned_leave_frequency\", \"column_break_22\", \"allocate_on_day\", \"rounding\"]",
		property_type="Data",
	)

# =============== LEAVE POLICY DETAIL DOCTYPE ===============

def property_leave_policy_detail():	
	make_property_setter(
		"Leave Policy Detail",
		"annual_allocation",
		"fieldtype",
		"Duration",
		"Data",
	),
	make_property_setter(
		"Leave Policy Detail",
		"annual_allocation",
		"hide_days",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Policy Detail",
		"annual_allocation",
		"hide_seconds",
		"1",
		"Check",
	)

# =============== ATTENDANCE DOCTYPE ===============

def property_attendance():	
	make_property_setter(
		"Attendance",
		"working_hours",
		"precision",
		"2",
		"Data",
	),
	make_property_setter(
		"Leave Policy Detail",
		"annual_allocation",
		"hide_days",
		"1",
		"Check",
	),
	make_property_setter(
		"Leave Policy Detail",
		"annual_allocation",
		"hide_seconds",
		"1",
		"Check",
	)

	make_property_setter(
		"Attendance",
		"status",
		"options",
		"Present\nAbsent\nOn Leave\nHours Leave\nWork From Home",
		"Text",
	)

# ERPNEXT APP

# =============== TASK DOCTYPE ===============

def custom_task():
	create_custom_fields({
		"Task": [
			{
				"fieldname": "custom_assign_to_id",
				"fieldtype": "Data",
				"insert_after": "type",
				"is_hidden": 1,
				"is_system_generated": 0,
				"label": "Assign To ID",
				"read_only": 1,
			},
			{
				"fieldname": "custom_assign_to_employee",
				"fieldtype": "Data",
				"insert_after": "custom_assign_to_id",
				"is_system_generated": 0,
				"label": "Assign To Employee",
				"read_only": 1,
			},
			{
				"fieldname": "custom_reviewer",
				"fieldtype": "Data",
				"insert_after": "parent_task",
				"is_system_generated": 0,
				"label": "Reviewer",
				"read_only": 1,
			},
			{
				"fieldname": "custom_utilization",
				"fieldtype": "Percent",
				"insert_after": "exp_end_date",
				"is_system_generated": 0,
				"label": "Utilization",
				"read_only": 1,
			},						
		]
	})

def property_task():	
	make_property_setter(
		"Task",
		"status",
		"options",
		"Open\nWorking\nQA Pending\nQA Reviewing\nQA Feedback\nQA Approved\nDelivered\nClient Feedback\nOverdue\nCompleted\nCancelled\nClosed",
		"Text",
	),
	make_property_setter(
		"Task",
		"status",
		"hidden",
		"0",
		"Check",
	),
	make_property_setter(
		"Task",
		"priority",
		"options",
		"Urgent\nHigh\nMedium\nLow\nSupport",
		"Text",
	),
	make_property_setter(
		"Task",
		"type",
		"in_list_view",
		"1",
		"Check",
	),
	make_property_setter(
		"Task",
		"type",
		"is_milestone",
		"0",
		"Check",
	),
	make_property_setter(
		"Task",
		"task_weight",
		"hidden",
		"1",
		"Check",
	),
	make_property_setter(
		"Task",
		"progress",
		"hidden",
		"1",
		"Check"
	),

# =============== TASK TYPE DOCTYPE ===============

def property_task_type():
	make_property_setter(
		"Task Type",
		"weight",
		"hidden",
		"1",
		"Check",
	)

# =============== TIMESHEET DOCTYPE ===============

def property_timesheet():	
	make_property_setter(
		"Timesheet",
		"end_date",
		"in_list_view",
		"1",
		"Check",
	)