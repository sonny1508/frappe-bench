frappe.query_reports["GS Task Pool"] = {
    // No period filter: this always shows the tasks waiting to be assigned now.
    filters: [
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project",
            get_query: () => ({ filters: { status: "Open" } }),
        },
    ],

    onload: function (report) {
        report.page.add_inner_button(__("Workload Sheet"), () => {
            frappe.set_route("query-report", "GS Workload Sheet");
        });
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        if (data && data.is_overdue && ["exp_end_date", "days_left"].includes(column.fieldname)) {
            value = `<span class="text-danger">${value}</span>`;
        }

        return value;
    },
};
