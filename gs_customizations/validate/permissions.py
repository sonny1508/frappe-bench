# gs_customizations/permissions.py
import frappe
from gs_customizations.utils.network_access import is_restricted_network

def has_project_permission(doc, ptype=None, user=None):
    """
    Block all permission types (read, write, create, delete) from restricted network.
    Return False to deny, None to fall through to default permissions.
    """
    if is_restricted_network():
        return False
    return None

def project_query_conditions(user):
    """
    Filter list view results. 
    Return '1=0' to show zero records, '' for no restriction.
    """
    if is_restricted_network():
        return "1=0"
    return ""

def block_assign(doc, method):
    user_roles = frappe.get_roles(frappe.session.user)
    manager_roles = frappe.conf.get("manager_roles")

    if not any(role in user_roles for role in manager_roles):
        frappe.throw(
            "Only Managers can assign tasks.",
            frappe.PermissionError
        )