# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MatrixRoom(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		bot_power_level: DF.Int
		join_rule: DF.Data | None
		joined_members: DF.Int
		last_error: DF.SmallText | None
		last_synced: DF.Datetime | None
		parent_space: DF.Link | None
		room_id: DF.Data
		room_name: DF.Data | None
		room_type: DF.Literal["Space", "Room"]
		root_space: DF.Link | None
		status: DF.Literal["OK", "Needs Admin", "Error", "Not Managed"]
	# end: auto-generated types

	pass
