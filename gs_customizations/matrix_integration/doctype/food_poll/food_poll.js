// Copyright (c) 2026, GS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Food Poll", {
	refresh(frm) {
		frm.add_custom_button(__("Fetch from Matrix"), function () {
			if (!frm.doc.matrix_link && !frm.doc.poll_event_id) {
				frappe.msgprint({
					title: __("No Poll Link"),
					indicator: "orange",
					message: __(
						"Paste the poll's link from Element into <b>Matrix Source &rarr; Matrix Poll Link</b> first."
					),
				});
				return;
			}

			frappe.call({
				method: "fetch_from_matrix",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Reading poll from Matrix..."),
				callback: function (r) {
					if (!r.message) return;
					let msg = __("{0} votes and {1} options read from Matrix.", [
						r.message.matrix_votes || 0,
						r.message.options || 0,
					]);
					if (r.message.manual_votes) {
						msg += " " + __("{0} manually added votes kept.", [r.message.manual_votes]);
					}
					if (r.message.unresolved) {
						msg +=
							"<br><br>" +
							__("{0} voters could not be matched to an Employee record.", [
								r.message.unresolved,
							]);
					}
					frappe.msgprint({
						title: __("Synced"),
						indicator: "green",
						message: msg,
					});
					frm.reload_doc();
				},
			});
		});

		frm.trigger("set_option_suggestions");
	},

	// Offer the poll's own options when typing a vote row, so late DM'd votes
	// spell menu items exactly the same way the poll did.
	set_option_suggestions(frm) {
		let options = (frm.doc.options || [])
			.map((o) => o.option_text)
			.filter((t) => t);
		let grid = frm.fields_dict.votes && frm.fields_dict.votes.grid;
		if (!grid || !grid.update_docfield_property) return;
		grid.update_docfield_property("option_text", "options", options);
	},

	options_on_form_rendered(frm) {
		frm.trigger("set_option_suggestions");
	},
});

frappe.ui.form.on("Food Poll Option", {
	option_text(frm) {
		frm.trigger("set_option_suggestions");
	},
	options_remove(frm) {
		frm.trigger("set_option_suggestions");
	},
});
