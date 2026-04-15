/**
 * Timesheet Check-in Enforcer
 * ===========================
 *
 * Client-side enforcement for the Daily Timesheet Check-in feature.
 *
 * Behavior:
 *   - On every SPA route change, if `frappe.boot.timesheet_checkin.enforce` is
 *     true, redirect the user to /app/timesheet-checkin (unless they're on an
 *     allowlisted route like timesheet-checkin or a Timesheet form).
 *   - On page ready, set a one-shot setTimeout for the company's
 *     `end_working_hour`. When it fires, refresh the check-in status with
 *     include_today=1 and redirect if today is unfilled.
 *
 * Zero-impact guarantee: if `frappe.boot.timesheet_checkin` is missing or
 * `enforce=false`, this script is a no-op. The opt-in flag on Employee
 * controls whether the backend ever returns enforce=true.
 */

(function () {
	"use strict";

	// Routes where the user is allowed to stay even when enforcement is active.
	// These include the check-in page itself and Timesheet forms/list.
	function is_allowed_route() {
		const route = frappe.get_route() || [];
		if (!route.length) return false;
		const first = String(route[0] || "").toLowerCase();
		if (first === "timesheet-checkin") return true;
		// Timesheet form/list/new (route[0] is "Form"/"List"/"new" and route[1] is "Timesheet")
		const second = String(route[1] || "").toLowerCase();
		if (second === "timesheet") return true;
		if (second === "leave application") return true;
		// Also allow direct navigation with route[0] == "Timesheet"
		if (first === "timesheet") return true;
		if (first === "leave application") return true;
		return false;
	}

	function should_enforce() {
		const checkin = frappe.boot && frappe.boot.timesheet_checkin;
		if (!checkin) return false;
		if (!checkin.enforce) return false;
		if (!checkin.missing_days || !checkin.missing_days.length) return false;
		return true;
	}

	function redirect_to_checkin() {
		if (is_allowed_route()) return;
		frappe.set_route("timesheet-checkin");
	}

	// --- Route-change enforcement -----------------------------------------
	function install_route_guard() {
		if (!frappe.router || !frappe.router.on) return;
		frappe.router.on("change", function () {
			if (should_enforce()) {
				redirect_to_checkin();
			}
		});
	}

	// --- End-of-day timer -------------------------------------------------
	let eod_timer_id = null;

	function setup_eod_timer() {
		const checkin = frappe.boot && frappe.boot.timesheet_checkin;
		if (!checkin || !checkin.end_working_hour) return;
		// If already enforcing (past days missing), no need for EOD timer
		if (should_enforce()) return;

		const parts = String(checkin.end_working_hour).split(":").map(Number);
		const h = parts[0] || 0;
		const m = parts[1] || 0;
		const s = parts[2] || 0;

		const eod = new Date();
		eod.setHours(h, m, s, 0);

		const ms_until = eod.getTime() - Date.now();

		if (eod_timer_id) {
			clearTimeout(eod_timer_id);
			eod_timer_id = null;
		}

		if (ms_until <= 0) {
			// Already past end-of-day — trigger immediately
			trigger_eod_check();
		} else {
			eod_timer_id = setTimeout(trigger_eod_check, ms_until);
		}
	}

	function trigger_eod_check() {
		frappe.call({
			method: "gs_customizations.api.get_timesheet_checkin_status",
			args: { include_today: 1 },
			callback: function (r) {
				if (r && r.message) {
					frappe.boot.timesheet_checkin = r.message;
					if (should_enforce()) {
						redirect_to_checkin();
					}
				}
			},
		});
	}

	// --- Initialize -------------------------------------------------------
	$(document).on("app_ready", function () {
		install_route_guard();
		setup_eod_timer();

		// Initial check on load (for users already behind on their timesheets)
		if (should_enforce()) {
			// Defer one tick so the router is ready
			setTimeout(redirect_to_checkin, 0);
		}
	});

	// Fallback in case app_ready was already fired
	$(function () {
		if (frappe.router && frappe.router.on && !window.__gs_checkin_installed) {
			window.__gs_checkin_installed = true;
			install_route_guard();
			setup_eod_timer();
			if (should_enforce()) {
				setTimeout(redirect_to_checkin, 0);
			}
		}
	});
})();
