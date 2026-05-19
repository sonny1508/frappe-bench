# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class MatrixSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from gs_customizations.matrix_integration.doctype.matrix_dm_room.matrix_dm_room import MatrixDMRoom
		from gs_customizations.matrix_integration.doctype.matrix_group_room.matrix_group_room import MatrixGroupRoom

		auto_provision_rooms: DF.Check
		bot_access_token: DF.Password | None
		bot_display_name: DF.Data | None
		bot_is_admin: DF.Check
		bot_user_id: DF.Data | None
		dm_rooms: DF.Table[MatrixDMRoom]
		enabled: DF.Check
		group_rooms: DF.Table[MatrixGroupRoom]
		homeserver_url: DF.Data | None
		test_dm_username: DF.Data | None
		test_group_room: DF.Data | None
		test_message: DF.SmallText | None
		test_target_type: DF.Literal["DM", "Group"]
	# end: auto-generated types

	@frappe.whitelist()
	def test_connection(self):
		"""Verify bot access token is valid by calling /_matrix/client/v3/account/whoami."""
		from gs_customizations.matrix.bot import test_connection
		return test_connection()

	@frappe.whitelist()
	def send_test_message(self):
		"""Send a test message to the selected DM user or group room."""
		from gs_customizations.matrix.bot import get_matrix_user_id, send_message, send_server_notice

		if not self.test_message:
			frappe.throw("Please enter a test message.")

		if self.test_target_type == "DM":
			if not self.test_dm_username:
				frappe.throw("Please enter a DM username.")
			# Use server notice for DMs — no room provisioning needed
			matrix_user_id = get_matrix_user_id(self.test_dm_username)
			send_server_notice(matrix_user_id, self.test_message)
			frappe.msgprint(f"Server notice sent to {self.test_dm_username}")

		elif self.test_target_type == "Group":
			if not self.test_group_room:
				frappe.throw("Please enter a group room name.")
			room_id = None
			for row in self.group_rooms:
				if row.room_name == self.test_group_room and row.status == "Active":
					room_id = row.room_id
					break
			if not room_id:
				frappe.throw(f"No active group room found for name: {self.test_group_room}")
			send_message(room_id, self.test_message)
			frappe.msgprint(f"Message sent to group room {self.test_group_room}")

	@frappe.whitelist()
	def provision_all_dm_rooms(self):
		"""Bulk-provision DM rooms for all employees with a User.username that don't already have one."""
		from gs_customizations.matrix.provisioning import provision_all_dm_rooms
		result = provision_all_dm_rooms()
		return result
