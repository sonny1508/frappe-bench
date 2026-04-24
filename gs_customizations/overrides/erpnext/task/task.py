import frappe
from frappe import _, throw

from frappe.utils import now_datetime

from frappe.desk.form.assign_to import clear, close_all_assignments
from frappe.model.mapper import get_mapped_doc

from erpnext.projects.doctype.task.task import Task

class CustomTask(Task):

	def validate(self):
		self.validate_dates()
		self.validate_progress()
		self.validate_status()
		self.update_depends_on()
		self.validate_dependencies_for_template_task()
		self.validate_completed_on()
		self.validate_parent_is_group()
	

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
	
	def unassign_todo(self):
		if self.status == "Closed":
			close_all_assignments(self.doctype, self.name)
		if self.status == "Cancelled":
			clear(self.doctype, self.name)

	def update_status(self):
		if self.status in ("Open", "Working") and self.exp_end_date:
			from datetime import datetime

			if self.exp_end_date < datetime.now().date():
				self.db_set("status", "Overdue", update_modified=False)
				self.update_project()

def custom_validate(doc, method):
	set_color_by_priority(doc)
	validate_task_fields_permissions(doc)
	auto_update(doc)

def auto_update(doc):
	# auto_update_completed_by(doc)
	auto_update_completed_on(doc)

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
	priority_color_map = {
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
def validate_task_fields_permissions(doc):
	session_roles = frappe.get_roles(frappe.session.user)

	manager_roles = frappe.conf.get("manager_roles") or []
	
	if any(role in manager_roles for role in session_roles):
		return
	
	# Skip new documents
	if doc.is_new():
		return
	
	# Fields that GS - Projects User is allowed to modify (when assigned)
	allowed_fields = ['status', 'progress']
	
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
			f"You are only allowed to modify 'Status' and 'Progress' fields. "
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
		'status', 'progress', 'priority', 'type', 'subject', 'project', 'description',
		'expected_time', 'exp_start_date', 'exp_end_date', 'parent_task',
		'is_group', 'is_template', 'color', 'department', 'company',
		'completed_by', 'completed_on'
		'custom_assign_to_id', 'custom_reviewer',
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

	if doc.priority == "Support":
		allowed_statuses = ["Open", "Working", "Completed"]
	else:
		allowed_statuses = ["Open", "Working", "QA Pending"]
	
	if old_status not in allowed_statuses or new_status not in allowed_statuses:
		status_list = "', '".join(allowed_statuses)
		frappe.throw(
			f"For tasks with priority '{doc.priority}', you can only change status between '{status_list}'.",
			title="Status Change Not Allowed"
		)

# Auto update fields, tags, etc
def auto_set_reviewer(doc):
	"""Auto-set custom_reviewer when status changes to QA Reviewing/Feedback/Approved"""
	if doc.is_new():
		return
	
	old_status = frappe.db.get_value("Task", doc.name, "status")
	new_status = doc.status
	target_statuses = ["QA Reviewing", "QA Feedback", "QA Approved", "Delivered"]
	
	# Only when transitioning TO "QA Reviewing" from something else
	if new_status in target_statuses and old_status != new_status:
		employee_name = frappe.db.get_value(
			"Employee", 
			{"user_id": frappe.session.user}, 
			"employee_name",
		)
		if employee_name:
			doc.custom_reviewer = employee_name
			return
		
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

	from frappe.utils import get_fullname
	full_name = get_fullname(todo)

	if doc.status in ["Completed", "Closed"]:
		if todo:
			if not doc.completed_by:
				doc.completed_by = employee
				doc.custom_completed_by_employee = full_name
	else:
		if todo:
			doc.custom_assign_to_employee = full_name
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