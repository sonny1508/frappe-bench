import frappe
import requests
import json

def schedule_daily_timesheet():
    synology_config = frappe.conf.get("synology_chat")

    if not synology_config:
        frappe.logger().warning("Synology Chat configuration not found in site_config.json")
        return

    base_url = synology_config.get("base_url")
    # all_employees = synology_config.get("employees", {})
    # test_only = ["sonny.nguyen.01"]

    # employees = {k: v for k, v in all_employees.items() if k in test_only}
    employees = synology_config.get("employees", {})
    excluded = synology_config.get("excluded_employees", [])

    for employee_id, token in employees.items():
        if employee_id in excluded:
            continue
        try:
            message = build_message(employee_id)
            send_synology_message(base_url, token, message)
        except Exception as e:
            frappe.logger().error(
                f"Synology Chat failed for {employee_id}: {e}",
                "Synology Chat Error"
            )


def build_message(employee_id):
    # Customize this to pull timesheet data, reminders, etc.
    return f"Hi `{employee_id}`, this is your daily timesheet reminder. Please update your timesheet at the end of the day."


def send_synology_message(base_url, token, message):
    url = f"{base_url}{token}"
    payload = json.dumps({"text": message})

    response = requests.post(
        url,
        data={"payload": payload},
        timeout=5
    )
    response.raise_for_status()