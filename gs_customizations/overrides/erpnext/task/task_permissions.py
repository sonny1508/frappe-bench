import frappe
from gs_customizations.validate.permissions import is_manager

def task_query_conditions(user):
    if is_manager(user):
        return ""

    return f"""
        EXISTS (
            SELECT 1
            FROM `tabToDo`
            WHERE
                `tabToDo`.reference_type = 'Task'
                AND `tabToDo`.reference_name = `tabTask`.name
                AND `tabToDo`.allocated_to = '{user}'
                AND `tabToDo`.status = 'Open'
        )
    """
