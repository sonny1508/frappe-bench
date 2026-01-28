frappe.ui.form.on("Leave Application", {

	make_dashboard: function (frm) {
		let leave_details;
		let lwps;

		if (frm.doc.employee) {
			frappe.call({
				method: "gs_customizations.overrides.hrms.leave_application.leave_application.get_leave_details",
				async: false,
				args: {
					employee: frm.doc.employee,
					date: frm.doc.from_date || frm.doc.posting_date,
				},
				callback: function (r) {
					if (!r.exc && r.message["leave_allocation"]) {
						leave_details = r.message["leave_allocation"];
					}
					lwps = r.message["lwps"];
				},
			});

			$("div").remove(".form-dashboard-section.custom");

			frm.dashboard.add_section(
				frappe.render_template("leave_application_dashboard", {
					data: leave_details,
				}),
				__("Allocated Leaves"),
			);
			frm.dashboard.show();

			let allowed_leave_types = Object.keys(leave_details);
			// lwps should be allowed for selection as they don't have any allocation
			allowed_leave_types = allowed_leave_types.concat(lwps);

			frm.set_query("leave_type", function () {
				return {
					filters: [["leave_type_name", "in", allowed_leave_types]],
				};
			});
		}
	},

	// reference only
	employee: function (frm) {
		frm.trigger("make_dashboard");
		frm.trigger("get_leave_balance");
		frm.trigger("set_leave_approver");
	},

	// reference only
	leave_approver: function (frm) {
		if (frm.doc.leave_approver) {
			frm.set_value("leave_approver_name", frappe.user.full_name(frm.doc.leave_approver));
		}
	},

	// reference only
	leave_type: function (frm) {
		frm.trigger("get_leave_balance");

		if (!frm.doc.custom_use_single_date && frm.doc.from_date) {
			frm.trigger("calculate_total_days");
		}

		if (frm.doc.custom_use_single_date && frm.doc.custom_from_time) {
			frm.trigger("calculate_total_time");
		}
	},

	from_date: function (frm) {
		if (!frm.doc.custom_use_single_date && frm.doc.from_date) {
			frm.set_value("custom_single_date", frm.doc.from_date);
		}

		frm.events.validate_from_to_date(frm, "from_date");
		frm.trigger("make_dashboard");
		frm.trigger("calculate_total_days");
	},

	to_date: function (frm) {
		frm.events.validate_from_to_date(frm, "to_date");
		frm.trigger("make_dashboard");
		frm.trigger("calculate_total_days");
	},

	custom_single_date: function (frm) {
		if (frm.doc.custom_use_single_date && frm.doc.custom_single_date) {
			frm.set_value("from_date", frm.doc.custom_single_date);
			frm.set_value("to_date", frm.doc.custom_single_date);
		}
		frm.trigger("get_leave_balance");
	},

	custom_from_time: function (frm) {
		// frm.events.validate_custom_from_to_time(frm, "custom_from_time");
		frm.trigger("calculate_total_time");
	},

	custom_to_time: function (frm) {
		// frm.events.validate_custom_from_to_time(frm, "custom_to_time");
		frm.trigger("calculate_total_time");
	},

	validate_custom_from_to_time: function (frm, updated_field) {
		if (!frm.doc.custom_from_time || !frm.doc.custom_to_time) return;
		if (!frm.doc.employee) return;
		
		// Fetch company working hours
		frappe.db.get_value('Employee', frm.doc.employee, 'company')
			.then(r => {
				if (r.message && r.message.company) {
					return frappe.db.get_value('Company', r.message.company, 
						['custom_start_working_hour', 'custom_end_working_hour']);
				}
			})
			.then(company_data => {
				if (company_data && company_data.message) {
					frm.events.apply_time_constraints(
						frm, 
						updated_field, 
						moment(company_data.message.custom_start_working_hour, "HH:mm:ss"),
						moment(company_data.message.custom_end_working_hour, "HH:mm:ss")
					);
				} else {
					frm.events.do_swap_if_needed(frm, updated_field);
				}
			});
	},

	apply_time_constraints: function(frm, updated_field, start_hour, end_hour) {
		if (!start_hour || !end_hour) {
			// No working hours defined, just do swap logic
			frm.events.do_swap_if_needed(frm, updated_field);
			return;
		}
		
		let custom_from_time = moment(frm.doc.custom_from_time, "HH:mm:ss");
		let custom_to_time = moment(frm.doc.custom_to_time, "HH:mm:ss");
		let adjusted = false;
		
		// Constrain custom_from_time to working hours
		if (custom_from_time < start_hour) {
			frm.set_value('custom_from_time', start_hour);
			frappe.show_alert({
				message: __("From time adjusted to working hours start: {0}", 
					[frappe.datetime.str_to_user(start_hour)]),
				indicator: "orange",
			});
			custom_from_time = start_hour;
			adjusted = true;
		} else if (custom_from_time > end_hour) {
			frm.set_value('custom_from_time', end_hour);
			frappe.show_alert({
				message: __("From time adjusted to working hours end: {0}", 
					[frappe.datetime.str_to_user(end_hour)]),
				indicator: "orange",
			});
			custom_from_time = end_hour;
			adjusted = true;
		}
		
		// Constrain custom_to_time to working hours
		if (custom_to_time < start_hour) {
			frm.set_value('custom_to_time', start_hour);
			frappe.show_alert({
				message: __("To time adjusted to working hours start: {0}", 
					[frappe.datetime.str_to_user(start_hour)]),
				indicator: "orange",
			});
			custom_to_time = start_hour;
			adjusted = true;
		} else if (custom_to_time > end_hour) {
			frm.set_value('custom_to_time', end_hour);
			frappe.show_alert({
				message: __("To time adjusted to working hours end: {0}", 
					[frappe.datetime.str_to_user(end_hour)]),
				indicator: "orange",
			});
			custom_to_time = end_hour;
			adjusted = true;
		}
		
		// After constraining, do swap logic if needed
		if 	(!adjusted) {
			setTimeout(() => {
				frm.trigger("calculate_total_time");
			}, 300);
		} 	else {
			frm.events.do_swap_if_needed(frm, updated_field);
		}
	},

	do_swap_if_needed: function(frm, updated_field) {
		const custom_from_time = moment(frm.doc.custom_from_time, "HH:mm:ss");
		const custom_to_time = moment(frm.doc.custom_to_time, "HH:mm:ss");
		
		if 	(custom_to_time < custom_from_time) {
			const other_field = updated_field === "custom_from_time" ? "custom_to_time" : "custom_from_time";
			frm.set_value(other_field, frm.doc[updated_field]);
			frappe.show_alert({
				message: __("Changing '{0}' to {1}.", [
					__(frm.fields_dict[other_field].df.label),
					frappe.datetime.str_to_user(moment(frm.doc[updated_field], "HH:mm:ss")),
				]),
				indicator: "blue",
			});
			// Recalculate after swap
			setTimeout(() => {
				frm.trigger("calculate_total_time");
			}, 300);
		} 	else {
			// Times are valid, recalculate
			frm.trigger("calculate_total_time");
		}
	},

	get_leave_balance: function (frm) {
		// First 3 conditions always required
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.employee &&
			frm.doc.leave_type
		) {
			let dateConditionMet = false;
			let dateValue, toDateValue;
			
			// Check date conditions based on custom_use_single_date
			if (frm.doc.custom_use_single_date) {
				// If using single date, check for custom_single_date field
				if (frm.doc.custom_single_date) {
					dateConditionMet = true;
					dateValue = frm.doc.custom_single_date;
					toDateValue = frm.doc.custom_single_date;
				}
			} else {
				// If not using single date, check for from_date and to_date
				if (frm.doc.from_date && frm.doc.to_date) {
					dateConditionMet = true;
					dateValue = frm.doc.from_date;
					toDateValue = frm.doc.to_date;
				}
			}
			
			// Only make the call if date condition is met
			if (dateConditionMet) {
				return frappe.call({
					method: "gs_customizations.overrides.hrms.leave_application.leave_application.get_leave_balance_on",
					args: {
						employee: frm.doc.employee,
						date: dateValue,
						to_date: toDateValue,
						leave_type: frm.doc.leave_type,
						consider_all_leaves_in_the_allocation_period: 1,
					},
					callback: function (r) {
						if (!r.exc && r.message) {
							frm.set_value("custom_leave_balance_before_application", r.message);
						} else {
							frm.set_value("custom_leave_balance_before_application", "0");
						}
					},
				});
			}
		}
	},

	calculate_total_days: function (frm) {
		if (!frm.doc.custom_use_single_date && frm.doc.from_date && frm.doc.to_date && frm.doc.employee && frm.doc.leave_type) {
			// server call is done to include holidays in leave days calculations
			return frappe.call({
				method: "gs_customizations.overrides.hrms.leave_application.leave_application.get_number_of_leave_days_in_seconds",
				args: {
					employee: frm.doc.employee,
					leave_type: frm.doc.leave_type,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
				},
				callback: function (r) {
					if (r && r.message) {
						frm.set_value("custom_total_leave_time", r.message);
						frm.trigger("get_leave_balance");
					}
				},
			});
		}
	},

	calculate_total_time: function (frm) {
		if (frm.doc.custom_use_single_date && frm.doc.custom_single_date && frm.doc.custom_from_time
			&& frm.doc.custom_to_time && frm.doc.employee && frm.doc.leave_type) {
			// server call is done to include holidays in leave days calculations
			return frappe.call({
				method: "gs_customizations.overrides.hrms.leave_application.leave_application.get_amount_of_leave_time",
				args: {
					employee: frm.doc.employee,
					// leave_type: frm.doc.leave_type,
					// custom_single_date: frm.doc.custom_single_date,
					custom_from_time: frm.doc.custom_from_time,
					custom_to_time: frm.doc.custom_to_time,
				},
				callback: function (r) {
					if (r && r.message) {
						frm.set_value("custom_total_leave_time", r.message);
						frm.trigger("get_leave_balance");
					}
				},
			});
		}
	},
});