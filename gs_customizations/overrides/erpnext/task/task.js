frappe.ui.form.on('Task', {
    status: function(frm) {
        update_completed_by_from_assigned_to(frm);
    },

    priority: function(frm) {
        set_color_by_priority(frm);
    },

    refresh: function(frm) {
        set_color_by_priority(frm);
        apply_task_field_permissions(frm);
    },
    
    onload: function(frm) {
        apply_task_field_permissions(frm);
    }
});

function update_completed_by_from_assigned_to(frm) {
    // When status changes to "Completed"
    if (frm.doc.status === "Completed") {
        if (!frm.doc.completed_by) {
            frappe.call({
                method: 'gs_customizations.overrides.erpnext.task.task.get_employee_from_todo',
                args: {
                    task_name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value('completed_by', r.message.name);
                        frm.set_value('custom_completed_by_employee', r.message.employee_name);
                    }
                }
            });
        }

        if (!frm.doc.completed_on) {
            frm.set_value('completed_on', frappe.datetime.now_datetime());
        }
    }
}

function set_color_by_priority(frm) {
    const priority_color_map = {
        "Urgent": "#FF4D4D",
        "High": "#FFA500",
        "Medium": "#318AD8",
        "Low": "#808080",
        "Support": "#28A745"
    };

    const color = priority_color_map[frm.doc.priority] || "#808080";

    if (frm.doc.color !== color) {
        frm.set_value("color", color).then(() => {
            if (!frm.is_new()) {
                frm.save();
            }
        });
    }
}

function apply_task_field_permissions(frm) {
    if (frm.is_new()) return;

    const managerRoles = frappe.boot.manager_roles || [];
    const userRoles = frappe.user_roles || [];
    const is_manager = managerRoles.some(role => userRoles.includes(role));
    
    if (is_manager) return;
    
    const allowed_fields = ['progress'];
    
    check_task_user_assignment(frm).then(is_assigned => {
        const meta = frappe.get_meta('Task');
        
        meta.fields.forEach(df => {
            if (['Section Break', 'Column Break', 'Tab Break', 'HTML'].includes(df.fieldtype)) {
                return;
            }
            
            const fieldname = df.fieldname;
            
            if (is_assigned && allowed_fields.includes(fieldname)) {
                frm.set_df_property(fieldname, 'read_only', 0);
            } else {
                frm.set_df_property(fieldname, 'read_only', 1);
            }
        });
        
        frm.refresh_fields();
    });
}

function check_task_user_assignment(frm) {
    return new Promise((resolve) => {
        frappe.call({
            method: 'frappe.client.get_list',
            args: {
                doctype: 'ToDo',
                filters: {
                    reference_type: 'Task',
                    reference_name: frm.doc.name,
                    status: ['!=', 'Cancelled']
                },
                fields: ['allocated_to']
            },
            async: false,
            callback: function(r) {
                if (r.message) {
                    const assigned_users = r.message.map(d => d.allocated_to);
                    resolve(assigned_users.includes(frappe.session.user));
                } else {
                    resolve(false);
                }
            }
        });
    });
}