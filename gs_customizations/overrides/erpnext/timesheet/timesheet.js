frappe.ui.form.on("Timesheet", {
	setup: function (frm) {
		frappe.require("/assets/erpnext/js/projects/timer.js");

		frm.ignore_doctypes_on_cancel_all = ["Sales Invoice"];

		frm.fields_dict.employee.get_query = function () {
			return {
				filters: { status: "Active" },
			};
		};

		frm.fields_dict["time_logs"].grid.get_field("task").get_query = function (frm, cdt, cdn) {
			var child = locals[cdt][cdn];
			return {
				filters: {
					project: child.project,
					status: ["!=", "Cancelled"],
				},
			};
		};

		frm.fields_dict["time_logs"].grid.get_field("project").get_query = function () {
			return {
				filters: { company: frm.doc.company },
			};
		};
	},

	refresh: function (frm) {
		_store_original_dates(frm);
		// Always re-fetch context on refresh so leave data is never stale
		// (leave approved after form open, save-triggered refreshes, etc.)
		frm._ts_ctx = null;
		if (frm.doc.employee && frm.doc.company) {
			_fetch_validation_context(frm);
		} else {
			_render_daily_summary(frm);
		}
	},

	employee: function (frm) {
		if (frm.doc.employee && frm.doc.company) {
			_fetch_validation_context(frm);
		}
	},

	validate: function (frm) {
		_validate_all_rules(frm);
	},

	time_logs_remove: function (frm) {
		_render_daily_summary(frm);
	},

	after_save: function (frm) {
		if (!frappe.boot || !frappe.boot.timesheet_checkin) return;
		if (
			frappe.boot.timesheet_checkin.employee == null &&
			frappe.boot.timesheet_checkin.enforce === false
		) {
			return;
		}
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
	},
});

// ---- Timesheet Detail child table events ----

frappe.ui.form.on("Timesheet Detail", {
	time_logs_add: function (frm, cdt, cdn) {
		_auto_set_from_time(frm, cdt, cdn);
		_render_daily_summary(frm);
	},

	from_time: function (frm, cdt, cdn) {
		_validate_row_date_range(frm, cdt, cdn);
		_validate_row_leave_block(frm, cdt, cdn);
		_render_daily_summary(frm);
	},

	hours: function (frm, cdt, cdn) {
		_validate_next_day_overflow(frm, cdt, cdn);
		_validate_daily_hours_for_date(frm, cdt, cdn);
		_render_daily_summary(frm);
	},

	activity_type: function (frm, cdt, cdn) {
		_toggle_free_fields(frm, cdt, cdn);
	},

	form_render: function (frm, cdt, cdn) {
		_toggle_free_fields(frm, cdt, cdn);
	},
});

// ---- Fetch validation context from server ----

function _fetch_validation_context(frm) {
	frappe.call({
		method: "gs_customizations.overrides.erpnext.timesheet.timesheet.get_timesheet_validation_context",
		args: { employee: frm.doc.employee, company: frm.doc.company },
		callback: function (r) {
			if (r && r.message) {
				frm._ts_ctx = r.message;
				_render_daily_summary(frm);
			}
		},
	});
}

// ---- Rule 4: Auto-set from_time on new row ----

function _auto_set_from_time(frm, cdt, cdn) {
	if (!frm._ts_ctx) return;

	var row = locals[cdt][cdn];
	var start_time = frm._ts_ctx.start_working_hour || "09:00:00";
	var existing = (frm.doc.time_logs || []).filter(function (r) {
		return r.name !== row.name && r.from_time;
	});

	var new_from_time;
	if (existing.length > 0) {
		var last = existing[existing.length - 1];
		if (last.to_time) {
			new_from_time = last.to_time;
		} else {
			var last_date = last.from_time.split(" ")[0];
			new_from_time = last_date + " " + start_time;
		}
	} else {
		new_from_time = frappe.datetime.get_today() + " " + start_time;
	}

	var target_date = new_from_time.split(" ")[0];
	var leave_hours = frm._ts_ctx.leave_data[target_date] || 0;
	if (leave_hours >= frm._ts_ctx.company_working_hours) {
		return;
	}

	frappe.model.set_value(cdt, cdn, "from_time", new_from_time);
}

// ---- Date range check (±6 days, checkin-enabled only) ----

function _validate_row_date_range(frm, cdt, cdn) {
	if (!frm._ts_ctx || !frm._ts_ctx.checkin_enabled) return;

	var row = locals[cdt][cdn];
	if (!row.from_time) return;

	var row_date = row.from_time.split(" ")[0];
	var today = frappe.datetime.get_today();
	var diff = frappe.datetime.get_diff(today, row_date);

	if (Math.abs(diff) > 6) {
		frappe.msgprint({
			title: __("Invalid Date"),
			indicator: "red",
			message: __(
				"Row {0}: Date {1} is outside the allowed ±6 day window. Please choose a date within 6 days of today.",
				[row.idx, row_date]
			),
		});
		frappe.model.set_value(cdt, cdn, "from_time", "");
	}
}

// ---- Rule 2: Full-day leave blocks entry ----

function _validate_row_leave_block(frm, cdt, cdn) {
	if (!frm._ts_ctx) return;

	var row = locals[cdt][cdn];
	if (!row.from_time) return;

	var row_date = row.from_time.split(" ")[0];
	var leave_hours = frm._ts_ctx.leave_data[row_date];
	if (leave_hours === undefined) return;

	if (leave_hours >= frm._ts_ctx.company_working_hours) {
		frappe.msgprint({
			title: __("Full-Day Leave"),
			indicator: "red",
			message: __(
				"You have a full-day leave on {0}. You cannot log timesheet hours on this date.",
				[row_date]
			),
		});
		frappe.model.set_value(cdt, cdn, "from_time", "");
	}
}

// ---- Next-day overflow check ----

function _validate_next_day_overflow(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	if (!row.from_time || !row.hours) return;

	var from_m = moment(row.from_time);
	var to_m = from_m.clone().add(row.hours, "hours");

	if (from_m.format("YYYY-MM-DD") !== to_m.format("YYYY-MM-DD")) {
		frappe.msgprint({
			title: __("Hours Overflow"),
			indicator: "orange",
			message: __(
				"Row {0}: Working hours exceed into the next day. " +
					"Start time {1} plus {2}h goes past midnight. " +
					"Please reduce the hours or adjust the start time.",
				[row.idx, from_m.format("HH:mm"), row.hours]
			),
		});
	}
}

// ---- Rules 1 & 2: Daily hours check on hours change ----

function _validate_daily_hours_for_date(frm, cdt, cdn) {
	if (!frm._ts_ctx) return;

	var row = locals[cdt][cdn];
	if (!row.from_time || !row.hours) return;

	var row_date = row.from_time.split(" ")[0];

	var total = 0;
	(frm.doc.time_logs || []).forEach(function (r) {
		if (r.from_time && r.from_time.split(" ")[0] === row_date) {
			total += flt(r.hours);
		}
	});

	var leave_hours = frm._ts_ctx.leave_data[row_date] || 0;
	var max_hours = frm._ts_ctx.company_working_hours - leave_hours;

	if (total > max_hours + 0.01) {
		var msg;
		if (leave_hours > 0) {
			msg = __(
				"Total hours on {0} is {1}h, but the maximum allowed is {2}h ({3}h working hours minus {4}h leave).",
				[
					row_date,
					total.toFixed(2),
					max_hours.toFixed(2),
					frm._ts_ctx.company_working_hours.toFixed(2),
					leave_hours.toFixed(2),
				]
			);
		} else {
			msg = __(
				"Total hours on {0} is {1}h, which exceeds the maximum working hours of {2}h.",
				[row_date, total.toFixed(2), frm._ts_ctx.company_working_hours.toFixed(2)]
			);
		}
		frappe.msgprint({ title: __("Hours Exceeded"), indicator: "orange", message: msg });
	}
}

// ---- Validate all rules on save ----

function _validate_all_rules(frm) {
	var today = frappe.datetime.get_today();
	var date_hours = {};
	var valid = true;

	(frm.doc.time_logs || []).forEach(function (row) {
		if (!valid) return;
		if (!row.from_time) return;

		var row_date = row.from_time.split(" ")[0];

		// Date restriction: only for checkin-enabled employees, only for new/changed dates
		if (frm._ts_ctx && frm._ts_ctx.checkin_enabled) {
			var orig_date = (frm._original_row_dates || {})[row.name];
			var is_new_or_changed = !orig_date || orig_date !== row_date;

			if (is_new_or_changed) {
				var diff = frappe.datetime.get_diff(today, row_date);
				if (Math.abs(diff) > 6) {
					frappe.msgprint({
						title: __("Invalid Date"),
						indicator: "red",
						message: __(
							"Row {0}: Date {1} is outside the allowed ±6 day window. You can only log time within 6 days of today.",
							[row.idx, row_date]
						),
					});
					valid = false;
					return;
				}
			}
		}

		// Next-day overflow
		if (row.hours) {
			var from_m = moment(row.from_time);
			var to_m = from_m.clone().add(row.hours, "hours");
			if (from_m.format("YYYY-MM-DD") !== to_m.format("YYYY-MM-DD")) {
				frappe.msgprint({
					title: __("Hours Overflow"),
					indicator: "red",
					message: __(
						"Row {0}: Working hours exceed into the next day. " +
							"Start time {1} plus {2}h goes past midnight.",
						[row.idx, from_m.format("HH:mm"), row.hours]
					),
				});
				valid = false;
				return;
			}
		}

		date_hours[row_date] = (date_hours[row_date] || 0) + flt(row.hours);
	});

	if (!valid) {
		frappe.validated = false;
		return;
	}

	// Rules 1 & 2 need context
	if (!frm._ts_ctx) return;

	for (var date_str in date_hours) {
		var total = date_hours[date_str];
		var leave_hours = frm._ts_ctx.leave_data[date_str] || 0;

		if (leave_hours >= frm._ts_ctx.company_working_hours) {
			frappe.msgprint({
				title: __("Full-Day Leave"),
				indicator: "red",
				message: __(
					"You have a full-day leave on {0}. You cannot log timesheet hours on this date.",
					[date_str]
				),
			});
			frappe.validated = false;
			return;
		}

		var max_hours = frm._ts_ctx.company_working_hours - leave_hours;
		if (total > max_hours + 0.01) {
			var msg;
			if (leave_hours > 0) {
				msg = __(
					"Total hours on {0} is {1}h, but the maximum allowed is {2}h ({3}h working hours minus {4}h leave).",
					[
						date_str,
						total.toFixed(2),
						max_hours.toFixed(2),
						frm._ts_ctx.company_working_hours.toFixed(2),
						leave_hours.toFixed(2),
					]
				);
			} else {
				msg = __(
					"Total hours on {0} is {1}h, which exceeds the maximum working hours of {2}h.",
					[date_str, total.toFixed(2), frm._ts_ctx.company_working_hours.toFixed(2)]
				);
			}
			frappe.msgprint({ title: __("Hours Exceeded"), indicator: "red", message: msg });
			frappe.validated = false;
			return;
		}
	}
}

// ---- Daily Hours Summary rendering ----

function _get_timesheet_monday(frm) {
	// Determine Monday of the timesheet's week.
	if (frm.doc.start_date) {
		return moment(frm.doc.start_date).startOf("isoWeek").format("YYYY-MM-DD");
	}
	var earliest = null;
	(frm.doc.time_logs || []).forEach(function (row) {
		if (row.from_time) {
			var d = row.from_time.split(" ")[0];
			if (!earliest || d < earliest) earliest = d;
		}
	});
	if (earliest) {
		return moment(earliest).startOf("isoWeek").format("YYYY-MM-DD");
	}
	return moment().startOf("isoWeek").format("YYYY-MM-DD");
}

function _render_daily_summary(frm) {
	var wrapper = frm.fields_dict.custom_daily_hours_summary;
	if (!wrapper || !wrapper.$wrapper) return;

	var has_ctx = !!frm._ts_ctx;
	var week_monday = _get_timesheet_monday(frm);

	// Collect logged hours per date from time_logs
	var date_hours = {};
	(frm.doc.time_logs || []).forEach(function (row) {
		if (!row.from_time) return;
		var date = row.from_time.split(" ")[0];
		date_hours[date] = (date_hours[date] || 0) + flt(row.hours);
	});

	// Always show Mon–Fri of the week, plus any extra logged dates outside that range
	var date_set = {};
	for (var i = 0; i < 5; i++) {
		date_set[moment(week_monday).add(i, "days").format("YYYY-MM-DD")] = true;
	}
	for (var d in date_hours) {
		date_set[d] = true;
	}
	var dates = Object.keys(date_set).sort();

	var grand_total = 0;
	var rows_html = "";

	dates.forEach(function (date) {
		var leave = has_ctx ? (frm._ts_ctx.leave_data[date] || 0) : 0;
		var max_raw = has_ctx ? frm._ts_ctx.company_working_hours : 0;
		var submitted = has_ctx ? ((frm._ts_ctx.submitted_hours || {})[date] || 0) : 0;
		var effective_available = has_ctx ? max_raw - leave - submitted : 0;

		// Hide dates fully consumed by leave + submitted hours from other timesheets
		if (has_ctx && effective_available <= 0.01) {
			return;
		}

		var day_name = moment(date).format("dddd");
		var logged = date_hours[date] || 0;
		grand_total += logged;

		var available_display = has_ctx ? effective_available.toFixed(0) + "h" : "—";
		if (has_ctx) {
			var notes = [];
			if (leave > 0) notes.push(leave.toFixed(0) + "h leave");
			if (submitted > 0) notes.push(submitted.toFixed(0) + "h submitted");
			if (notes.length) {
				available_display += " <span class='text-muted'>(" + notes.join(", ") + ")</span>";
			}
		}

		var row_style = "";
		if (has_ctx && logged > effective_available + 0.01) {
			row_style = ' style="color: var(--red-500);"';
		}

		rows_html +=
			"<tr" + row_style + ">" +
			"<td>" + date + "</td>" +
			"<td>" + day_name + "</td>" +
			"<td class='text-right'>" + logged.toFixed(0) + "h</td>" +
			"<td class='text-right'>" + available_display + "</td>" +
			"</tr>";
	});

	var html =
		'<div style="margin: 10px 0 15px;">' +
		'<h5 class="text-muted" style="margin-bottom: 0px;">' + __("Daily Hours Summary") + "</h5>" +
		'<table class="table table-bordered" style="max-width: 840px; font-size: 14px; margin-bottom: 0;">' +
		"<thead>" +
		'<tr style="background: var(--subtle-fg);">' +
		"<th>" + __("Date") + "</th>" +
		"<th>" + __("Day") + "</th>" +
		'<th class="text-right">' + __("Logged") + "</th>" +
		'<th class="text-right">' + __("Available") + "</th>" +
		"</tr>" +
		"</thead>" +
		"<tbody>" + rows_html + "</tbody>" +
		"<tfoot>" +
		'<tr style="font-weight: bold;">' +
		'<td colspan="2">' + __("Total") + "</td>" +
		'<td class="text-right">' + grand_total.toFixed(0) + "h</td>" +
		"<td></td>" +
		"</tr>" +
		"</tfoot>" +
		"</table>" +
		"</div>";

	wrapper.$wrapper.html(html);
}

// ---- Store original row dates for detecting new/changed dates ----

function _store_original_dates(frm) {
	frm._original_row_dates = {};
	(frm.doc.time_logs || []).forEach(function (row) {
		if (row.from_time) {
			frm._original_row_dates[row.name] = row.from_time.split(" ")[0];
		}
	});
}

// ---- Toggle read-only on project/task fields for Free/Documents activity ----

function _toggle_free_fields(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	var is_free = row.activity_type === "Free";
	var fields = ["project", "project_name", "task", "custom_task_name", "custom_task_type"];
	fields.forEach(function (field) {
		frappe.meta.get_docfield("Timesheet Detail", field, cdn).read_only = is_free ? 1 : 0;
	});
	frm.refresh_field("time_logs");
}
