frappe.ui.form.on("Timesheet", {
	setup: function (frm) {
		frappe.require("/assets/erpnext/js/projects/timer.js");

		frm.ignore_doctypes_on_cancel_all = ["Sales Invoice"];

		frm.fields_dict.employee.get_query = function () {
			return {
				filters: {
					status: "Active",
				},
			};
		};

		frm.fields_dict["time_logs"].grid.get_field("task").get_query = function (frm, cdt, cdn) {
			var child = locals[cdt][cdn];
			return {
				filters: {
					project: child.project,
					status: ["!=", "Cancelled"],
					// is_group: 0,
				},
			};
		};

		frm.fields_dict["time_logs"].grid.get_field("project").get_query = function () {
			return {
				filters: {
					company: frm.doc.company,
				},
			};
		};
	}
});