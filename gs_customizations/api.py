import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_login_backgrounds(folder="login_backgrounds"):
    """Get list of background images from a folder in File Manager"""
    
    # Get files from the specified folder
    files = frappe.get_all(
        "File",
        filters={
            "folder": f"Home/{folder}",
            "is_folder": 0,
        },
        fields=["file_url"],
        order_by="creation asc"
    )
    
    # Filter for image files only
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    image_urls = [
        f["file_url"] for f in files 
        if f["file_url"].lower().endswith(image_extensions)
    ]
    
    return image_urls


@frappe.whitelist()
def get_timesheet_checkin_status(include_today=0):
    """Return the Timesheet Check-in status for the current user.

    Called by the client after saving a timesheet and by the end-of-day
    timer to refresh state without a full page reload.
    """
    from gs_customizations.utils.timesheet_checkin import get_checkin_status
    try:
        include_today = int(include_today)
    except (TypeError, ValueError):
        include_today = 0
    return get_checkin_status(frappe.session.user, include_today=bool(include_today))


@frappe.whitelist()
def create_timesheet_for_date(date):
    """Create a Draft Timesheet for the current user's employee on the given
    date, pre-populated with one empty time_log row. Returns the new name.
    """
    from gs_customizations.utils.timesheet_checkin import find_existing_timesheet
    from frappe.utils import get_datetime

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user, "status": "Active"},
        ["name", "company"],
        as_dict=True,
    )
    if not employee:
        frappe.throw(_("No active Employee linked to your user."))

    # Reuse existing draft if any
    existing = find_existing_timesheet(employee.name, date)
    if existing:
        return existing

    start_dt = get_datetime(f"{date} 09:00:00")
    end_dt = get_datetime(f"{date} 10:00:00")

    ts = frappe.get_doc({
        "doctype": "Timesheet",
        "employee": employee.name,
        "company": employee.company,
        "time_logs": [
            {
                "from_time": start_dt,
                "to_time": end_dt,
                "hours": 1,
            }
        ],
    })
    ts.insert(ignore_permissions=False)
    return ts.name