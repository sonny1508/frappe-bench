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
            fieldname: "date_field",
            label: __("Date Filter On"),
            fieldtype: "Select",
            options: [
                { value: "completed_on", label: __("Completed On") },
                { value: "exp_start_date", label: __("Expected Start Date") }
            ],
            default: "completed_on",
            reqd: 1,
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
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: [
                { value: "Both", label: __("Both Completed & Closed") },
                { value: "Completed", label: __("Completed") },
                { value: "Closed", label: __("Closed") },
                { value: "All", label: __("All") }
            ],
            default: "Both",
            on_change: (report) => {
                // Unfinished tasks have no completed_on, so leaving the date range
                // pointed at it would filter out almost everything "All" exists to
                // show (135 unfinished tasks become 8). Switch the date field over.
                if (frappe.query_report.get_filter_value("status") === "All"
                    && frappe.query_report.get_filter_value("date_field") !== "exp_start_date") {

                    frappe.show_alert({
                        message: __("Date filter switched to Expected Start Date, so unfinished tasks are included."),
                        indicator: "blue"
                    }, 7);

                    // set_filter_value fires the date_field change, which refreshes
                    // for us - calling report.refresh() too would double-fetch.
                    frappe.query_report.set_filter_value("date_field", "exp_start_date");
                    return;
                }

                // Defining on_change replaces the default refresh (query_report.js),
                // so it has to be called by hand.
                report.refresh();
            }
        },
        {
            fieldname: "group_by_assignee",
            label: __("Group By Assignee"),
            fieldtype: "Check",
            default: 0,
            on_change: (report) => {
                report.refresh();
            }
        },
        {
            fieldname: "show_mds",
            label: __("Show MDs"),
            fieldtype: "Check",
            default: 0,
            on_change: () => {
                // Purely a display toggle - no server round-trip needed, and
                // deliberately no report.refresh() so it applies instantly.
                apply_md_column_visibility(frappe.query_report.datatable);
            }
        }
    ],
    
    onload: function(report) {
        size_filters_to_content(report);

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
    
    after_datatable_render: function(datatable) {
        // Runs on both the create and the refresh path, unlike
        // get_datatable_options which only fires when the datatable is first built.
        apply_md_column_visibility(datatable);
    },

    // Enable tree view when grouping
    tree: true,
    name_field: "custom_assign_to_employee",
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

// Query report filters render as bare inputs (page.js add_field passes
// only_input, so the label becomes the placeholder) and carry no width of their
// own - they fall back to an input's intrinsic ~180px each. With eight filters
// that overflows the row and orphans the last checkbox on a line by itself.
//
// So each one is sized to what it actually holds. Scoped to this report's page
// wrapper: .page-form is every report's filter bar, and an unscoped rule would
// resize filters on every report in the desk.
const FILTER_WIDTHS = {
    filter_based_on: 150,
    date_field: 165,
    month: 90,
    year: 90,
    start_date: 120,
    end_date: 120,
    status: 185,
};
const FILTER_STYLE_ID = "gs-task-sheet-filter-style";
const PAGE_SCOPE_CLASS = "gs-task-sheet-page";

function size_filters_to_content(report) {
    if (!report || !report.page || !report.page.wrapper) return;

    report.page.wrapper.addClass(PAGE_SCOPE_CLASS);

    if (document.getElementById(FILTER_STYLE_ID)) return;

    // data-fieldname sits on the control wrapper for some fieldtypes and on the
    // input itself for others, so the selector deliberately matches either.
    const rules = Object.keys(FILTER_WIDTHS).map((fieldname) =>
        `.${PAGE_SCOPE_CLASS} .page-form [data-fieldname="${fieldname}"]` +
        ` { width: ${FILTER_WIDTHS[fieldname]}px; min-width: 0; }`
    );

    const style = document.createElement("style");
    style.id = FILTER_STYLE_ID;
    style.textContent = rules.join("\n");
    document.head.appendChild(style);
}

// The two "In Days" columns are derived (hours / 8) and mostly just cost
// horizontal scroll, so they are hidden unless "Show MDs" is ticked.
//
// Hiding happens in the DOM rather than by dropping the columns in get_columns():
// the Excel export re-runs the report server-side and never looks at the page, so
// the export keeps all its columns whatever this toggle is set to.
const MD_COLUMNS = ["expected_time_days", "actual_time_days"];
const MD_STYLE_ID = "gs-task-sheet-md-style";
const MD_SCOPE_CLASS = "gs-task-sheet";

function apply_md_column_visibility(datatable) {
    const existing = document.getElementById(MD_STYLE_ID);
    if (existing) existing.remove();

    if (!datatable || !datatable.wrapper || !datatable.datamanager) return;

    // Every datatable in the desk uses .dt-cell--col-N, so the rules are scoped to
    // this report's own wrapper. An unscoped rule would keep hiding whatever
    // happened to be columns 14 and 15 on the next report the user opens.
    datatable.wrapper.classList.add(MD_SCOPE_CLASS);

    if (frappe.query_report.get_filter_value("show_mds")) return;

    const selectors = (datatable.datamanager.getColumns() || [])
        .filter((col) => MD_COLUMNS.includes(col.fieldname || col.id))
        .map((col) => `.${MD_SCOPE_CLASS} .dt-cell--col-${col.colIndex}`);

    if (!selectors.length) return;

    const style = document.createElement("style");
    style.id = MD_STYLE_ID;
    style.textContent = `${selectors.join(", ")} { display: none !important; }`;
    document.head.appendChild(style);
}

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