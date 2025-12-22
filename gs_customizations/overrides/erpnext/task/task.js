frappe.ui.form.on('Task', {
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
    
    const is_projects_manager = frappe.user_roles.includes('Projects Manager');
    const is_projects_user = frappe.user_roles.includes('GS - Projects User');
    
    if (is_projects_manager) return;
    if (!is_projects_user) return;
    
    const allowed_fields = ['status', 'progress'];
    
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
        
        // if (!is_assigned) {
        //     frm.set_intro(
        //         __('You are not assigned to this task. All fields are read-only.'),
        //         'yellow'
        //     );
        // } else {
        //     frm.set_intro(
        //         __('You can only modify Status and Progress fields.'),
        //         'blue'
        //     );
        // }
        
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