// Copyright (c) 2026, GS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Matrix Settings", {
	setup(frm) {
		// Only root spaces can be managed — everything inside them comes along
		frm.set_query("managed_root_spaces", () => ({
			filters: { room_type: "Space", parent_space: ["is", "not set"] },
		}));
	},

	onload(frm) {
		frappe.realtime.off("matrix_space_sync");
		frappe.realtime.on("matrix_space_sync", (summary) => {
			frappe.show_alert({
				message: __("Space sync finished: {0} rooms, {1} need an admin, {2} with errors", [
					summary.rooms, summary.needs_admin, summary.errors,
				]),
				indicator: summary.errors || summary.needs_admin ? "orange" : "green",
			}, 10);
			frm.reload_doc();
		});
	},

	refresh(frm) {
		frm.add_custom_button(__("Discover Root Spaces"), function () {
			frappe.call({
				method: "discover_root_spaces",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Reading spaces from the server..."),
				callback: function (r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Root Spaces"),
							indicator: "green",
							message: __("Found {0} root spaces ({1} new). Pick the ones to manage under Managed Root Spaces.", [
								r.message.found, r.message.new,
							]),
						});
					}
				},
			});
		}, __("Spaces"));

		frm.add_custom_button(__("Sync Now"), function () {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save first — the sync uses the saved steward list and root spaces."));
				return;
			}
			frappe.call({
				method: "sync_spaces_now",
				doc: frm.doc,
				callback: function () {
					frappe.show_alert({
						message: __("Space sync started. This page refreshes when it finishes."),
						indicator: "blue",
					});
				},
			});
		}, __("Spaces"));

		frm.add_custom_button(__("Rooms Needing Attention"), function () {
			frappe.set_route("List", "Matrix Room", { status: ["in", ["Needs Admin", "Error"]] });
		}, __("Spaces"));

		// Test Connection button in Bot Configuration section
		frm.add_custom_button(__("Test Connection"), function () {
			frappe.call({
				method: "test_connection",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Testing connection..."),
				callback: function (r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Connection Successful"),
							indicator: "green",
							message: __("Bot identity: {0}", [r.message.user_id || JSON.stringify(r.message)]),
						});
					}
				},
			});
		}, __("Bot"));

		// Provision DM Rooms button
		frm.add_custom_button(__("Provision DM Rooms"), function () {
			frappe.confirm(
				__("This will provision Matrix DM rooms for rows in the table that don't have a Room ID yet. Existing rooms in Matrix will be detected and reused. Continue?"),
				function () {
					frappe.call({
						method: "provision_all_dm_rooms",
						doc: frm.doc,
						freeze: true,
						freeze_message: __("Provisioning rooms... This may take a while."),
						callback: function (r) {
							if (r.message) {
								frappe.msgprint({
									title: __("Provisioning Complete"),
									indicator: "green",
									message: __(
										"Provisioned: {0}, Skipped: {1}, Failed: {2}",
										[r.message.provisioned || 0, r.message.skipped || 0, r.message.failed || 0]
									),
								});
								frm.reload_doc();
							}
						},
					});
				}
			);
		}, __("Rooms"));

		// Send Test Message button
		frm.add_custom_button(__("Send Test Message"), function () {
			frappe.call({
				method: "send_test_message",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Sending test message..."),
				callback: function () {
					frappe.show_alert({
						message: __("Test message sent!"),
						indicator: "green",
					});
				},
			});
		}, __("Dev"));

		// Clean Empty Rooms button
		if (frm.doc.bot_is_admin) {
			frm.add_custom_button(__("Clean Empty Rooms"), function () {
				frappe.call({
					method: "scan_empty_rooms",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Scanning for empty rooms..."),
					callback: function (r) {
						let rooms = r.message || [];
						if (rooms.length === 0) {
							frappe.msgprint(__("No empty rooms found."));
							return;
						}

						let room_ids = rooms.map((r) => r.room_id);

						frappe.confirm(
							__(
								"Found {0} empty rooms (named 'Empty room' with 1 or fewer members). Delete them all?",
								[rooms.length]
							),
							function () {
								frappe.call({
									method: "delete_empty_rooms",
									doc: frm.doc,
									args: { room_ids: room_ids },
									freeze: true,
									freeze_message: __("Deleting {0} rooms...", [room_ids.length]),
									callback: function (r) {
										if (r.message) {
											frappe.msgprint({
												title: __("Cleanup Complete"),
												indicator: "green",
												message: __(
													"Deleted: {0}, Failed: {1}",
													[r.message.deleted || 0, r.message.failed || 0]
												),
											});
										}
									},
								});
							}
						);
					},
				});
			}, __("Admin"));
		}
	},
});
