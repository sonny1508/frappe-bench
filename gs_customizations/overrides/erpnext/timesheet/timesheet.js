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
	},

	after_save: function (frm) {
		// Refresh the Timesheet Check-in status in frappe.boot so the
		// enforcer JS picks up the change without a full page reload.
		if (!frappe.boot || !frappe.boot.timesheet_checkin) return;
		// Only bother calling if the feature is enabled for this user
		// (otherwise enforce will always be false and this is a waste).
		if (
			frappe.boot.timesheet_checkin.employee == null &&
			frappe.boot.timesheet_checkin.enforce === false
		) {
			return;
		}
		// Match the checkin page's logic: only include today if past EOD
		var include_today = 0;
		var checkin = frappe.boot.timesheet_checkin;
		if (checkin && checkin.end_working_hour) {
			var parts = String(checkin.end_working_hour).split(":").map(Number);
			var eod = new Date();
			eod.setHours(parts[0] || 0, parts[1] || 0, parts[2] || 0, 0);
			if (Date.now() >= eod.getTime()) {
				include_today = 1;
			}
		}
		frappe.call({
			method: "gs_customizations.api.get_timesheet_checkin_status",
			args: { include_today: include_today },
			callback: function (r) {
				if (r && r.message) {
					frappe.boot.timesheet_checkin = r.message;
				}
			},
		});
	}
});