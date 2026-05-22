import json
import frappe


def execute():
	boards = frappe.db.sql(
		"""
		SELECT name, fields
		FROM `tabKanban Board`
		WHERE reference_doctype = 'Task'
		""",
		as_dict=True,
	)

	for board in boards:
		fields = json.loads(board.fields or "[]")
		new_fields = ["custom_utilization" if f == "progress" else f for f in fields]

		if new_fields != fields:
			frappe.db.sql(
				"""
				UPDATE `tabKanban Board`
				SET fields = %s
				WHERE name = %s
				""",
				(json.dumps(new_fields), board.name),
			)
			frappe.db.commit()