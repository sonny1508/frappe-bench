frappe.ui.form.on("Timesheet Detail", {
    activity_type: function (frm, cdt, cdn) {
        toggle_free_fields(frm, cdt, cdn);
    },
    form_render: function (frm, cdt, cdn) {
        toggle_free_fields(frm, cdt, cdn);
    },
});

function toggle_free_fields(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    var is_free = row.activity_type === "Free";
    var fields = ["project", "project_name", "task", "custom_task_name", "custom_task_type"];
    fields.forEach(function (field) {
        frappe.meta.get_docfield("Timesheet Detail", field, cdn).read_only = is_free ? 1 : 0;
    });
    frm.refresh_field("time_logs");
}