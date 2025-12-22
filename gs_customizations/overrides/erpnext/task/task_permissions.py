import frappe

def task_query_conditions(user):
    allowed_roles = {
        "GS - Projects Manager",
        "Projects Manager",
        "System Manager"
    }

    user_roles = set(frappe.get_roles(user))

    if user_roles & allowed_roles:
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
