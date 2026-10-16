frappe.query_reports["GS Timesheet"] = {
	filters: [
		{
			fieldname: "filter_based_on",
			label: __("Filter Based On"),
			fieldtype: "Select",
			options: ["Month", "Glenda Studio Interactive", "Date Range"],
			default: "Date Range",
			reqd: 1,
			on_change: (report) => {
				let by_range = frappe.query_report.get_filter_value("filter_based_on") == "Date Range";
				set_reqd_filter("month", !by_range);
				set_reqd_filter("year", !by_range);
				set_reqd_filter("start_date", by_range);
				set_reqd_filter("end_date", by_range);
				report.refresh();
			},
		},
		{
			fieldname: "month",
			label: __("Month"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Jan") },
				{ value: 2, label: __("Feb") },
				{ value: 3, label: __("Mar") },
				{ value: 4, label: __("Apr") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("June") },
				{ value: 7, label: __("July") },
				{ value: 8, label: __("Aug") },
				{ value: 9, label: __("Sep") },
				{ value: 10, label: __("Oct") },
				{ value: 11, label: __("Nov") },
				{ value: 12, label: __("Dec") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
			depends_on: "eval:doc.filter_based_on != 'Date Range'",
		},
		{
			fieldname: "year",
			label: __("Year"),
			fieldtype: "Select",
			options: year_options(),
			default: year_options()[0],
			depends_on: "eval:doc.filter_based_on != 'Date Range'",
		},
		{
			fieldname: "start_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.filter_based_on == 'Date Range'",
		},
		{
			fieldname: "end_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			depends_on: "eval:doc.filter_based_on == 'Date Range'",
		},
		{
			fieldname: "summarize_by_activity",
			label: __("Summarize Hours by Activity"),
			fieldtype: "Check",
			default: 0,
		},
	],
};

// The current year and the ten before it, newest first. Given to the Select up
// front so its default has a matching <option> when the filters are built.
function year_options() {
	let current_year = frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear();
	return Array.from({ length: 11 }, (_, i) => String(current_year - i));
}

function set_reqd_filter(fieldname, required) {
	let filter = frappe.query_report.get_filter(fieldname);
	if (filter) {
		filter.df.reqd = required;
		filter.refresh();
	}
}
