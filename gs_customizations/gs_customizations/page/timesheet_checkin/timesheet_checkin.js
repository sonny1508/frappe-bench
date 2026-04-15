/**
 * Timesheet Check-in Page
 * =======================
 *
 * Shown to employees who have unfilled timesheets for the current week.
 * Renders a friendly card-based layout listing each missing day.
 */

frappe.pages["timesheet-checkin"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Daily Timesheet Check-in"),
		single_column: true,
	});

	const $container = $(`
		<div class="gs-checkin-wrapper">
			<div class="gs-checkin-header">
				<h2 class="gs-checkin-greeting"></h2>
				<p class="gs-checkin-subtitle text-muted"></p>
			</div>
			<div class="gs-checkin-days"></div>
			<div class="gs-checkin-actions">
				<button class="btn btn-primary gs-checkin-refresh">
					${frappe.utils.icon("refresh", "sm")} ${__("Check Again")}
				</button>
				<button class="btn btn-default gs-checkin-leave" style="margin-left: 8px;">
					${__("Leave Application")}
				</button>
			</div>
			<div class="gs-checkin-success" style="display: none;">
				<div class="text-center" style="padding: 60px 20px;">
					<div style="font-size: 64px;">✓</div>
					<h3>${__("All caught up!")}</h3>
					<p class="text-muted">${__("Your timesheets are complete. Redirecting you to the desk...")}</p>
				</div>
			</div>
		</div>
	`).appendTo(page.main);

	// Inline styles (kept local to avoid adding another CSS file to includes)
	$("<style>").text(`
		.gs-checkin-wrapper { max-width: 820px; margin: 0 auto; padding: 24px 16px; }
		.gs-checkin-header { margin-bottom: 28px; }
		.gs-checkin-greeting { margin: 0 0 8px 0; font-weight: 600; }
		.gs-checkin-subtitle { margin: 0; font-size: 14px; }
		.gs-checkin-days { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
		.gs-checkin-card {
			background: var(--card-bg, #fff);
			border: 1px solid var(--border-color, #e2e6e9);
			border-radius: 10px;
			padding: 18px 22px;
			display: flex;
			align-items: center;
			justify-content: space-between;
			transition: box-shadow 0.15s ease, transform 0.15s ease;
		}
		.gs-checkin-card:hover {
			box-shadow: 0 2px 8px rgba(0,0,0,0.06);
		}
		.gs-checkin-card-info { flex: 1; min-width: 0; }
		.gs-checkin-card-date { font-weight: 600; font-size: 16px; margin-bottom: 4px; }
		.gs-checkin-card-hours {
			font-size: 13px;
			color: var(--text-muted, #6c757d);
		}
		.gs-checkin-card-hours .shortfall {
			color: var(--red-500, #e24c4b);
			font-weight: 500;
		}
		.gs-checkin-card-leave-note {
			font-size: 12px;
			color: var(--text-muted, #6c757d);
			margin-top: 4px;
			font-style: italic;
		}
		.gs-checkin-card-action { margin-left: 16px; }
		.gs-checkin-actions { text-align: center; }
		.gs-checkin-empty {
			text-align: center;
			padding: 40px 20px;
			color: var(--text-muted, #6c757d);
		}
	`).appendTo("head");

	page.$container = $container;
	page.refresh_status = refresh_status.bind(page);

	page.$container.find(".gs-checkin-refresh").on("click", function () {
		page.refresh_status();
	});

	page.$container.find(".gs-checkin-leave").on("click", function () {
		frappe.set_route("List", "Leave Application");
	});
};

frappe.pages["timesheet-checkin"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	if (page && page.refresh_status) {
		page.refresh_status();
	}
};

function refresh_status() {
	const page = this;
	const $c = page.$container;

	// Determine include_today flag based on current time vs end_working_hour
	let include_today = 0;
	const checkin = frappe.boot && frappe.boot.timesheet_checkin;
	if (checkin && checkin.end_working_hour) {
		const parts = String(checkin.end_working_hour).split(":").map(Number);
		const eod = new Date();
		eod.setHours(parts[0] || 0, parts[1] || 0, parts[2] || 0, 0);
		if (Date.now() >= eod.getTime()) {
			include_today = 1;
		}
	}

	frappe.call({
		method: "gs_customizations.api.get_timesheet_checkin_status",
		args: { include_today: include_today },
		callback: function (r) {
			if (!r || !r.message) return;
			const data = r.message;
			frappe.boot.timesheet_checkin = data;
			render(page, data);
		},
	});
}

function render(page, data) {
	const $c = page.$container;
	const $header = $c.find(".gs-checkin-header");
	const $days = $c.find(".gs-checkin-days");
	const $actions = $c.find(".gs-checkin-actions");
	const $success = $c.find(".gs-checkin-success");

	const greeting = get_greeting();
	const name = data.employee_name || frappe.session.user_fullname || "";
	$c.find(".gs-checkin-greeting").text(`${greeting}, ${name}!`);

	if (!data.enforce || !data.missing_days || !data.missing_days.length) {
		// All done
		$header.hide();
		$days.hide();
		$actions.hide();
		$success.show();
		setTimeout(function () {
			frappe.set_route("");
		}, 2000);
		return;
	}

	$header.show();
	$days.show();
	$actions.show();
	$success.hide();

	$c.find(".gs-checkin-subtitle").text(
		__("Please fill in your timesheets for the following days before continuing.")
	);

	$days.empty();
	data.missing_days.forEach(function (day) {
		const $card = build_card(day, data.employee);
		$days.append($card);
	});
}

function build_card(day, employee) {
	const date_str = frappe.datetime.str_to_user(day.date);
	const leave_note = day.leave_hours > 0
		? `<div class="gs-checkin-card-leave-note">${__("Includes")} ${format_hours(day.leave_hours)} ${__("of approved leave")}</div>`
		: "";

	const $card = $(`
		<div class="gs-checkin-card">
			<div class="gs-checkin-card-info">
				<div class="gs-checkin-card-date">${day.day_name}, ${date_str}</div>
				<div class="gs-checkin-card-hours">
					${__("Required")}: <strong>${format_hours(day.required_hours)}</strong>
					&nbsp;·&nbsp;
					${__("Logged")}: <strong>${format_hours(day.logged_hours)}</strong>
					&nbsp;·&nbsp;
					<span class="shortfall">${__("Missing")}: ${format_hours(day.shortfall)}</span>
				</div>
				${leave_note}
			</div>
			<div class="gs-checkin-card-action">
				<button class="btn btn-primary btn-sm gs-fill-btn">
					${__("Fill Timesheet")}
				</button>
			</div>
		</div>
	`);

	$card.find(".gs-fill-btn").on("click", function () {
		fill_timesheet(day, employee);
	});

	return $card;
}

function fill_timesheet(day, employee) {
	if (day.existing_timesheet) {
		frappe.set_route("Form", "Timesheet", day.existing_timesheet);
		return;
	}
	// Create a draft timesheet pre-filled with the target date
	frappe.call({
		method: "gs_customizations.api.create_timesheet_for_date",
		args: { date: day.date },
		freeze: true,
		freeze_message: __("Creating timesheet..."),
		callback: function (r) {
			if (r && r.message) {
				frappe.set_route("Form", "Timesheet", r.message);
			}
		},
	});
}

function format_hours(h) {
	h = Number(h) || 0;
	const whole = Math.floor(h);
	const mins = Math.round((h - whole) * 60);
	if (mins === 0) return `${whole}h`;
	return `${whole}h ${mins}m`;
}

function get_greeting() {
	const hour = new Date().getHours();
	if (hour < 12) return __("Good morning");
	if (hour < 18) return __("Good afternoon");
	return __("Good evening");
}
