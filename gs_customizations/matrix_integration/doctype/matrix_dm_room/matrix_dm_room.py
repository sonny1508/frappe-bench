# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MatrixDMRoom(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		error_log: DF.SmallText | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		room_id: DF.Data | None
		status: DF.Literal["Active", "Failed"]
		username: DF.Data
	# end: auto-generated types

	pass
