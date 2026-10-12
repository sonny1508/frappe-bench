# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_link_to_form


class MatrixRoomMember(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		added_by_bot_on: DF.Datetime | None
		current_power_level: DF.Int
		department: DF.Link | None
		designation: DF.Link | None
		employee: DF.Link | None
		employee_name: DF.Data | None
		employee_status: DF.Data | None
		enforce: DF.Check
		joined_before: DF.Check
		last_error: DF.SmallText | None
		matrix_user_id: DF.Data
		membership: DF.Literal["", "Joined", "Invited", "Left", "Banned", "Not Joined"]
		min_role: DF.Literal["Default", "Moderator", "Admin"]
		room: DF.Link
		room_name: DF.Data | None
		room_type: DF.Data | None
		root_space: DF.Link | None
		source: DF.Literal["Manual", "Steward"]
	# end: auto-generated types

	def validate(self):
		self.set_matrix_user_id()
		self.check_duplicate()

	def set_matrix_user_id(self):
		"""The employee's username is the Matrix localpart — always derive it."""
		if not self.employee:
			if not self.matrix_user_id:
				frappe.throw("Set an Employee, or a Matrix User ID for someone who is not an employee.")
			return

		from gs_customizations.matrix.spaces import matrix_user_id_for_employee

		matrix_id = matrix_user_id_for_employee(self.employee)
		if not matrix_id:
			frappe.throw(
				f"Employee {self.employee} has no linked User with a username, "
				"so their Matrix ID is unknown."
			)
		self.matrix_user_id = matrix_id

	def check_duplicate(self):
		existing = frappe.db.get_value(
			"Matrix Room Member",
			{"room": self.room, "matrix_user_id": self.matrix_user_id, "name": ["!=", self.name]},
		)
		if existing:
			frappe.throw(
				f"{self.matrix_user_id} already has a row for this room: "
				f"{get_link_to_form('Matrix Room Member', existing)}"
			)
