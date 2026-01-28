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
    status_notifications = synology_config.get("status_notifications", {})
    
    # Check if this status should trigger notifications
    status_config = status_notifications.get(doc.status)
    if not status_config:
        return
    
    # Get assigned users
    assignees = get_task_assignees(doc.name)

    # Get project subscribers if project exists
    subscribers = []
    if doc.project:
        subscribers = get_project_subscribers(doc.project)

    # Determine who to notify based on status config
    recipients = get_recipients(status_config, assignees, subscribers)
    
    if not recipients:
        return

    # Build the message
    message = build_message(doc, assignees)
    
    # Collect webhook URLs for all recipients
    urls_to_notify = []
    for username in recipients:
        if username in employees:
            urls_to_notify.append(base_url + employees[username])
        else:
            frappe.logger().warning(f"No Synology Chat token found for user: {username}")
    
    # Send notifications
    send_notifications(urls_to_notify, message, doc.name)

    
def get_task_assignees(task_name):
    """Get list of usernames assigned to the task."""
    allocated_users = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Task",
            "reference_name": task_name,
            "status": "Open"
        },
        fields=["allocated_to"]
    )
    
    assignees = []
    for row in allocated_users:
        username = frappe.db.get_value("User", row.allocated_to, "username")
        if username:
            assignees.append(username)
    
    return assignees


def get_project_subscribers(project_name):
    """Get list of usernames subscribed to project notifications."""
    subscriber_rows = frappe.get_all(
        "Portal User",
        filters={
            "parent": project_name,
            "parenttype": "Project",
            "parentfield": "custom_notification"
        },
        fields=["user"]
    )
    
    subscribers = []
    for row in subscriber_rows:
        if row.user:
            username = frappe.db.get_value("User", row.user, "username")
            if username:
                subscribers.append(username)
    
    return subscribers


def get_recipients(status_config, assignees, subscribers):
    """Determine notification recipients based on status configuration."""
    recipients = set()
    
    # Add subscribers if configured
    if status_config.get("notify_subscribers", False):
        recipients.update(subscribers)
    
    # Add assignees if configured
    if status_config.get("notify_assignees", False):
        recipients.update(assignees)
    
    return list(recipients)


def build_message(doc, assignees):
    """Build the notification message."""
    message = f"Task `{doc.subject}` is now *{doc.status}*"
    
    if doc.project:
        project_name = frappe.db.get_value("Project", doc.project, "project_name")
        if project_name:
            message += f"\nProject: {project_name}"
    
    if doc.type:
        message += f"\nType: {doc.type}"
    
    if doc.exp_end_date:
        message += f"\nDue: {doc.exp_end_date}"

    if assignees:
        message += f"\nAssigned to: *{', '.join(assignees)}*"
        if doc.expected_time:
            message += f"\nExpected Time: {doc.expected_time} hours"
    
    return message


def send_notifications(urls, message, task_name):
    """Send notifications to all webhook URLs."""
    if not urls:
        return
    
    payload_data = json.dumps({"text": message})
    
    for webhook_url in urls:
        try:
            response = requests.post(
                webhook_url,
                data={"payload": payload_data},
                timeout=5
            )
            response.raise_for_status()
        except Exception as e:
            frappe.logger().error(f"Synology webhook failed for Task {task_name}: {e}")
    
    frappe.logger().info(f"Synology notifications sent for Task {task_name} ({len(urls)} recipients)")