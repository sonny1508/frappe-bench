import frappe


def execute():
	"""Archive the Overdue column on every Task Kanban board grouped by status.

	Overdue is no longer a Task status - lateness is the Overdue priority now
	(overdue_priority.py) - so the column can never hold a card again. Archived
	rather than deleted: it can be brought back from the board's column menu.
	"""
	boards = frappe.get_all(
		"Kanban Board",
		filters={"reference_doctype": "Task", "field_name": "status"},
		pluck="name",
	)

	for board in boards:
		columns = frappe.get_all(
			"Kanban Board Column",
			filters={
				"parent": board,
				"parenttype": "Kanban Board",
				"column_name": "Overdue",
				"status": ["!=", "Archived"],
			},
			pluck="name",
		)

		for column in columns:
			frappe.db.set_value("Kanban Board Column", column, "status", "Archived", update_modified=False)

		if columns:
			frappe.clear_document_cache("Kanban Board", board)
