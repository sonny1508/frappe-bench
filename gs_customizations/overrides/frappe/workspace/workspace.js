frappe.ui.form.on('Workspace', {
    refresh: function(frm) {
        const isAllowed = frappe.user_roles.includes('System Manager') || 
                          frappe.session.user === 'Administrator';
        
        if (!isAllowed) {
            frm.disable_save();
            frm.page.hide_icon_group();
            frm.set_read_only(true);
            
            frm.dashboard.add_comment(
                __('Only System Manager can edit Workspaces.'),
                'yellow',
                true
            );
        }
    },
    
    before_load: function(frm) {
        const isAllowed = frappe.user_roles.includes('System Manager') || 
                          frappe.session.user === 'Administrator';
        
        if (frm.is_new() && !isAllowed) {
            frappe.throw(__('Only System Manager can create new Workspaces.'));
        }
    }
});

// Also hide the "New Workspace" button in list view
$(document).on('page-change', function() {
    const isAllowed = frappe.user_roles.includes('System Manager') || 
                      frappe.session.user === 'Administrator';
    
    if (!isAllowed && frappe.get_route()[0] === 'List' && frappe.get_route()[1] === 'Workspace') {
        setTimeout(() => {
            $('button[data-doctype="Workspace"].btn-primary-dark').hide();
        }, 100);
    }
});