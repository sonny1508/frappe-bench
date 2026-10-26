"""
Matrix notification hooks for Task status changes and ToDo assignments.

Mirrors the Synology notification logic (synology/synology.py) but delivers
messages via Matrix DM rooms. Both systems run side-by-side — Synology hooks
stay wired independently until the admin disables them.

The status notification config is kept in code (same structure as the Synology
site_config), not in the DocType.

Status changes are not sent from inside the Task save. They wait in Matrix
Pending Notification until the status has held for NOTIFY_DELAY_MINUTES - see
notify_task_update().
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from gs_customizations.matrix.bot import get_matrix_user_id, send_server_notice

# A status change is announced only once it has held this long, so a card
# dragged into the wrong column and straight back sends nothing.
NOTIFY_DELAY_MINUTES = 5

PENDING_DOCTYPE = "Matrix Pending Notification"

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
	"""Hold a Task status change for NOTIFY_DELAY_MINUTES before announcing it.

	Hooked to: Task → on_update. send_due_task_notifications() does the sending.

	Keeps the name it had when it sent straight away. Frappe caches hooks.py in
	Redis while new worker processes import this module from disk, so renaming a
	hooked function breaks every save until the cache is cleared.

	Sending used to happen right here, inside the save: one HTTPS call to
	Synapse per recipient, while the drag-and-drop waited behind a frozen screen
	and the save's transaction held its row locks. Now the save only writes one
	row, in its own transaction, so a save that fails takes the row with it.

	One row per task, named after it. A further change restarts the hold but
	keeps `from_status`, the status the task had before the first change. If the
	task is back to that status when the hold runs out, nothing is sent: that
	was a misclick undone. Otherwise the message describes the task as it is at
	that moment, so only the status it settled on is announced.

	Never raises: a notice that cannot be queued must not fail the status change.
	"""
	try:
		if not _is_matrix_enabled():
			return

		previous = doc.get_doc_before_save()
		# A new task has nobody assigned yet. Its assignees hear about it from
		# notify_todo_insert when they are assigned.
		if not previous or previous.status == doc.status:
			return

		# Until `bench migrate` has created the table, keep sending straight away.
		if not frappe.db.table_exists(PENDING_DOCTYPE):
			_announce_task_status(doc.name, previous.status)
			return

		send_after = add_to_date(now_datetime(), minutes=NOTIFY_DELAY_MINUTES)

		if frappe.db.exists(PENDING_DOCTYPE, doc.name):
			frappe.db.set_value(
				PENDING_DOCTYPE,
				doc.name,
				{"to_status": doc.status, "send_after": send_after},
				update_modified=False,
			)
			return

		# Nothing is held yet, and this status tells nobody.
		if not any(STATUS_NOTIFICATIONS.get(doc.status, {}).values()):
			return

		frappe.get_doc({
			"doctype": PENDING_DOCTYPE,
			"task": doc.name,
			"from_status": previous.status,
			"to_status": doc.status,
			"send_after": send_after,
		}).insert(ignore_permissions=True)

	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"gs_customizations: queueing Matrix notice for Task {0} failed".format(doc.name),
			defer_insert=True,
		)


def send_due_task_notifications():
	"""Announce the held Task status changes whose hold has run out.

	Scheduled every minute (hooks.py), so a notice goes out between
	NOTIFY_DELAY_MINUTES and one minute more after the last change.

	Each row is deleted and committed before its notice is sent. A failure while
	sending then loses that one notice, as an inline send always did, rather than
	repeating it every minute.
	"""
	due = frappe.get_all(
		PENDING_DOCTYPE,
		filters={"send_after": ["<=", now_datetime()]},
		pluck="name",
		order_by="send_after asc",
	)

	for name in due:
		# Locking read: a save may have restarted this hold since the list above.
		pending = frappe.db.get_value(
			PENDING_DOCTYPE,
			name,
			["task", "from_status", "send_after"],
			as_dict=True,
			for_update=True,
		)
		if not pending or pending.send_after > now_datetime():
			frappe.db.commit()
			continue

		frappe.db.delete(PENDING_DOCTYPE, {"name": name})
		frappe.db.commit()

		try:
			_announce_task_status(pending.task, pending.from_status)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				"gs_customizations: Matrix notice for Task {0} failed".format(pending.task),
			)
			frappe.db.commit()


def _announce_task_status(task_name, from_status):
	"""Send the notice for a Task's current status, as STATUS_NOTIFICATIONS says."""
	# Checked here as well as when queueing: the integration may have been
	# switched off while the notice was held.
	if not _is_matrix_enabled():
		return

	if not frappe.db.exists("Task", task_name):
		return

	task = frappe.get_doc("Task", task_name)

	if task.status == from_status:
		return

	status_config = STATUS_NOTIFICATIONS.get(task.status)
	if not status_config:
		return

	assignees = get_task_assignees(task.name)

	subscribers = []
	if task.project:
		subscribers = get_project_subscribers(task.project)

	recipients = get_recipients(status_config, assignees, subscribers)
	if not recipients:
		return

	message = build_message(task, assignees)
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
