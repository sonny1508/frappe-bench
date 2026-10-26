# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MatrixPendingNotification(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from_status: DF.Data | None
		send_after: DF.Datetime | None
		task: DF.Link
		to_status: DF.Data | None
	# end: auto-generated types

	pass
