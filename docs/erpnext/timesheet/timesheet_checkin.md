# Timesheet Check-in Enforcement

Redirects employees to a check-in page when they have unfilled timesheets for the current week. Opt-in per employee.

## Files

| File | Purpose |
|---|---|
| `utils/timesheet_checkin.py` | Core logic: missing-day computation, leave/logged hours helpers |
| `public/js/timesheet_checkin_enforcer.js` | Client-side route guard + EOD timer (loaded globally via `app_include_js`) |
| `boot.py` | Injects `timesheet_checkin` into `frappe.boot` on every page load |
| `api.py` | `get_timesheet_checkin_status()` -- refresh endpoint; `create_timesheet_for_date()` -- creates/reuses weekly draft |
| `gs_customizations/page/timesheet_checkin/` | The actual check-in page UI |

## How It Works

### Boot
`boot.py` calls `get_checkin_status(user)` and stores the result in `frappe.boot.timesheet_checkin`. Wrapped in try/except so failures never break login.

### Enforcement flow
1. `timesheet_checkin_enforcer.js` installs a route guard on `frappe.router.on("change")`
2. On every SPA navigation, if `frappe.boot.timesheet_checkin.enforce == true`, redirect to `/app/timesheet-checkin`
3. Allowed routes (bypass redirect): `timesheet-checkin`, any Timesheet form/list, Leave Application
4. An EOD timer fires at `custom_end_working_hour`; calls the API with `include_today=1` to also check today

### Opt-in
Controlled by `Employee.custom_enable_timesheet_checkin` (Check, default 0). Exemptions:
- Administrator, Guest
- Users with any role in `frappe.conf.manager_roles` list (set in site_config.json)
- Users without an active Employee record

## Missing-Day Computation (`get_missing_timesheet_days`)

Scans weekdays (Mon-Fri) from Monday of the current week through yesterday (or today if `include_today=True`):
1. Skip weekends (Saturday, Sunday)
2. Skip holidays (via `get_holiday_dates()` → `hrms.hr.utils.get_holiday_dates_for_employee`) and Absent days (via `get_absent_dates()`) — both are non-working days
3. Skip days before `date_of_joining`
4. Compute leave hours for the day (full-day + hourly)
5. If fully on leave (`leave_hours >= company_working_hours`), skip
6. Compare `logged_hours` (from Timesheet Detail) vs `required_hours` (company hours - leave)
7. If shortfall, add to missing list with `existing_timesheet` name (weekly draft lookup)

Returns list of dicts with: `date`, `day_name`, `required_hours`, `logged_hours`, `shortfall`, `leave_hours`, `existing_timesheet`.

## Key Helper Functions (used by both checkin and timesheet overrides)

- `get_leave_hours_for_date(employee, date, company_working_hours)`: Returns leave hours for a date, sourced from the **Attendance** record (not Leave Application — every approved Leave Application creates/updates Attendance, so it's the single source of truth). Status mapping:
  - `On Leave` → full `company_working_hours`
  - `Hours Leave` → `custom_total_leave_time` (seconds / 3600), capped at `company_working_hours`
  - `Half Day` → half of `company_working_hours` (legacy; being phased out in favour of Hours Leave)
  - anything else / no Attendance row → 0

- `get_holiday_dates(employee, start_date, end_date)`: Returns a set of holiday date strings from the employee's Holiday List via `get_holiday_dates_for_employee`. Returns empty set on failure (graceful degrade).

- `get_logged_hours_for_date(employee, date)`: SQL sum of `Timesheet Detail.hours` where `DATE(from_time) = date` and docstatus in (0, 1).

- `find_existing_timesheet(employee, date)`: Finds existing Draft Timesheet for the same Mon-Sun week. Checks `start_date` within week first, then falls back to overlapping date range. Returns name or None.

## After-Save Refresh
`timesheet.js` `after_save` calls `get_timesheet_checkin_status` to refresh boot data so the enforcer picks up the change without a page reload. Only calls if the feature is active for the user.
