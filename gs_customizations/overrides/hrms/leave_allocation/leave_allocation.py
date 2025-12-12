# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, formatdate, get_link_to_form, getdate

from hrms.hr.doctype.leave_allocation.leave_allocation import (
    LeaveAllocation,
    get_previous_allocation,
    OverAllocationError,
    LessAllocationError,
    validate_carry_forward,
    show_expire_leave_dialog,
)
from hrms.hr.doctype.leave_application.leave_application import get_approved_leaves_for_period
from gs_customizations.overrides.hrms.leave_ledger_entry.leave_ledger_entry import create_leave_ledger_entry
from hrms.hr.utils import (
    create_additional_leave_ledger_entry,
    get_leave_period,
    set_employee_name,
)
from hrms.hr.utils import get_monthly_earned_leave as _get_monthly_earned_leave


class CustomLeaveAllocation(LeaveAllocation):
    """
    Custom Leave Allocation - Duration fields only (seconds)
    Working hours from Company.custom_total_working_hours
    All duration fields stored in SECONDS, converted to DAYS for ledger entries
    """

    def get_working_hours_in_seconds(self):
        """Get working hours from Company (Duration field in seconds)"""
        company_doc = frappe.get_cached_doc("Company", self.company)
        if company_doc.get("custom_total_working_hours"):
            return flt(company_doc.custom_total_working_hours)
        return 28800.0  # 8 hours default

    def seconds_to_days(self, seconds):
        """Convert seconds to days"""
        if not seconds:
            return 0.0
        return flt(seconds) / self.get_working_hours_in_seconds()

    def days_to_seconds(self, days):
        """Convert days to seconds"""
        if not days:
            return 0
        return int(flt(days) * self.get_working_hours_in_seconds())

    def get_existing_leave_count(self):
        ledger_entries = frappe.get_all(
            "Leave Ledger Entry",
            filters={
                "transaction_type": "Leave Allocation",
                "transaction_name": self.name,
                "employee": self.employee,
                "company": self.company,
                "leave_type": self.leave_type,
                "is_carry_forward": 0,
                "docstatus": 1,
            },
            # leaves -> custom_time_leaves
            fields=["SUM(custom_time_leaves) as total_leaves"],
        )

        return ledger_entries[0].total_leaves if ledger_entries else 0

    @frappe.whitelist()
    def set_total_leaves_allocated(self):
        self.custom_unused_time_leaves = flt(
            get_carry_forwarded_leaves(self.employee, self.leave_type, self.from_date, self.carry_forward)
        )

        self.custom_total_time_leaves_allocated = flt(
            flt(self.custom_unused_time_leaves) + flt(self.custom_new_time_leaves_allocated)
        )

        self.limit_carry_forward_based_on_max_allowed_leaves()

        if self.carry_forward:
            self.set_carry_forwarded_leaves_in_previous_allocation()

        if (
            not self.custom_total_time_leaves_allocated
            and not frappe.db.get_value("Leave Type", self.leave_type, "is_earned_leave")
            and not frappe.db.get_value("Leave Type", self.leave_type, "is_compensatory")
        ):
            frappe.throw(_("Total leaves allocated is mandatory for Leave Type {0}").format(self.leave_type))

    def validate(self):
        """Validation using duration fields"""
        self.validate_period()
        self.validate_allocation_overlap()
        self.validate_lwp()
        set_employee_name(self)
        self.set_total_leaves_allocated()
        self.validate_leave_days_and_dates()

    def validate_leave_days_and_dates(self):
        """Run date and allocation validations"""
        self.validate_back_dated_allocation()
        self.validate_total_leaves_allocated()
        self.validate_leave_allocation_days()

    def validate_leave_allocation_days(self):
        company = frappe.db.get_value("Employee", self.employee, "company")
        leave_period = get_leave_period(self.from_date, self.to_date, company)
        max_leaves_allowed = frappe.db.get_value("Leave Type", self.leave_type, "max_leaves_allowed")

        if max_leaves_allowed > 0:
            leave_allocated_seconds = 0
            if leave_period:
                leave_allocated_seconds = get_leave_allocation_for_period(
                    self.employee,
                    self.leave_type,
                    leave_period[0].from_date,
                    leave_period[0].to_date,
                    exclude_allocation=self.name,
                )
            
            leave_allocated_seconds += flt(self.custom_new_time_leaves_allocated)
            leave_allocated_days = self.seconds_to_days(leave_allocated_seconds)
            
            if leave_allocated_days > max_leaves_allowed:
                frappe.throw(
                    _(
                        "Total allocated leaves are more than maximum allocation allowed for {0} leave type for employee {1} in the period"
                    ).format(self.leave_type, self.employee),
                    OverAllocationError,
                )

    def validate_total_leaves_allocated(self):
        """Check if allocation exceeds period days"""
        total_leaves_days = self.seconds_to_days(self.custom_total_time_leaves_allocated)
        date_difference = date_diff(self.to_date, self.from_date) + 1
        
        if date_difference < total_leaves_days:
            if frappe.db.get_value("Leave Type", self.leave_type, "allow_over_allocation"):
                frappe.msgprint(
                    _("<b>Total Leaves Allocated</b> are more than the number of days in the allocation period"),
                    indicator="orange",
                    alert=True,
                )
            else:
                frappe.throw(
                    _("<b>Total Leaves Allocated</b> are more than the number of days in the allocation period"),
                    exc=OverAllocationError,
                    title=_("Over Allocation"),
                )

    def validate_against_leave_applications(self):
        """Check against approved leaves"""
        leaves_taken = get_approved_leaves_for_period(
            self.employee, self.leave_type, self.from_date, self.to_date
        )
        total_allocated_days = self.seconds_to_days(self.custom_total_time_leaves_allocated)
        
        if flt(leaves_taken) > flt(total_allocated_days):
            if frappe.db.get_value("Leave Type", self.leave_type, "allow_negative"):
                frappe.msgprint(
                    _(
                        "Note: Total allocated leaves {0} shouldn't be less than already approved leaves {1} for the period"
                    ).format(total_allocated_days, leaves_taken)
                )
            else:
                frappe.throw(
                    _(
                        "Total allocated leaves {0} cannot be less than already approved leaves {1} for the period"
                    ).format(total_allocated_days, leaves_taken),
                    LessAllocationError,
                )

    def on_update_after_submit(self):
        if self.has_value_changed("custom_new_time_leaves_allocated"):
            self.validate_earned_leave_update()
            self.validate_against_leave_applications()

            # recalculate total leaves allocated
            self.custom_total_time_leaves_allocated = (
                flt(self.custom_unused_time_leaves) + 
                flt(self.custom_new_time_leaves_allocated)
            )
            # run required validations again since total leaves are being updated
            self.validate_leave_days_and_dates()

            leaves_to_be_added = flt(self.custom_new_time_leaves_allocated - self.get_existing_leave_count())

            args = {
                "custom_time_leaves": leaves_to_be_added,
                "from_date": self.from_date,
                "to_date": self.to_date,
                "is_carry_forward": 0,
            }
            create_leave_ledger_entry(self, args, True)
            self.db_update()

    def create_leave_ledger_entry(self, submit=True):
        if self.custom_unused_time_leaves:
            expiry_days = frappe.db.get_value(
                "Leave Type", self.leave_type, "expire_carry_forwarded_leaves_after_days"
            )
            end_date = add_days(self.from_date, expiry_days - 1) if expiry_days else self.to_date
            args = dict(
                custom_time_leaves=self.custom_unused_time_leaves,
                from_date=self.from_date,
                to_date=min(getdate(end_date), getdate(self.to_date)),
                is_carry_forward=1,
            )
            create_leave_ledger_entry(self, args, submit)
            if submit and getdate(end_date) < getdate():
                show_expire_leave_dialog(self.custom_unused_time_leaves, self.leave_type)

        args = dict(
            custom_time_leaves=self.custom_new_time_leaves_allocated,
            from_date=self.from_date,
            to_date=self.to_date,
            is_carry_forward=0,
        )
        create_leave_ledger_entry(self, args, submit)

    @frappe.whitelist()
    def allocate_leaves_manually(self, new_leaves, from_date=None):
        """Manual allocation (new_leaves in seconds)"""
        if from_date and not (getdate(self.from_date) <= getdate(from_date) <= getdate(self.to_date)):
            frappe.throw(
                _("Cannot allocate leaves outside the allocation period {0} - {1}").format(
                    frappe.bold(formatdate(self.from_date)), 
                    frappe.bold(formatdate(self.to_date))
                ),
                title=_("Invalid Dates"),
            )

        new_leaves_days = self.seconds_to_days(new_leaves)
        current_total_days = self.seconds_to_days(self.custom_total_time_leaves_allocated)
        existing_leaves = self.get_existing_leave_count()
        
        new_allocation_days = flt(current_total_days) + flt(new_leaves_days)
        new_allocation_without_cf = flt(existing_leaves) + flt(new_leaves_days)

        max_leaves_allowed = frappe.db.get_value("Leave Type", self.leave_type, "max_leaves_allowed")
        if new_allocation_days > max_leaves_allowed and max_leaves_allowed > 0:
            new_allocation_days = max_leaves_allowed

        annual_allocation = frappe.db.get_value(
            "Leave Policy Detail",
            {"parent": self.leave_policy, "leave_type": self.leave_type},
            "annual_allocation",
        )
        annual_allocation = flt(annual_allocation, 2)

        if new_allocation_days != current_total_days and new_allocation_without_cf <= annual_allocation:
            new_total_seconds = self.days_to_seconds(new_allocation_days)
            self.db_set("custom_total_time_leaves_allocated", new_total_seconds, update_modified=False)

            date = from_date or frappe.flags.current_date or getdate()
            create_additional_leave_ledger_entry(self, new_leaves_days, date)

            hours = flt(new_leaves) / 3600
            text = _("{0} hours ({1} days) were manually allocated by {2} on {3}").format(
                frappe.bold(f"{hours:.2f}"),
                frappe.bold(f"{new_leaves_days:.2f}"),
                frappe.session.user,
                frappe.bold(formatdate(date))
            )
            self.add_comment(comment_type="Info", text=text)
            
            frappe.msgprint(
                _("{0} hours ({1} days) allocated successfully").format(
                    frappe.bold(f"{hours:.2f}"),
                    frappe.bold(f"{new_leaves_days:.2f}")
                ),
                indicator="green",
                alert=True,
            )
        else:
            msg = _("Total leaves allocated cannot exceed annual allocation of {0}.").format(
                frappe.bold(_(annual_allocation))
            )
            msg += "<br><br>"
            msg += _("Reference: {0}").format(get_link_to_form("Leave Policy", self.leave_policy))
            frappe.throw(msg, title=_("Annual Allocation Exceeded"))

    @frappe.whitelist()
    def get_monthly_earned_leave(self):
        """Return monthly earned leave in seconds"""
        doj = frappe.db.get_value("Employee", self.employee, "date_of_joining")

        annual_allocation = frappe.db.get_value(
            "Leave Policy Detail",
            {"parent": self.leave_policy, "leave_type": self.leave_type},
            "annual_allocation",
        )

        frequency, rounding = frappe.db.get_value(
            "Leave Type",
            self.leave_type,
            ["earned_leave_frequency", "rounding"],
        )

        monthly_earned_days = _get_monthly_earned_leave(doj, annual_allocation, frequency, rounding)
        return self.days_to_seconds(monthly_earned_days)

# only for reference
def get_carry_forwarded_leaves(employee, leave_type, date, carry_forward=None):
	"""Returns carry forwarded leaves for the given employee"""
	unused_leaves = 0.0
	previous_allocation = get_previous_allocation(date, leave_type, employee)
	if carry_forward and previous_allocation:
		validate_carry_forward(leave_type)
		unused_leaves = get_unused_leaves(
			employee, leave_type, previous_allocation.from_date, previous_allocation.to_date
		)
		if unused_leaves:
			max_carry_forwarded_leaves = frappe.db.get_value(
				"Leave Type", leave_type, "maximum_carry_forwarded_leaves"
			)
			if max_carry_forwarded_leaves and unused_leaves > flt(max_carry_forwarded_leaves):
				unused_leaves = flt(max_carry_forwarded_leaves)

	return unused_leaves


def get_unused_leaves(employee, leave_type, from_date, to_date):
	"""Returns unused leaves between the given period while skipping leave allocation expiry"""
	leaves = frappe.get_all(
		"Leave Ledger Entry",
		filters={
			"employee": employee,
			"leave_type": leave_type,
			"from_date": (">=", from_date),
			"to_date": ("<=", to_date),
		},
		or_filters={"is_expired": 0, "is_carry_forward": 1},
        # leaves -> custom_time_leaves
		fields=["sum(custom_time_leaves) as leaves"],
	)
	return flt(leaves[0]["leaves"])


def get_leave_allocation_for_period(employee, leave_type, from_date, to_date, exclude_allocation=None):
    from frappe.query_builder.functions import Sum

    Allocation = frappe.qb.DocType("Leave Allocation")
    return (
        frappe.qb.from_(Allocation)
        .select(Sum(Allocation.custom_total_time_leaves_allocated).as_("custom_total_allocated_time_leaves"))
        .where(
            (Allocation.employee == employee)
            & (Allocation.leave_type == leave_type)
            & (Allocation.docstatus == 1)
            & (Allocation.name != exclude_allocation)
            & (
                (Allocation.from_date.between(from_date, to_date))
                | (Allocation.to_date.between(from_date, to_date))
                | ((Allocation.from_date < from_date) & (Allocation.to_date > to_date))
            )
        )
    ).run()[0][0] or 0.0