# gs_customizations/permissions.py
import frappe
from gs_customizations.utils.network_access import is_restricted_network

# Roles allowed to see every employee's records (Task list views and reports)
MANAGER_ROLES = {
    "GS - Projects Manager",
    "System Manager"
}

def is_manager(user=None):
    """Check if the user holds any role that may see all employees' records"""
    user_roles = set(frappe.get_roles(user or frappe.session.user))
    return bool(user_roles & MANAGER_ROLES)

def validate_leave_access(employee, leave_application=None):
    """Allow an employee's leave numbers only to them, their approver, anyone who can read the
    Employee, or anyone who can read this Leave Application of theirs. Same rule as newer HRMS,
    which our leave overrides replace and so would not otherwise get."""
    from hrms.hr.doctype.leave_application.leave_application import get_leave_approver

    employee_user = frappe.db.get_value("Employee", employee, "user_id")

    if (
        frappe.session.user not in (employee_user, get_leave_approver(employee))
        and not frappe.has_permission("Employee", "read", employee)
        and not (
            leave_application
            and frappe.db.get_value("Leave Application", leave_application, "employee") == employee
            and frappe.has_permission("Leave Application", "read", leave_application)
        )
    ):
        frappe.throw("Not permitted", frappe.PermissionError)

def validate_timesheet_context_access(employee):
    """Allow an employee's absent days and leave hours, which the Timesheet form needs, only to
    them, managers, and anyone who can read the Employee."""
    if (
        frappe.db.get_value("Employee", employee, "user_id") != frappe.session.user
        and not is_manager()
        and not frappe.has_permission("Employee", "read", employee)
    ):
        frappe.throw("Not permitted", frappe.PermissionError)

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