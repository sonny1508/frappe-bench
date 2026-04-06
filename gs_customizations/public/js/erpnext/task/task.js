$(document).on('app_ready', function() {
    frappe.router.on('change', function() {
        if (frappe.get_route()[0] === 'List' && frappe.get_route()[1] === 'Task') {
            overrideTaskListAssignments();
        }
    });
});

function overrideTaskListAssignments() {
    if (!window.cur_list) return;
    
    // Prevent multiple overrides
    if (cur_list._assignments_overridden) return;
    cur_list._assignments_overridden = true;
    
    // Override the get_meta_html method which renders the assignments
    const originalGetMetaHtml = cur_list.get_meta_html.bind(cur_list);
    
    cur_list.get_meta_html = function(doc) {
        let html = originalGetMetaHtml(doc);
        
        // Replace the assignments HTML if it exists
        if (doc._assign) {
            try {
                const assignees = JSON.parse(doc._assign);
                if (assignees && assignees.length > 0) {
                    // Generate names HTML
                    const namesHtml = assignees.map(email => {
                        const fullName = frappe.user.full_name(email);
                        return `<span style="font-size: 13px; color: var(--text-color);">${frappe.utils.escape_html(fullName)}</span>`;
                    }).join(', ');
                    
                    const assignmentsHtml = `
                        <div class="list-assignments d-flex align-items-center" style="justify-content: flex-start; width: 100px; min-width: 100px;">
                            <div class="avatar-group left">
                                ${namesHtml}
                            </div>
                        </div>
                    `;
                    
                    // Replace the avatar HTML with our names HTML
                    // The avatar HTML is wrapped in a div with class "list-assignments"
                    html = html.replace(/<div class="list-assignments[^>]*>[\s\S]*?<\/div>\s*<\/div>/i, assignmentsHtml);
                }
            } catch (e) {
                console.error('Error processing assignments:', e);
            }
        }
        
        return html;
    };
    
    // Refresh the list to apply changes
    cur_list.refresh();
}