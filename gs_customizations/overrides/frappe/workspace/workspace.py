import frappe
from frappe import _

def validate_workspace_permission(doc, method):
    """
    Prevent non-System Manager users from creating or modifying Workspaces.
    """
    if frappe.session.user == "Administrator":
        return
    
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(
            _("Only users with System Manager role can create or modify Workspaces."),
            frappe.PermissionError
        )

def validate_workspace_delete(doc, method):
    """
    Prevent non-System Manager users from deleting Workspaces.
    """
    if frappe.session.user == "Administrator":
        return
    
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(
            _("Only users with System Manager role can delete Workspaces."),
            frappe.PermissionError
        )