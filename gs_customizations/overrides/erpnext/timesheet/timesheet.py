import frappe
from frappe.utils import getdate

FREE_FIELDS = ["project", "project_name", "task", "custom_task_name", "custom_task_type"]

def clear_free_activity_fields(doc, method):
    for row in doc.time_logs:
        if row.activity_type == "Free":
            for field in FREE_FIELDS:
                row.set(field, None)

def update_completed_from_task(doc, method):
    for row in doc.time_logs:
        if row.task:
            task = frappe.db.get_value("Task", row.task, ["status", "completed_on"], as_dict=True)
            if (
                task
                and task.status in ("Completed", "Closed")
                and task.completed_on
                and row.from_time
                and getdate(row.from_time) >= getdate(task.completed_on)
            ):
                row.completed = 1
            else:
                row.completed = 0
        else:
            row.completed = 0