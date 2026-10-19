frappe.ui.form.on('Task', {
    status: function(frm) {
        update_completed_by_from_assigned_to(frm);
        apply_overdue_priority_rules(frm);
    },

    priority: function(frm) {
        set_color_by_priority(frm);
    },

    refresh: function(frm) {
        set_color_by_priority(frm);
        apply_overdue_priority_rules(frm);
    },
    
    onload: function(frm) {
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

// The Overdue priority is set by the server once a task passes its Expected End
// Date, and stays until the date is moved later (overdue_priority.py). The form
// only mirrors that: Overdue is left out of the dropdown, and the field is
// locked while an unfinished task is Overdue. The server enforces both anyway.
const OVERDUE_PRIORITY = "Overdue";
const FINISHED_STATUSES = ["Completed", "Closed", "Cancelled", "Template"];

function apply_overdue_priority_rules(frm) {
    const meta_df = frappe.get_meta("Task").fields.find((df) => df.fieldname === "priority");
    if (!meta_df) return;

    const is_overdue = frm.doc.priority === OVERDUE_PRIORITY;
    const locked = is_overdue && !FINISHED_STATUSES.includes(frm.doc.status);

    // Overdue stays in the list while it is the current value, or the field
    // would show blank.
    const options = (meta_df.options || "")
        .split("\n")
        .filter((option) => is_overdue || option !== OVERDUE_PRIORITY);

    frm.set_df_property("priority", "options", options);
    frm.set_df_property("priority", "read_only", locked ? 1 : meta_df.read_only);
    frm.set_df_property(
        "priority",
        "description",
        locked
            ? __("Set automatically: this task is past its Expected End Date. Move the date later to change it.")
            : meta_df.description || ""
    );
}

function set_color_by_priority(frm) {
    // Keep in step with the same map in task.py.
    const priority_color_map = {
        "Overdue": "#8B0000",
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

// function apply_task_field_permissions(frm) {
//     if (frm.is_new()) return;

//     const managerRoles = frappe.boot.manager_roles || [];
//     const userRoles = frappe.user_roles || [];
//     const is_manager = managerRoles.some(role => userRoles.includes(role));
    
//     if (is_manager) return;
    
//     const allowed_fields = ['progress'];
    
//     check_task_user_assignment(frm).then(is_assigned => {
//         const meta = frappe.get_meta('Task');
        
//         meta.fields.forEach(df => {
//             if (['Section Break', 'Column Break', 'Tab Break', 'HTML'].includes(df.fieldtype)) {
//                 return;
//             }
            
//             const fieldname = df.fieldname;
            
//             if (is_assigned && allowed_fields.includes(fieldname)) {
//                 frm.set_df_property(fieldname, 'read_only', 0);
//             } else {
//                 frm.set_df_property(fieldname, 'read_only', 1);
//             }
//         });
        
//         frm.refresh_fields();
//     });
// }

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