// Copyright (c) 2026, GS and contributors
// For license information, please see license.txt

frappe.listview_settings["Food Poll"] = {
	add_fields: ["poll_ended", "total_votes"],

	get_indicator(doc) {
		if (doc.poll_ended) {
			return [__("Closed"), "green", "poll_ended,=,1"];
		}
		return [__("Open"), "orange", "poll_ended,=,0"];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Import from Matrix"), function () {
			frappe.prompt(
				[
					{
						fieldname: "matrix_link",
						fieldtype: "Small Text",
						label: __("Matrix Poll Link"),
						reqd: 1,
						description: __(
							"In Element, hover the poll message &rarr; <b>Options</b> &rarr; <b>Share</b>, then paste the copied link here."
						),
					},
				],
				function (values) {
					frappe.call({
						method: "gs_customizations.matrix.polls.import_poll",
						args: { matrix_link: values.matrix_link },
						freeze: true,
						freeze_message: __("Reading poll from Matrix..."),
						callback: function (r) {
							if (!r.message) return;
							frappe.show_alert({
								message: r.message.created
									? __("Imported {0} vote(s)", [r.message.total_votes])
									: __("Poll already recorded - refreshed it"),
								indicator: "green",
							});
							frappe.set_route("Form", "Food Poll", r.message.name);
						},
					});
				},
				__("Import Poll from Matrix"),
				__("Import")
			);
		});
	},
};
