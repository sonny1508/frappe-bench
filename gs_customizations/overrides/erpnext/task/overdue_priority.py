"""The Overdue priority: how a Task past its deadline is marked.

This replaces ERPNext's Overdue *status*. ERPNext switched Open/Working tasks
past exp_end_date to status Overdue, which pulled the task out of its workflow
stage, and validate_status_transition() gave artists no way to move it on again.
The status is now left alone and lateness is carried by the priority.

For a task that is not finished:
  * past its deadline     -> the priority becomes Overdue, and the priority it
                             had is kept in custom_priority_before_overdue.
  * while it stays late   -> the priority cannot be changed.
  * deadline moved later  -> the kept priority comes back.
  * Overdue is never picked by hand; only these rules set it.

A finished task is left as it is, so one that finished late keeps Overdue as the
record of it.

"Past its deadline" means exp_end_date is before today: the deadline day itself
is still on time.

Two code paths apply the rules, and both go through resolve_priority():
  1. apply_overdue_priority()   Task validate, on every save
  2. CustomTask.update_status() ERPNext's daily set_tasks_as_overdue job
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, today

OVERDUE = "Overdue"
DEFAULT_PRIORITY = "Medium"
FINISHED_STATUSES = ("Completed", "Closed", "Cancelled", "Template")


def is_past_deadline(exp_end_date, status, on_date=None):
	"""Whether a task with this deadline and status counts as late today."""
	if status in FINISHED_STATUSES or not exp_end_date:
		return False

	return getdate(exp_end_date) < getdate(on_date or today())


def resolve_priority(stored_priority, new_priority, kept_priority, past_deadline, finished):
	"""Decide the priority a save ends with.

	stored_priority is the value in the database (None for a new task),
	new_priority the value being saved, kept_priority the stored
	custom_priority_before_overdue.

	Returns (priority, kept_priority, error). error is None, "locked" (changing
	away from Overdue while still late) or "manual" (picking Overdue by hand),
	and the save is refused when it is set.

	A pure function over scalars, so the rules can be checked without a database.
	"""
	was_overdue = stored_priority == OVERDUE

	if new_priority == OVERDUE and not was_overdue and not past_deadline:
		return new_priority, kept_priority, "manual"

	if finished:
		return new_priority, kept_priority, None

	if past_deadline:
		if was_overdue and new_priority != OVERDUE:
			return new_priority, kept_priority, "locked"

		if not was_overdue:
			# Going late with this save. Keep what it had, or what it was just
			# changed to if the same save also changed the priority.
			kept_priority = new_priority if new_priority != OVERDUE else stored_priority

		return OVERDUE, kept_priority or DEFAULT_PRIORITY, None

	# Not late. A task that was Overdue had its deadline moved later (or cleared).
	if new_priority == OVERDUE:
		return kept_priority or DEFAULT_PRIORITY, None, None

	return new_priority, None, None


def apply_overdue_priority(doc):
	"""Apply the rules to a Task being saved. Returns True if the priority changed.

	Runs after validate_task_fields_permissions(): a priority the system sets is
	not a change the user made, so it must not count against an artist's
	status-only edit.
	"""
	stored_priority = None if doc.is_new() else frappe.db.get_value("Task", doc.name, "priority")

	priority, kept_priority, error = resolve_priority(
		stored_priority,
		doc.priority,
		# .get: a process can load this code before migrate has added the field.
		doc.get("custom_priority_before_overdue"),
		is_past_deadline(doc.exp_end_date, doc.status),
		doc.status in FINISHED_STATUSES,
	)

	if error == "locked":
		frappe.throw(
			_("Task {0} is past its Expected End Date ({1}), so its priority stays {2}. Move the Expected End Date later to change it.").format(
				frappe.bold(doc.name), formatdate(doc.exp_end_date), frappe.bold(OVERDUE)
			),
			title=_("Priority Locked"),
		)

	if error == "manual":
		frappe.throw(
			_("{0} is set automatically once a task passes its Expected End Date, and can't be picked by hand.").format(
				frappe.bold(OVERDUE)
			),
			title=_("Priority Not Allowed"),
		)

	changed = priority != doc.priority
	doc.priority = priority
	doc.custom_priority_before_overdue = kept_priority

	return changed


def workflow_priority(doc):
	"""The priority that decides which status workflow a task follows.

	While a task is Overdue its kept priority still decides, so a late Support
	task keeps the Support workflow instead of being moved onto the QA path.
	"""
	if doc.priority == OVERDUE:
		return doc.get("custom_priority_before_overdue") or DEFAULT_PRIORITY

	return doc.priority
