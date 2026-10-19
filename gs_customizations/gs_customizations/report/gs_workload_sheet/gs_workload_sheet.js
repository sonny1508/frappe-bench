// Columns whose menu sorts the employees by their totals. Every other column has
// its menu turned off in get_columns(): the datatable's own sort orders every row
// on its own, which pulls tasks away from their employee.
const SORT_COLUMNS = ["active_count", "submitted_count", "overdue_count", "expected_time", "utilization"];

// Whether every employee's tasks are shown. The report always opens collapsed
// (initial_depth), so this resets on each refresh.
let tasks_expanded = false;
let $tasks_toggle = null;

frappe.query_reports["GS Workload Sheet"] = {
    // No period filter, unlike the other GS reports: this always shows the
    // current assignments.
    filters: [
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
        },
        {
            fieldname: "grade",
            label: __("Grade"),
            fieldtype: "Link",
            options: "Employee Grade",
        },
        {
            // Picks out the artists with room for more work. "1" keeps only
            // those with no active task at all.
            fieldname: "active_below",
            label: __("Active Tasks Fewer Than"),
            fieldtype: "Select",
            options: ["", "1", "2", "3", "4", "5"],
        },
    ],

    tree: true,
    name_field: "id",
    parent_field: "parent_id",
    // Opens on the list of people; expand an employee to see their tasks.
    initial_depth: 0,

    onload: function (report) {
        $tasks_toggle = report.page.add_inner_button(__("Expand All"), () => {
            set_tasks_expanded(report, !tasks_expanded);
        });

        report.page.add_inner_button(__("Task Pool"), () => {
            frappe.set_route("query-report", "GS Task Pool");
        });
    },

    after_datatable_render: function (datatable) {
        sort_by_employee(datatable);
        update_tasks_toggle(false);
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        const is_late =
            (column.fieldname === "exp_end_date" && data.is_overdue) ||
            (column.fieldname === "overdue_count" && data.overdue_count > 0);

        if (is_late) {
            value = `<span class="text-danger">${value}</span>`;
        }

        // Employee rows in bold, so the people stand out from their tasks.
        if (data.indent === 0) {
            value = `<b>${value}</b>`;
        }

        return value;
    },
};

function set_tasks_expanded(report, expanded) {
    if (!report.datatable) return;

    // Through the report, when it has its tree footer, so the footer's own
    // Expand All / Collapse All buttons stay in step with this one.
    if (report.$tree_footer) {
        expanded ? report.expand_all_rows() : report.collapse_all_rows();
    } else if (expanded) {
        report.datatable.rowmanager.expandAllNodes();
    } else {
        report.datatable.rowmanager.collapseAllNodes();
    }

    update_tasks_toggle(expanded);
}

function update_tasks_toggle(expanded) {
    tasks_expanded = expanded;
    if ($tasks_toggle) {
        $tasks_toggle.text(expanded ? __("Collapse All") : __("Expand All"));
    }
}

// Sort employees as whole groups: an employee row moves together with its
// tasks, which keep their own order (soonest deadline first) underneath.
//
// Replaces the datatable's _sortRows on this report's instance only. It is an
// internal method of frappe-datatable, so check this still works after a Frappe
// upgrade. The instance survives report refreshes, hence the guard.
function sort_by_employee(datatable) {
    if (datatable.gs_sort_by_employee) return;
    datatable.gs_sort_by_employee = true;

    datatable.datamanager._sortRows = function (colIndex, sortOrder) {
        const groups = [];
        this.rows.forEach((row, index) => {
            if (row.meta.indent === 0 || !groups.length) {
                groups.push([index]);
            } else {
                groups[groups.length - 1].push(index);
            }
        });

        const column = this.getColumn(colIndex);
        if (sortOrder !== "none" && SORT_COLUMNS.includes(column.id)) {
            // A blank total (an employee with no tasks has no utilization)
            // counts as the lowest value.
            const total = (group) => {
                const content = this.getCell(colIndex, group[0]).content;
                return content == null || content === "" ? -Infinity : Number(content);
            };
            const direction = sortOrder === "asc" ? 1 : -1;

            // Array sort is stable, so ties keep the department / name order.
            groups.sort((a, b) => {
                const [x, y] = [total(a), total(b)];
                return x === y ? 0 : (x < y ? -1 : 1) * direction;
            });
        }

        this.rowViewOrder = groups.flat();
        this.currentSort = { colIndex, sortOrder };
    };

    // Sorting redraws every row, open or not. Show again only the tasks of
    // employees that were expanded.
    datatable.on("onSortColumn", () => {
        const rows_to_show = [];
        let showing_children = true;

        datatable.datamanager.getRows().forEach((row) => {
            if (row.meta.indent === 0) {
                rows_to_show.push(row.meta.rowIndex);
                showing_children = !row.meta.isTreeNodeClose;
            } else if (showing_children) {
                rows_to_show.push(row.meta.rowIndex);
            }
        });

        datatable.rowmanager.showRows(rows_to_show);
    });
}
