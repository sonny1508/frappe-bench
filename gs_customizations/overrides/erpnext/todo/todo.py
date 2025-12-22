import frappe

def update_task_assign_to(doc):
	"""Update Task's custom_assign_to when assigned via ToDo"""
	if doc.reference_type != "Task":
		return
	
	if doc.status == "Cancelled":
		return
	
	employee = frappe.db.get_value(
		"Employee",
		{"user_id": doc.allocated_to},
		"employee"
	)
	
	if employee:
		frappe.db.set_value("Task", doc.reference_name, "custom_assign_to", employee)