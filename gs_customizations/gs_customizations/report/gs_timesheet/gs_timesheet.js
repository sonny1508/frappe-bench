frappe.query_reports["GS Timesheet"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "summarize_by_activity",
			label: __("Summarize Hours by Activity"),
			fieldtype: "Check",
			default: 0,
		},
	],
};