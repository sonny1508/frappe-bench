frappe.query_reports["GS Task Sheet"] = {
    "filters": [
        {
            fieldname: "filter_based_on",
            label: __("Filter Based On"),
            fieldtype: "Select",
            options: ["Month", "Date Range"],
            default: "Month",
            reqd: 1,
            on_change: (report) => {
                let filter_based_on = frappe.query_report.get_filter_value("filter_based_on");
                if (filter_based_on == "Month") {
                    set_reqd_filter("month", true);
                    set_reqd_filter("year", true);
                    set_reqd_filter("start_date", false);
                    set_reqd_filter("end_date", false);
                }
                if (filter_based_on == "Date Range") {
                    set_reqd_filter("month", false);
                    set_reqd_filter("year", false);
                    set_reqd_filter("start_date", true);
                    set_reqd_filter("end_date", true);
                }
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
            depends_on: "eval:doc.filter_based_on == 'Month'",
        },
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Select",
            depends_on: "eval:doc.filter_based_on == 'Month'",
            default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear(),
        },
        {
            fieldname: "start_date",
            label: __("Start Date"),
            fieldtype: "Date",
            depends_on: "eval:doc.filter_based_on == 'Date Range'",
            on_change: validate_date_range,
        },
        {
            fieldname: "end_date",
            label: __("End Date"),
            fieldtype: "Date",
            depends_on: "eval:doc.filter_based_on == 'Date Range'",
            on_change: validate_date_range,
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: [
                { value: "Both", label: __("Both Completed & Closed") },
                { value: "Completed", label: __("Completed") },
                { value: "Closed", label: __("Closed") }
            ],
            default: "Both"
        },
        {
            fieldname: "group_by_employee",
            label: __("Group By Employee"),
            fieldtype: "Check",
            default: 0,
            on_change: (report) => {
                report.refresh();
            }
        }
    ],
    
    onload: function(report) {
        // Populate year options
        let year_filter = report.filters.find(f => f.df.fieldname === "year");
        if (year_filter) {
            let current_year = frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear();
            let years = [];
            for (let i = current_year; i >= current_year - 10; i--) {
                years.push({ value: i, label: i.toString() });
            }
            year_filter.df.options = years;
            year_filter.refresh();
        }
    },
    
    // Enable tree view when grouping
    tree: true,
    name_field: "custom_completed_by_employee",
    parent_field: "parent_employee",
    initial_depth: 1,
    
    formatter: function(value, row, column, data, default_formatter) {
        // Handle Float fields with custom number format (3 decimal places)
        if (column.fieldtype === "Float" && data && column.fieldname in data) {
            let raw_value = data[column.fieldname];
            if (raw_value !== null && raw_value !== undefined && raw_value !== "") {
                let num = parseFloat(raw_value);
                if (!isNaN(num)) {
                    value = num.toLocaleString('en-US', {
                        minimumFractionDigits: 3,
                        maximumFractionDigits: 3
                    });
                }
            }
        } else {
            value = default_formatter(value, row, column, data);
        }
        
        // Style parent rows (summary rows) - make entire row bold
        if (data && data.indent === 0) {
            value = `<b>${value}</b>`;
        }
        
        return value;
    }
};

function set_reqd_filter(fieldname, required) {
    let filter = frappe.query_report.get_filter(fieldname);
    if (filter) {
        filter.df.reqd = required;
        filter.refresh();
    }
}

function validate_date_range() {
    let start_date = frappe.query_report.get_filter_value("start_date");
    let end_date = frappe.query_report.get_filter_value("end_date");
    
    if (start_date && end_date && start_date > end_date) {
        frappe.msgprint(__("Start Date cannot be after End Date"));
        frappe.query_report.set_filter_value("start_date", "");
    }
}