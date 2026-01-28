import frappe

def boot_session(bootinfo):
    bootinfo.manager_roles = frappe.conf.get("manager_roles")

    # import frappe.desk.doctype.kanban_board.kanban_board as original_kb
    # from gs_customizations.overrides.frappe.kanban_board.kanban_board import get_order_for_column

    # if getattr(original_kb.get_order_for_column, "_is_patched", False):
    #     return
    
    # get_order_for_column._is_patched = True
    # original_kb.get_order_for_column = get_order_for_column