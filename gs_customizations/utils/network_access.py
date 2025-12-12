import frappe

RESTRICTED_SERVER_IPS = ['192.168.3.207']

RESTRICTED_DOCTYPES = [
    'Project',
    'Task',
    'Project Type',
    'Project Template',
    'Project Template Task',
    'Timesheet',
    'Activity Type',
    'Activity Cost'
]

BLOCKED_ROUTES = [
    '/app/project',
    '/app/task',
    '/app/timesheet',
    '/app/projects',  # workspace
]

def is_restricted_network():
    """Check if request came through restricted network interface"""
    if not frappe.request:
        return False
    
    server_addr = frappe.request.headers.get('X-Server-Addr', '')
    
    # Debug: log what we're receiving (remove after testing)
    # frappe.logger().debug(f"X-Server-Addr: {server_addr}")
    
    for ip in RESTRICTED_SERVER_IPS:
        if ip in server_addr:
            return True
    
    return False

def check_doctype_access(doc, method=None):
    """Deny access to restricted doctypes from external network"""
    if is_restricted_network():
        frappe.throw(
            f"Access to {doc.doctype} is not available from this network.",
            frappe.PermissionError
        )

def block_restricted_routes():
    """Block direct URL access to project-related pages"""
    if not frappe.request or not is_restricted_network():
        return
    
    path = frappe.request.path or ''
    
    for blocked in BLOCKED_ROUTES:
        if path.startswith(blocked):
            frappe.throw(
                "This page is not accessible from this network.",
                frappe.PermissionError
            )