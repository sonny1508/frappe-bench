frappe.ui.form.on("Leave Allocation", {
	refresh: function (frm) {
		if (!frm.doc.__islocal && frm.doc.leave_policy_assignment) {
			frappe.db.get_value("Leave Type", frm.doc.leave_type, "is_earned_leave", (r) => {
				if (!r?.is_earned_leave) return;
				frm.set_df_property("custom_new_time_leaves_allocated", "read_only", 1);
				frm.trigger("add_allocate_leaves_button");
			});
		}
	},

	add_allocate_leaves_button: async function (frm) {
		const { message: monthly_earned_leave } = await frappe.call({
			method: "get_monthly_earned_leave",
			doc: frm.doc,
		});

		frm.add_custom_button(
			__("Allocate Leaves"),
			function () {
				const dialog = new frappe.ui.Dialog({
					title: "Manual Leave Allocation",
					fields: [
						{
							label: "New Leaves to be Allocated",
							fieldname: "new_leaves",
							fieldtype: "Duration",
							hide_seconds: 1,
							reqd: 1,
						},
						{
							label: "From Date",
							fieldname: "from_date",
							fieldtype: "Date",
							default: frappe.datetime.get_today(),
						},
						{
							label: "To Date",
							fieldname: "to_date",
							fieldtype: "Date",
							read_only: 1,
							default: frm.doc.to_date,
						},
					],
					primary_action_label: "Allocate",
					primary_action({ new_leaves, from_date }) {
						frappe.call({
							method: "allocate_leaves_manually",
							doc: frm.doc,
							args: { new_leaves, from_date },
							callback: function (r) {
								if (!r.exc) {
									dialog.hide();
									frm.reload_doc();
								}
							},
						});
					},
				});
				dialog.fields_dict.new_leaves.set_value(monthly_earned_leave);
				dialog.fields_dict.from_date.datepicker?.update({
					minDate: frappe.datetime.str_to_obj(frm.doc.from_date),
					maxDate: frappe.datetime.str_to_obj(frm.doc.to_date),
				});

				dialog.show();
			},
			__("Actions"),
		);
	},

	employee: function (frm) {
		frm.trigger("calculate_custom_total_time_leaves_allocated");
	},

	leave_type: function (frm) {
		frm.trigger("leave_policy");
		frm.trigger("calculate_custom_total_time_leaves_allocated");
	},

	carry_forward: function (frm) {
		frm.trigger("calculate_custom_total_time_leaves_allocated");
	},

    custom_unused_time_leaves: function (frm) {
        frm.set_value(
            "custom_total_time_leaves_allocated",
            flt(frm.doc.custom_unused_time_leaves) + flt(frm.doc.custom_new_time_leaves_allocated),
        );
    },

    custom_new_time_leaves_allocated: function (frm) {
		frm.set_value(
			"custom_total_time_leaves_allocated",
			flt(frm.doc.custom_unused_time_leaves) + flt(frm.doc.custom_new_time_leaves_allocated),
		);
	},

	// leave_policy

	calculate_custom_total_time_leaves_allocated: function (frm) {
        if (cint(frm.doc.carry_forward) == 1 && frm.doc.leave_type && frm.doc.employee) {
			return frappe.call({
				method: "set_total_leaves_allocated",
				doc: frm.doc,
				callback: function () {
					frm.refresh_fields();
				},
			});
		}
        else if (cint(frm.doc.carry_forward) == 0) {
			frm.set_value("custom_unused_time_leaves", 0);
			frm.set_value("custom_total_time_leaves_allocated", flt(frm.doc.custom_new_time_leaves_allocated));
		}
	},
});

frappe.tour["Leave Allocation"] = [
	{
		fieldname: "custom_new_time_leaves_allocated",
		title: "New Time Leaves Allocated",
		description: __("Enter the number of time leaves you want to allocate for the period."),
	},
];