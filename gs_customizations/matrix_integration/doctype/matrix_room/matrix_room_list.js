// Copyright (c) 2026, GS and contributors
// For license information, please see license.txt

const MATRIX_ROOM_STATUS_COLORS = {
	OK: "green",
	"Needs Admin": "orange",
	Error: "red",
	"Not Managed": "gray",
};

frappe.listview_settings["Matrix Room"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		return [__(doc.status), MATRIX_ROOM_STATUS_COLORS[doc.status] || "gray", `status,=,${doc.status}`];
	},
};
