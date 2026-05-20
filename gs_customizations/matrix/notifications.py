"""
Matrix notification hooks for Task status changes and ToDo assignments.

Mirrors the Synology notification logic (synology/synology.py) but delivers
messages via Matrix DM rooms. Both systems run side-by-side — Synology hooks
stay wired independently until the admin disables them.

The status notification config is kept in code (same structure as the Synology
site_config), not in the DocType.
"""

import frappe

from gs_customizations.matrix.bot import get_matrix_user_id, send_server_notice

# ---------------------------------------------------------------------------
# Status notification config — mirrors the Synology site_config structure.
# Defines which task statuses trigger notifications and to whom.
# ---------------------------------------------------------------------------

STATUS_NOTIFICATIONS = {
	"Open":            {"notify_assignees": True,  "notify_subscribers": False},
	"Working":         {"notify_assignees": False, "notify_subscribers": False},
	"QA Pending":      {"notify_assignees": False, "notify_subscribers": True},
	"QA Reviewing":    {"notify_assignees": False, "notify_subscribers": False},
	"QA Feedback":     {"notify_assignees": True,  "notify_subscribers": False},
	"QA Approved":     {"notify_assignees": True,  "notify_subscribers": False},
	"Client Feedback": {"notify_assignees": True,  "notify_subscribers": False},
	"Completed":       {"notify_assignees": True,  "notify_subscribers": False},
}


# ---------------------------------------------------------------------------
# Hook functions
# ---------------------------------------------------------------------------

def notify_todo_insert(doc, method):
	"""Send Matrix notification when a task is assigned via ToDo creation.

	Only triggers for newly created assignments (status = Open).
	Hooked to: ToDo → after_insert
	"""
	if doc.reference_type != "Task" or doc.status != "Open":
		return

	if not _is_matrix_enabled():
		return

	status_config = STATUS_NOTIFICATIONS.get("Open")
	if not status_config or not status_config.get("notify_assignees", False):
		return

	task = frappe.get_doc("Task", doc.reference_name)

	assignees = get_task_assignees(task.name)

	subscribers = []
	if task.project:
		subscribers = get_project_subscribers(task.project)

	recipients = get_recipients(status_config, assignees, subscribers)
	if not recipients:
		return

	message = build_message(task, assignees)
	_send_to_recipients(recipients, message)


def notify_task_update(doc, method):
	"""Send Matrix notification when Task status changes.

	Hooked to: Task → on_update
	"""
	if not _is_matrix_enabled():
		return

	# Skip if status hasn't actually changed
	previous = doc.get_doc_before_save()
	if previous and previous.status == doc.status:
		return

	status_config = STATUS_NOTIFICATIONS.get(doc.status)
	if not status_config:
		return

	assignees = get_task_assignees(doc.name)

	subscribers = []
	if doc.project:
		subscribers = get_project_subscribers(doc.project)

	recipients = get_recipients(status_config, assignees, subscribers)
	if not recipients:
		return

	message = build_message(doc, assignees)
	_send_to_recipients(recipients, message)


# ---------------------------------------------------------------------------
# Helpers — same logic as synology.py, returning usernames
# ---------------------------------------------------------------------------

def get_task_assignees(task_name):
	"""Get list of usernames assigned to the task."""
	allocated_users = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": task_name,
			"status": "Open",
		},
		fields=["allocated_to"],
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
			"parentfield": "custom_notification",
		},
		fields=["user"],
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

	if status_config.get("notify_subscribers", False):
		recipients.update(subscribers)

	if status_config.get("notify_assignees", False):
		recipients.update(assignees)

	return list(recipients)


def build_message(doc, assignees):
	"""Build the notification message."""
	message = f"Task: ===== *{doc.subject}* is now *{doc.status}* 🎉"

	if doc.project:
		project_name = frappe.db.get_value("Project", doc.project, "project_name")
		if project_name:
			message += f"\nProject: ==== {project_name}"

	if doc.type:
		message += f"\nType: ====== {doc.type}"

	if doc.exp_end_date:
		message += f"\nDue: ======== {doc.exp_end_date}"

	if assignees:
		message += f"\nAssigned: === *{', '.join(assignees)}*"
		if doc.expected_time:
			message += f"\nExpected Time: {doc.expected_time} hours"

	return message


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_matrix_enabled():
	"""Check if Matrix integration is enabled without throwing."""
	try:
		settings = frappe.get_single("Matrix Settings")
		return settings.enabled
	except Exception:
		return False


def _is_matrix_enabled_for_user(username):
	"""Check if Matrix notifications are enabled for a specific user.

	Looks up the Employee linked to the User with the given username and
	checks the custom_enable_matrix_notifications flag. Returns False if
	the flag is off or the employee/user can't be found.
	"""
	try:
		user_email = frappe.db.get_value("User", {"username": username}, "name")
		if not user_email:
			return False
		enabled = frappe.db.get_value("Employee", {"user_id": user_email}, "custom_enable_matrix_notifications")
		return bool(enabled)
	except Exception:
		return False


def _send_to_recipients(usernames, message):
	"""Send a server notice to each recipient.

	Uses the Synapse Server Notices API — Synapse auto-creates a notice room
	per user, so no room provisioning or lookup is needed for DM notifications.

	Only sends to employees who have custom_enable_matrix_notifications enabled.
	Silently skips failures so one user's error doesn't block others.
	"""
	for username in usernames:
		try:
			if not _is_matrix_enabled_for_user(username):
				continue
			matrix_user_id = get_matrix_user_id(username)
			send_server_notice(matrix_user_id, message)
		except Exception as e:
			frappe.logger("matrix").error(
				f"Failed to send server notice to {username}: {e}"
			)
