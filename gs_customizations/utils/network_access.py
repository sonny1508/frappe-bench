import frappe

RESTRICTED_SERVER_IPS = ['192.168.3.206']

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
	
	session_roles = frappe.get_roles(frappe.session.user)
	manager_roles = frappe.conf.get("manager_roles")
	
	server_addr = frappe.request.headers.get('X-Server-Addr', '')
	
	for ip in RESTRICTED_SERVER_IPS:
		if ip in server_addr:
			if any(role in manager_roles for role in session_roles):
				return False
			else:
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