import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import DATE_FORMAT, flt, formatdate, get_link_to_form, getdate, today

from hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry import InvalidLeaveLedgerEntry


class CustomLeaveLedgerEntry(Document):
	"""Override to handle duration-based allocations"""
	
	def validate(self):
		if getdate(self.from_date) > getdate(self.to_date):
			frappe.throw(
				_(
					"Leave Ledger Entry's To date needs to be after From date. Currently, From Date is {0} and To Date is {1}"
				).format(
					frappe.bold(formatdate(self.from_date)),
					frappe.bold(formatdate(self.to_date)),
				),
				exc=InvalidLeaveLedgerEntry,
				title=_("Invalid Leave Ledger Entry"),
			)

	def on_cancel(self):
		# allow cancellation of expiry leaves
		if self.is_expired:
			frappe.db.set_value("Leave Allocation", self.transaction_name, "expired", 0)
		else:
			frappe.throw(_("Only expired allocation can be cancelled"))


def validate_leave_allocation_against_leave_application(ledger):
	"""Checks that leave allocation has no leave application against it"""
	leave_application_records = frappe.db.sql_list(
		"""
		SELECT transaction_name
		FROM `tabLeave Ledger Entry`
		WHERE
			employee=%s
			AND leave_type=%s
			AND transaction_type='Leave Application'
			AND from_date>=%s
			AND to_date<=%s
	""",
		(ledger.employee, ledger.leave_type, ledger.from_date, ledger.to_date),
	)

	if leave_application_records:
		frappe.throw(
			_("Leave allocation {0} is linked with the Leave Application {1}").format(
				ledger.transaction_name,
				", ".join(
					get_link_to_form("Leave Application", application)
					for application in leave_application_records
				),
			)
		)


def create_custom_leave_ledger_entry(ref_doc, args, submit=True):
	"""
	Custom version of create_leave_ledger_entry for duration-based system.
	
	Args:
		ref_doc: Leave Allocation document (with custom duration fields)
		args: Dictionary containing:
			- custom_time_leaves: Value in SECONDS (Duration fieldtype) - NOT days
			- from_date, to_date
			- is_carry_forward, is_expired, is_lwp (optional)
		submit: Whether to submit the entry
	
	The custom_time_leaves field stores durations in SECONDS.
	This is the native Duration fieldtype behavior.
	"""
	ledger = frappe._dict(
		doctype="Leave Ledger Entry",
		employee=ref_doc.employee,
		employee_name=ref_doc.employee_name,
		leave_type=ref_doc.leave_type,
		transaction_type=ref_doc.doctype,
		transaction_name=ref_doc.name,
		is_carry_forward=0,
		is_expired=0,
		is_lwp=0,
	)
	ledger.update(args)

	if submit:
		doc = frappe.get_doc(ledger)
		doc.flags.ignore_permissions = 1
		doc.submit()
	else:
		delete_ledger_entry(ledger)


def create_leave_ledger_entry(ref_doc, args, submit=True):
	"""
	Wrapper that ensures proper duration handling.
	
	For Leave Allocation documents, the 'custom_time_leaves' value should be in SECONDS.
	This is stored directly in the Duration fieldtype on Leave Ledger Entry.
	"""
	create_custom_leave_ledger_entry(ref_doc, args, submit=submit)


def delete_ledger_entry(ledger):
	"""Delete ledger entry on cancel of leave application/allocation/encashment"""
	if ledger.transaction_type == "Leave Allocation":
		validate_leave_allocation_against_leave_application(ledger)

	expired_entry = get_previous_expiry_ledger_entry(ledger)
	frappe.db.sql(
		"""DELETE
		FROM `tabLeave Ledger Entry`
		WHERE
			`transaction_name`=%s
			OR `name`=%s""",
		(ledger.transaction_name, expired_entry),
	)


def get_previous_expiry_ledger_entry(ledger):
	"""Returns the expiry ledger entry having same creation date as the ledger entry to be cancelled"""
	creation_date = frappe.db.get_value(
		"Leave Ledger Entry",
		filters={
			"transaction_name": ledger.transaction_name,
			"is_expired": 0,
			"transaction_type": "Leave Allocation",
		},
		fieldname=["creation"],
	)

	creation_date = creation_date.strftime(DATE_FORMAT) if creation_date else ""

	return frappe.db.get_value(
		"Leave Ledger Entry",
		filters={
			"creation": ("like", creation_date + "%"),
			"employee": ledger.employee,
			"leave_type": ledger.leave_type,
			"is_expired": 1,
			"docstatus": 1,
			"is_carry_forward": 0,
		},
		fieldname=["name"],
	)


def get_remaining_leaves(allocation):
	"""Returns remaining leaves from the given allocation"""
	return frappe.db.get_value(
		"Leave Ledger Entry",
		filters={
			"employee": allocation.employee,
			"leave_type": allocation.leave_type,
			"to_date": ("<=", allocation.to_date),
			"docstatus": 1,
		},
		fieldname=["SUM(custom_time_leaves)"],
	)


def process_expired_allocation():
	"""
	Check if a carry forwarded allocation has expired and create a expiry ledger entry.
	
	Case 1: carry forwarded expiry period is set for the leave type,
	        create a separate leave expiry entry against each entry of carry forwarded and non carry forwarded leaves
	Case 2: leave type has no specific expiry period for carry forwarded leaves
	        and there is no carry forwarded leave allocation, create a single expiry against the remaining leaves.
	"""

	# fetch leave type records that has carry forwarded leaves expiry
	leave_type_records = frappe.db.get_values(
		"Leave Type", filters={"expire_carry_forwarded_leaves_after_days": (">", 0)}, fieldname=["name"]
	)

	leave_type = [record[0] for record in leave_type_records] or [""]

	# fetch non expired leave ledger entry of transaction_type allocation
	expire_allocation = frappe.db.sql(
		"""
		SELECT
			custom_time_leaves, to_date, from_date, employee, leave_type,
			is_carry_forward, transaction_name as name, transaction_type
		FROM `tabLeave Ledger Entry` l
		WHERE (NOT EXISTS
			(SELECT name
				FROM `tabLeave Ledger Entry`
				WHERE
					transaction_name = l.transaction_name
					AND transaction_type = 'Leave Allocation'
					AND name<>l.name
					AND docstatus = 1
					AND (
						is_carry_forward=l.is_carry_forward
						OR (is_carry_forward = 0 AND leave_type not in %s)
			)))
			AND transaction_type = 'Leave Allocation'
			AND to_date < %s""",
		(leave_type, today()),
		as_dict=1,
	)

	if expire_allocation:
		create_expiry_ledger_entry(expire_allocation)


def create_expiry_ledger_entry(allocations):
	"""Create ledger entry for expired allocation"""
	for allocation in allocations:
		if allocation.is_carry_forward:
			expire_carried_forward_allocation(allocation)
		else:
			expire_allocation(allocation)


@frappe.whitelist()
def expire_allocation(allocation, expiry_date=None):
	"""
	Expires non-carry forwarded allocation.
	
	allocation: Can be dict from SQL query or Leave Allocation document
	expiry_date: Date to mark leaves as expired (default: allocation.to_date)
	"""
	import json

	if isinstance(allocation, str):
		allocation = json.loads(allocation)
		allocation = frappe.get_doc("Leave Allocation", allocation["name"])
	elif isinstance(allocation, dict) and "name" not in allocation:
		# Convert from SQL result (has 'transaction_name' instead of 'name')
		allocation = frappe.get_doc("Leave Allocation", allocation.get("transaction_name") or allocation.get("name"))

	leaves = get_remaining_leaves(allocation)
	expiry_date = expiry_date if expiry_date else allocation.to_date

	# allows expired leaves entry to be created/reverted
	if leaves and flt(leaves) > 0:
		args = dict(
			custom_time_leaves=flt(leaves) * -1,  # Negative to reduce balance (in seconds)
			transaction_name=allocation.name,
			transaction_type="Leave Allocation",
			from_date=expiry_date,
			to_date=expiry_date,
			is_carry_forward=0,
			is_expired=1,
		)
		create_custom_leave_ledger_entry(allocation, args)

	frappe.db.set_value("Leave Allocation", allocation.name, "expired", 1)


def expire_carried_forward_allocation(allocation):
	"""Expires remaining leaves in the carried forward allocation"""
	from gs_customizations.overrides.hrms.leave_application.leave_application import get_leaves_for_period

	# Handle both dict and doc formats
	if isinstance(allocation, dict) and "name" not in allocation:
		allocation_name = allocation.get("transaction_name")
		allocation_doc = frappe.get_doc("Leave Allocation", allocation_name)
	else:
		allocation_name = allocation.name
		allocation_doc = allocation if hasattr(allocation, 'name') else frappe.get_doc("Leave Allocation", allocation.get("name"))

	# Get leaves taken during the allocation period (in days, convert to seconds for calculation)
	leaves_taken = get_leaves_for_period(
		allocation_doc.employee,
		allocation_doc.leave_type,
		allocation_doc.from_date,
		allocation_doc.to_date,
		skip_expired_leaves=False,
	)
	
	leaves = flt(allocation.get("custom_time_leaves", 0)) + flt(leaves_taken)

	# allow expired leaves entry to be created
	if leaves > 0:
		args = frappe._dict(
			transaction_name=allocation_name,
			transaction_type="Leave Allocation",
			custom_time_leaves=leaves * -1,  # Negative to reduce balance (in seconds)
			is_carry_forward=allocation.get("is_carry_forward", 0),
			is_expired=1,
			from_date=allocation_doc.to_date,
			to_date=allocation_doc.to_date,
		)
		create_custom_leave_ledger_entry(allocation_doc, args)


def on_doctype_update():
	frappe.db.add_index("Leave Ledger Entry", ["transaction_type", "transaction_name"])