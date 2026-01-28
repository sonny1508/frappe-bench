// monthly_attendance_sheet_override.js

// This runs after the page changes to the report
$(document).on('page-change', function() {
    // Check if we're on the Monthly Attendance Sheet report
    if (frappe.get_route()[0] === 'query-report' && 
        frappe.get_route()[1] === 'Monthly Attendance Sheet') {
        // Small delay to ensure report JS has loaded
        setTimeout(apply_attendance_formatter_override, 300);
    }
});

function apply_attendance_formatter_override() {
    // Make sure the report object exists
    if (!frappe.query_reports["Monthly Attendance Sheet"]) {
        // If not loaded yet, try again
        setTimeout(apply_attendance_formatter_override, 200);
        return;
    }

    console.log("Applying Monthly Attendance Sheet formatter override...");

    // Override the formatter
    frappe.query_reports["Monthly Attendance Sheet"].formatter = function (value, row, column, data, default_formatter) {
        // value = default_formatter(value, row, column, data);
        const summarized_view = frappe.query_report.get_filter_value("summarized_view");
        const group_by = frappe.query_report.get_filter_value("group_by");

        // Handle Float fields with custom number format for summarized view
        if (column.fieldtype === "Float" && value !== null && value !== undefined) {
            // Format as 0,000.00 (comma thousand separator, 2 decimals)
            let num = parseFloat(value);
            return num.toLocaleString('en-US', {
                minimumFractionDigits: 3,
                maximumFractionDigits: 3
            });
        }
        
        value = default_formatter(value, row, column, data);

        if (group_by && column.colIndex === 1) {
            value = "<strong>" + value + "</strong>";
        }

        if (!summarized_view) {
            if ((group_by && column.colIndex > 3) || (!group_by && column.colIndex > 2)) {
                // Original statuses
                if (value == "P" || value == "WFH")
                    value = "<span style='color:green'>" + value + "</span>";
                else if (value == "A") 
                    value = "<span style='color:red'>" + value + "</span>";
                else if (value == "LP" || value == "LU") 
                    value = "<span style='color:#318AD8'>" + value + "</span>";
                
                // Custom
                else if (value == "HLP/A" || value == "HLU/A")
                    value = "<span style='color:orange'>" + value + "</span>";
                else if (value == "HLP/P" || value == "HLU/P")
                    value = "<span style='color:#914EE3'>" + value + "</span>";
                
                // Default grey for anything else (H, WO, etc.)
                else 
                    value = "<span style='color:#878787'>" + value + "</span>";
            }
        }

        return value;
    };

    console.log("Formatter override applied successfully!");
}