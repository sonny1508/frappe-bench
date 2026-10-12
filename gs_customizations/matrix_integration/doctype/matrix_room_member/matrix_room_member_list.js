// Copyright (c) 2026, GS and contributors
// For license information, please see license.txt

const MATRIX_MEMBERSHIP_COLORS = {
	Joined: "green",
	Invited: "orange",
	"Not Joined": "orange",
	Left: "gray",
	Banned: "red",
};

frappe.listview_settings["Matrix Room Member"] = {
	add_fields: ["membership", "last_error", "enforce"],
	get_indicator(doc) {
		if (doc.last_error) {
			return [__("Error"), "red", "last_error,is,set"];
		}
		if (!doc.enforce) {
			return [__("Not Enforced"), "gray", "enforce,=,0"];
		}
		if (!doc.membership) {
			return [__("Not Synced"), "gray", "membership,is,not set"];
		}
		return [
			__(doc.membership),
			MATRIX_MEMBERSHIP_COLORS[doc.membership] || "gray",
			`membership,=,${doc.membership}`,
		];
	},
};
