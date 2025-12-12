import frappe

def validate(doc, method):
    set_color_by_priority(doc)
    validate_task_fields_permissions(doc, method)

def set_color_by_priority(doc):
    priority_color_map = {
        "Urgent": "#FF4D4D",
        "High": "#FFA500",
        "Medium": "#318AD8",
        "Low": "#808080",
        "Support": "#28A745"
    }

    doc.color = priority_color_map.get(doc.priority, "#808080")

# Task fields permissions
def validate_task_fields_permissions(doc, method):
    user_roles = frappe.get_roles(frappe.session.user)
    
    if "Projects Manager" in user_roles:
        return
    
    if "GS Projects User" not in user_roles:
        return
    
    # Skip new documents
    if doc.is_new():
        return
    
    # Fields that Projects User is allowed to modify (when assigned)
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
        'status', 'progress', 'priority', 'subject', 'project', 'description',
        'expected_time', 'exp_start_date', 'exp_end_date', 'parent_task',
        'is_group', 'is_template', 'color', 'department', 'company',
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