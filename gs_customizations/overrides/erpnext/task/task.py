import frappe
from frappe import _, throw

from frappe.utils import now_datetime
from frappe.utils import flt
from frappe.utils import getdate
from frappe.utils import get_fullname

from frappe.desk.form.assign_to import clear, close_all_assignments
from frappe.model.mapper import get_mapped_doc

from erpnext.projects.doctype.task.task import Task

from gs_customizations.overrides.erpnext.task.overdue_priority import (
	OVERDUE,
	apply_overdue_priority,
	is_past_deadline,
	workflow_priority,
)

class CustomTask(Task):

	def validate(self):
		self.validate_dates()
		self.validate_progress()
		self.validate_status()
		self.update_depends_on()
		self.validate_dependencies_for_template_task()
		self.validate_completed_on()
		self.validate_parent_is_group()
		
	def validate_progress(self):
		pass
	

	def validate_status(self):
		if self.is_template and self.status != "Template":
			self.status = "Template"
		if self.status != self.get_db_value("status") and self.status == "Completed":
			for d in self.depends_on:
				if frappe.db.get_value("Task", d.task, "status") not in ("Completed", "Cancelled", "Closed"):
					frappe.throw(
						_(
							"Cannot complete task {0} as its dependant task {1} are not completed / cancelled / closed."
						).format(frappe.bold(self.name), frappe.bold(d.task))
					)
		if self.status != self.get_db_value("status") and self.status == "Closed":
			close_all_assignments(self.doctype, self.name)
			# self.custom_assign_to_id = ""

		if self.status != self.get_db_value("status") and self.status == "QA Pending":
			for d in self.depends_on:
				if frappe.db.get_value("Task", d.task, "status") not in ("Completed", "Cancelled", "Closed"):
					frappe.throw(
						_(
							"Cannot QA task {0} as its dependant task {1} are not completed / cancelled / closed."
						).format(frappe.bold(self.name), frappe.bold(d.task))
					)

	def on_update(self):
		self.update_nsm_model()
		self.check_recursion()
		self.reschedule_dependent_tasks()
		self.update_project()
		self.unassign_todo()
		self.populate_depends_on()
		self.update_utilization()

	def update_utilization(self):
		expected = flt(self.expected_time or 0)
		actual = flt(self.actual_time or 0)

		if expected <= 0:
			custom_utilization = 0
		else:
			custom_utilization = round((actual / expected) * 100, 2)

		if flt(self.custom_utilization) != custom_utilization:
			self.db_set("custom_utilization", custom_utilization, update_modified=False)
			self.custom_utilization = custom_utilization
	
	def unassign_todo(self):
		if self.status == "Closed":
			close_all_assignments(self.doctype, self.name)
		if self.status == "Cancelled":
			clear(self.doctype, self.name)

	def update_status(self):
		"""Daily deadline check, called for every unfinished task by ERPNext's
		set_tasks_as_overdue scheduler job.

		ERPNext's version switched the status to Overdue. Here the status is left
		alone: a task that has passed its deadline is saved, so that
		apply_overdue_priority() gives it the Overdue priority (overdue_priority.py).

		Saved through the full lifecycle rather than db_set so the change bumps
		`modified` - a form left open from before is then refused on save instead
		of quietly writing its old priority back - and shows in the Task's history.
		"""
		if self.priority == OVERDUE or not is_past_deadline(self.exp_end_date, self.status):
			return

		# ERPNext's job loops every task with no error handling of its own, so one
		# task that fails to save must not stop the rest.
		frappe.db.savepoint("overdue_priority")
		try:
			self.save(ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point="overdue_priority")
			frappe.log_error(
				frappe.get_traceback(),
				"gs_customizations: Overdue priority for Task {0} failed".format(self.name),
			)

def custom_validate(doc, method):
	set_color_by_priority(doc)
	validate_task_fields_permissions(doc)

	# After the permission check: a priority the system sets is not a change the
	# user made.
	if apply_overdue_priority(doc):
		set_color_by_priority(doc)

	auto_update(doc)

def auto_update(doc):
	# auto_update_completed_by(doc)
	auto_update_completed_on(doc)

	preserve_exp_start_date(doc)
	auto_set_fields_on_todo(doc)
	auto_set_reviewer(doc)
	auto_update_tag_on_status(doc)

def on_change(doc, method):
	set_color_by_priority(doc)


def auto_update_completed_by(doc):
	if doc.status in ["Completed", "Closed"] and not doc.completed_by:
		todo = frappe.db.get_value(
			"ToDo",
			{
				"reference_type": "Task",
				"reference_name": doc.name,
				"status": ["not in", ["Closed", "Cancelled"]]
			},
			"allocated_to"
		)

		if todo:
			employee = frappe.db.get_value(
				"Employee",
				{"user_id": todo},
				"name"
			)

			if employee:
				doc.completed_by = employee

def auto_update_completed_on(doc):
	if doc.status == "Completed":
		if not doc.has_value_changed("status"):
			return
		old_status = doc.get_doc_before_save()
		if old_status and old_status.status == "Closed":
			return
		doc.completed_on = now_datetime()
	elif doc.status == "Closed" and not doc.completed_on:
		doc.completed_on = now_datetime()

def set_color_by_priority(doc):
	# Keep in step with the same map in task.js: the form saves the task again
	# whenever its color disagrees with this one.
	priority_color_map = {
		"Overdue": "#8B0000",
		"Urgent": "#FF4D4D",
		"High": "#FFA500",
		"Medium": "#318AD8",
		"Low": "#808080",
		"Support": "#28A745"
	}

	new_color = priority_color_map.get(doc.priority, "#808080")
	
	if doc.color != new_color:
		# Use db_set to avoid recursion
		doc.db_set("color", new_color, update_modified=False)


# Task fields permissions

# Completion metadata is derived by the server from the assignment and the status
# change (see auto_update), never from what the client submits.
COMPLETION_FIELDS = ['completed_by', 'completed_on', 'custom_completed_by_employee']


def discard_client_completion_fields(doc):
	"""Roll completion metadata back to its stored values.

	The Task form fills these in client-side when status becomes 'Completed'
	(see task.js). For non-managers those values would otherwise register as
	restricted field changes below. Dropping them here both keeps the field
	guard focused on 'status' and stops the values from being forged - auto_update
	recomputes them from the ToDo assignment once validation has passed.
	"""
	db_values = frappe.db.get_value("Task", doc.name, COMPLETION_FIELDS, as_dict=True) or {}

	for fieldname in COMPLETION_FIELDS:
		doc.set(fieldname, db_values.get(fieldname))


def validate_task_fields_permissions(doc):
	session_roles = frappe.get_roles(frappe.session.user)

	manager_roles = frappe.conf.get("manager_roles") or []

	if any(role in manager_roles for role in session_roles):
		return

	# Skip new documents
	if doc.is_new():
		return

	discard_client_completion_fields(doc)

	# Fields that GS - Projects User is allowed to modify (when assigned)
	allowed_fields = ['status']


	# Get changed fields by directly comparing with database
	changed_fields = get_changed_fields_from_db(doc, allowed_fields)
	
	# No changes to validate
	if not changed_fields['allowed'] and not changed_fields['restricted']:
		return
	
	# Check if user is assigned to this task
	is_assigned = check_user_assignment(doc.name)
	
	if not is_assigned:
		frappe.throw(
			"You must be assigned to this task to make any changes.",
			title="Permission Denied"
		)
	
	if changed_fields['restricted']:
		frappe.throw(
			f"You are only allowed to modify 'Status' fields. "
			f"Cannot modify: {', '.join(changed_fields['restricted'])}",
			title="Permission Denied"
		)
	
	if 'status' in changed_fields['allowed']:
		validate_status_transition(doc)


def get_changed_fields_from_db(doc, allowed_fields):
	"""Compare current values directly against database values"""
	changed = {'allowed': [], 'restricted': []}
	
	# Get ALL current database values in one query
	db_values = frappe.db.get_value(
		"Task",
		doc.name,
		["*"],
		as_dict=True
	)
	
	if not db_values:
		return changed
	
	# Fields to check - only editable, relevant fields
	fields_to_check = [
		'status', 'priority', 'type', 'subject', 'project', 'description',
		'expected_time', 'exp_start_date', 'exp_end_date', 'parent_task',
		'is_group', 'is_template', 'color', 'department', 'company',
		'completed_by', 'completed_on',
		'custom_assign_to_id', 'custom_reviewer', 'custom_utilization',
		# Add more fields as needed
	]
	
	for fieldname in fields_to_check:
		old_value = db_values.get(fieldname)
		new_value = doc.get(fieldname)
		
		# Normalize for comparison (handle None vs empty string, etc.)
		old_normalized = normalize_value(old_value)
		new_normalized = normalize_value(new_value)
		
		if old_normalized != new_normalized:
			if fieldname in allowed_fields:
				changed['allowed'].append(fieldname)
			else:
				changed['restricted'].append(fieldname)
	
	return changed


def normalize_value(value):
	"""Normalize values for comparison"""
	if value is None:
		return ''
	if isinstance(value, (int, float)):
		return value
	return str(value).strip()


def check_user_assignment(task_name):
	"""Check if current user is assigned to the task"""
	allocated_users = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": task_name,
			"status": ["!=", "Cancelled"]
		},
		fields=["allocated_to"]
	)
	assigned_users = [u.allocated_to for u in allocated_users]
	return frappe.session.user in assigned_users


def validate_status_transition(doc):
	"""Validate allowed status transitions based on priority"""
	old_status = frappe.db.get_value("Task", doc.name, "status") or ''
	new_status = doc.status or ''
	
	milestone_statuses = ["Open", "QA Feedback", "Client Feedback"]

	# Allow: Feedback -> Working (one-way)
	if old_status in milestone_statuses:
		if new_status != "Working":
			frappe.throw(
				f"From '{old_status}', you can only change status to 'Working'.",
				title="Status Change Not Allowed"
			)
		return
	
	# Block: Anything -> Feedback (prevents reverse route)
	if new_status in milestone_statuses:
		frappe.throw(
			f"You are not allowed to set status to '{new_status}'.",
			title="Status Change Not Allowed"
		)

	priority = workflow_priority(doc)

	if priority == "Support":
		allowed_statuses = ["Open", "Working", "Completed"]
	else:
		allowed_statuses = ["Open", "Working", "QA Pending"]
	
	if old_status not in allowed_statuses or new_status not in allowed_statuses:
		status_list = "', '".join(allowed_statuses)
		frappe.throw(
			f"For tasks with priority '{priority}', you can only change status between '{status_list}'.",
			title="Status Change Not Allowed"
		)

# Auto update fields, tags, etc
def auto_set_reviewer(doc):
    """Auto-set custom_reviewer: inherit from parent, or set on status transition for top-level tasks."""
    # Child tasks: always sync reviewer from parent, skip status-based logic
    if doc.parent_task:
        doc.custom_reviewer = frappe.db.get_value(
            "Task", doc.parent_task, "custom_reviewer"
        )
        return

    if doc.is_new():
        return

    old_status = frappe.db.get_value("Task", doc.name, "status")
    new_status = doc.status
    target_statuses = ["QA Reviewing", "QA Feedback", "QA Approved", "Delivered"]

    if new_status in target_statuses and old_status != new_status:
        employee_name = frappe.db.get_value(
            "Employee",
            {"user_id": frappe.session.user},
            "employee_name",
        )
        if employee_name:
            doc.custom_reviewer = employee_name
		
    # Fallback: if custom_reviewer is still empty, pull from Project
	# if not doc.custom_reviewer and doc.project:
	# 	default_reviewer = frappe.db.get_value(
    #         "Portal User",
    #         {"parent": doc.project, "parenttype": "Project", "idx": 1},
    #         "custom_employee_name",
	# 	)
	# 	if default_reviewer:
	# 		doc.custom_reviewer = default_reviewer

def auto_update_tag_on_status(doc):
	"""Auto-add tags when status changes to feedback statuses"""
	if doc.is_new():
		return
	
	old_status = frappe.db.get_value("Task", doc.name, "status")
	new_status = doc.status
	
	if old_status == new_status:
		return
	
	if new_status == "QA Feedback":
		doc.add_tag("FB Internal")
	
	elif new_status == "Client Feedback":
		doc.add_tag("FB Client")

	elif new_status == "Delivered":
		doc.remove_tag("FB Internal")

	elif new_status == "Completed" or new_status == "Closed":
		doc.remove_tag("FB Client")
		doc.remove_tag("FB Internal")

def auto_set_fields_on_todo(doc):
	"""Update Task's custom_assign_to when assigned"""
	if doc.is_new():
		return

	assignees = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Task",
			"reference_name": doc.name,
			"status": ["not in", ["Closed", "Cancelled"]]
		},
		pluck="allocated_to"
	)
	todo = assignees[0] if assignees else None

	if doc.status in ["Completed", "Closed"]:
		# Credit the user who did the completing when they are one of the
		# assignees, so multi-assignee tasks don't credit an arbitrary one.
		completed_by = frappe.session.user if frappe.session.user in assignees else todo

		if completed_by and not doc.completed_by:
			doc.completed_by = frappe.db.get_value(
				"Employee",
				{"user_id": completed_by},
				"name"
			)
			doc.custom_completed_by_employee = get_fullname(completed_by)
	else:
		if todo:
			doc.custom_assign_to_employee = get_fullname(todo)
			doc.custom_assign_to_id = todo
		else:
			doc.custom_assign_to_employee = ""
			doc.custom_assign_to_id = ""

@frappe.whitelist()
def get_employee_from_todo(task_name):
    """Get employee ID from the user assigned in ToDo for this task"""
    # Get the ToDo linked to this task
    todo = frappe.db.get_value(
		"ToDo", 
        {
			"reference_type": "Task",
		 	"reference_name": task_name,
		 	"status": "Open"
		}, 
        "allocated_to"
    )
    
    if todo:
        # Get employee from the user
        employee = frappe.db.get_value(
			"Employee", 
			{"user_id": todo},
			["name", "employee_name"],
			as_dict=True
		)

        return employee
    
    return None

# ---------------------------------------------------------------------------
# Expected Start Date, derived from the assignment
#
# exp_start_date is server-owned on this site: it records the date an assignee
# was added to the Task, and is re-stamped every time an assignee is removed and
# assigned again - same person or not. Three code paths write it, and all three
# go through the two helpers below so they cannot drift apart:
#
#   1. set_exp_start_date_from_assignment()   ToDo after_insert   (live)
#   2. preserve_exp_start_date()              Task validate       (anti-clobber)
#   3. maintenance/task_exp_start_backfill.py                     (one-off sweep)
# ---------------------------------------------------------------------------


def resolve_assignment_date(todo_creation):
	"""The single definition of "the date an assignee was added".

	Always the ToDo row's `creation`. ToDo.date is the *due* date - assign_to.add()
	merely seeds it from nowdate() and it is freely edited afterwards - so it is
	the wrong column for this.

	Read off the row rather than from nowdate() so the live hook and the backfill
	derive the same value from the same input, and so the rule stays testable
	without freezing the clock.
	"""
	return getdate(todo_creation)


def exp_start_date_block_reason(assignment_date, exp_end_date=None, project_end_date=None):
	"""Reason string if writing `assignment_date` would break Task validation, else None.

	erpnext's Task.validate_dates() runs validate_from_to_dates("exp_start_date",
	"exp_end_date") and validate_parent_project_dates(); both raise InvalidDates.
	Neither runs on our write, because we go through frappe.db.set_value - so a bad
	value is not rejected at write time, it detonates on the NEXT ordinary save by
	any user and leaves the Task un-editable until someone with DB access fixes it.

	So we refuse the write instead. Clamping to the bound was considered and
	rejected: the field's whole contract is "the date the assignee was assigned",
	and a clamped date is silently wrong data that looks correct. A NULL is
	honestly absent - and NULL is what every one of these tasks holds today.

	Deliberately a pure function over scalars: the live hook looks the bounds up
	with one get_value, the backfill already has them from its JOIN, and neither
	can drift from the other.
	"""
	assignment_date = getdate(assignment_date)

	if exp_end_date and assignment_date > getdate(exp_end_date):
		return "after-exp-end-date"

	if project_end_date and assignment_date > getdate(project_end_date):
		return "after-project-end-date"

	return None


def set_exp_start_date_from_assignment(doc, method=None):
	"""Stamp Task.exp_start_date with the day this assignee was added.

	Hooked to: ToDo -> after_insert.

	after_insert, not on_update: a ToDo row is inserted exactly once per assignment,
	while un-assigning only flips `status` (assign_to.remove -> Cancelled,
	close_all_assignments -> Closed, clear -> Cancelled, all via todo.save()). And
	a genuine remove-then-re-add clears the Open-status duplicate guard in
	assign_to.add(), inserting a NEW row with a new `creation` - so "re-stamp every
	time the assignee is removed and assigned again" falls out of the framework for
	free, for the same person as well as a different one.

	Writes with frappe.db.set_value(update_modified=False) rather than doc.save():

	  * doc.save() would re-run the entire Task lifecycle from inside the ToDo
		insert transaction - validate_status, update_depends_on,
		validate_task_fields_permissions, then on_update -> update_nsm_model,
		check_recursion, reschedule_dependent_tasks, update_project (which re-costs
		the whole Project) and notify_task_update (a Matrix HTTP call per
		assignment).
	  * update_modified=False keeps `modified` still. The assigning manager has the
		Task form open - assign_to.js re-renders the sidebar avatars but never
		reloads the doc - so bumping `modified` would hand them "Document has been
		modified after you have opened it" on their very next save.
	  * It is the framework's own precedent: ToDo.update_in_reference() writes the
		parent's `_assign` exactly this way, from this exact event.

	Consequence worth knowing: db.set_value writes no Version row, so changes to
	this field do not appear in the Task's document history. The `tabToDo` rows are
	the audit trail.

	Never raises. This runs inside the assignment's own transaction, and a
	bookkeeping field must not be able to fail an assignment.
	"""
	try:
		if doc.reference_type != "Task" or not doc.reference_name:
			return

		# A real assignment is always inserted Open by assign_to.add(); anything
		# else was hand-made in the ToDo list view and is not an assignment event.
		# A role-based ToDo has no allocated_to and is not an assignment to a person.
		if doc.status != "Open" or not doc.allocated_to:
			return

		task = frappe.db.get_value(
			"Task",
			doc.reference_name,
			["name", "exp_start_date", "exp_end_date", "act_start_date", "project"],
			as_dict=True,
		)
		if not task:
			return

		# Once a submitted Timesheet has stamped a real start date (via
		# Task.update_time_and_costing), the expected start date is settled history.
		if task.act_start_date:
			return

		assignment_date = resolve_assignment_date(doc.creation)

		# Same-day re-assignment: skip the pointless UPDATE and cache bust.
		if task.exp_start_date and getdate(task.exp_start_date) == assignment_date:
			return

		project_end_date = (
			frappe.db.get_value("Project", task.project, "expected_end_date")
			if task.project
			else None
		)

		reason = exp_start_date_block_reason(
			assignment_date, task.exp_end_date, project_end_date
		)
		if reason:
			# An expected outcome under a specific data shape, not a bug - so it
			# goes to the app log, not the Error Log, where predictable noise would
			# train people to ignore genuine failures.
			frappe.logger("gs_customizations").warning(
				"exp_start_date skipped for Task {0}: assignment date {1} is {2} "
				"(exp_end_date={3}, project_end_date={4})".format(
					task.name, assignment_date, reason, task.exp_end_date, project_end_date
				)
			)
			return

		frappe.db.set_value(
			"Task",
			task.name,
			"exp_start_date",
			assignment_date,
			update_modified=False,
		)

	except Exception:
		# The assignment must succeed even if this does not.
		# defer_insert pushes the Error Log through redis instead of the current
		# transaction: assign_to.add() can still frappe.throw() *after* this hook
		# (it checks assignee permissions afterwards), and a rollback would
		# otherwise take the error record down with it.
		frappe.log_error(
			frappe.get_traceback(),
			"gs_customizations: exp_start_date from assignment failed",
			defer_insert=True,
		)


def preserve_exp_start_date(doc):
	"""Stop a stale form from silently wiping the server-set exp_start_date.

	set_exp_start_date_from_assignment() deliberately writes with
	update_modified=False, so a Task form that was already open when the assignment
	happened still holds the pre-assignment value AND still passes check_if_latest().
	Saving it would write that stale blank straight back over ours - and nothing
	would restore it, because an ordinary save inserts no ToDo row and the live hook
	never fires again.

	GS - Projects User is already covered by the framework: exp_start_date is
	permlevel 1 (Property Setter Task-exp_start_date-permlevel) and that role has
	read-but-not-write there, so Document.validate_higher_perm_levels() resets the
	field from a fresh DB read before validate runs. GS - Projects Manager and
	System Manager DO hold permlevel 1 write, are exempt from
	validate_task_fields_permissions(), and are the only roles block_assign() lets
	assign in the first place - so they are exactly who this is for.

	Restore-only: a manager who types a real date still gets to set it. Only a blank
	posted over a stored value is treated as stale. The trade-off is that the field
	can no longer be *cleared* from the form - a deliberate blank and a stale blank
	are indistinguishable, both arriving with a matching `modified`. Clearing is
	available through maintenance/task_exp_start_backfill.revert().

	Note this never re-derives a date from ToDo. CustomTask.validate() - and so
	validate_dates() - has already run by the time this doc_event fires, so any new
	value set here would escape validation entirely. The value restored here was
	bound-checked by exp_start_date_block_reason() when it was first written.
	"""
	if doc.is_new():
		return

	if doc.exp_start_date:
		return

	stored = frappe.db.get_value("Task", doc.name, "exp_start_date")
	if stored:
		doc.exp_start_date = stored


def set_assignee_from_assignment(doc, method=None):
	"""Stamp Task.custom_assign_to_employee / custom_assign_to_id on assignment.

	Hooked to: ToDo -> after_insert.

	auto_set_fields_on_todo() already derives these two fields, but only when the
	Task itself is saved - and assigning somebody does not save the Task, it only
	inserts a ToDo. So a freshly created Open task sat with an empty
	custom_assign_to_employee until someone happened to edit it for an unrelated
	reason. GS Task Sheet now filters on that field, which made the gap visible as
	silently missing rows.

	Mirrors auto_set_fields_on_todo()'s rule that a Completed or Closed task keeps
	the assignee it finished with rather than being re-stamped.

	Assign direction only. Un-assigning still reconciles on the Task's next save,
	exactly as before. Hooking ToDo.on_update to catch it would be actively
	dangerous: close_all_assignments() runs inside CustomTask.validate_status()
	while the Task's *stored* status is still the old one, so the guard below
	would not have flipped yet and closing a task would wipe its assignee.

	Never raises - this runs inside the assignment's transaction.
	"""
	try:
		if doc.reference_type != "Task" or not doc.reference_name:
			return

		if doc.status != "Open" or not doc.allocated_to:
			return

		task_status = frappe.db.get_value("Task", doc.reference_name, "status")
		if task_status is None or task_status in ("Completed", "Closed"):
			return

		frappe.db.set_value(
			"Task",
			doc.reference_name,
			{
				"custom_assign_to_employee": get_fullname(doc.allocated_to),
				"custom_assign_to_id": doc.allocated_to,
			},
			update_modified=False,
		)

	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"gs_customizations: assignee stamp from assignment failed",
			defer_insert=True,
		)
