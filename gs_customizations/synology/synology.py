import frappe
import requests
import json

def notify_task_update(doc, method):
    """
    Send Synology Chat notifications when Task status changes.
    Configuration is read from site_config.json under 'synology_chat' key.
    """

    synology_config = frappe.conf.get("synology_chat")
    
    if not synology_config:
        frappe.logger().warning("Synology Chat configuration not found in site_config.json")
        return
    
    base_url = synology_config.get("base_url")
    employees = synology_config.get("employees", {})
    groups = synology_config.get("groups", {})
    status_notifications = synology_config.get("status_notifications", {})
    
    # Check if this status should trigger notifications
    status_config = status_notifications.get(doc.status)
    if not status_config:
        return  # This status doesn't require notifications
    
    # Build the message
    message = f"Task `{doc.subject}` is now {doc.status}"
    
    if doc.project:
        project_name = frappe.db.get_value("Project", doc.project, "project_name")
        message += f"\nProject: {project_name}"
    
    # Get assigned users
    allocated_users = frappe.get_all(
        "ToDo",
        filters={"reference_type": "Task", "reference_name": doc.name},
        fields=["allocated_to"]
    )
    
    employee_names = []
    if allocated_users:
        for row in allocated_users:
            full_name = frappe.db.get_value("User", row.allocated_to, "full_name")
            if full_name:
                employee_names.append(full_name)
        
        if employee_names:
            message += f"\nAssigned to: *{', '.join(employee_names)}*"
    
    if doc.type:
        message += f"\nType: {doc.type}"

    if doc.exp_end_date:
        message += f"\nDue: {doc.exp_end_date}"
    
    # Collect all webhook URLs to notify
    urls_to_notify = []
    
    # Notify assigned users if configured
    if status_config.get("notify_assigned", False):
        for name in employee_names:
            if name in employees:
                urls_to_notify.append(base_url + employees[name])
            else:
                frappe.logger().warning(f"Can't find {name}'s Synology Chat token in config")
    
    # Notify groups if configured
    # for group_name in status_config.get("notify_groups", []):
    #     if group_name in groups:
    #         urls_to_notify.append(base_url + groups[group_name])
    #     else:
    #         frappe.logger().warning(f"Can't find group '{group_name}' in Synology Chat config")
    
    # Send notifications
    payload_data = json.dumps({"text": message})
    
    for webhook_url in urls_to_notify:
        try:
            response = requests.post(
                webhook_url,
                data={"payload": payload_data},
                timeout=5
            )
            response.raise_for_status()
        except Exception as e:
            frappe.logger().error(f"Synology webhook failed for Task {doc.name}: {e}")
    
    if urls_to_notify:
        frappe.logger().info(f"Synology notifications sent for Task {doc.name} ({len(urls_to_notify)} recipients)")