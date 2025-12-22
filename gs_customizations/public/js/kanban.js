frappe.after_ajax(() => {
    if (frappe.views?.KanbanView?.prototype) {
        const original = frappe.views.KanbanView.prototype.setup_drag;

        frappe.views.KanbanView.prototype.setup_drag = function () {
            // Do nothing -> disables drag entirely
            return;
        };
    }
});