import frappe
from frappe.desk.desktop import get_workspace_sidebar_items as original_get_workspace_sidebar_items
from gs_customizations.utils.network_access import is_restricted_network

HIDDEN_WORKSPACES = 'Projects'  # Check exact name in your system

@frappe.whitelist()
def get_workspace_sidebar_items():
    """Override to hide Projects workspace on restricted network"""
    result = original_get_workspace_sidebar_items()
    
    if is_restricted_network():
        if isinstance(result, dict) and 'pages' in result:
            result['pages'] = [
                page for page in result['pages']
                if page.get('name') not in HIDDEN_WORKSPACES
                and page.get('title') not in HIDDEN_WORKSPACES
            ]
    
    return result