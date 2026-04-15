import frappe

def boot_session(bootinfo):
    bootinfo.manager_roles = frappe.conf.get("manager_roles")

    # Timesheet Check-in enforcement data.
    # Wrapped in try/except so a bug here can never break login.
    try:
        from gs_customizations.utils.timesheet_checkin import get_checkin_status
        bootinfo.timesheet_checkin = get_checkin_status(frappe.session.user)
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "gs_customizations: timesheet_checkin boot failed",
        )
        bootinfo.timesheet_checkin = {
            "enforce": False,
            "missing_days": [],
            "employee": None,
            "employee_name": None,
            "end_working_hour": None,
            "include_today": False,
        }

    # import frappe.desk.doctype.kanban_board.kanban_board as original_kb
    # from gs_customizations.overrides.frappe.kanban_board.kanban_board import get_order_for_column

    # if getattr(original_kb.get_order_for_column, "_is_patched", False):
    #     return
    
    # get_order_for_column._is_patched = True
    # original_kb.get_order_for_column = get_order_for_column