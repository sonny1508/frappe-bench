# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MatrixSpaceSteward(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		employee: DF.Link
		employee_name: DF.Data | None
		min_role: DF.Literal["Moderator", "Admin"]
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
