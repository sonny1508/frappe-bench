# Timesheet Overrides

Timesheets are **weekly** (one Draft per employee per Mon-Sun week, not per day).
The native ERPNext `from_time`/`to_time` fields remain as Datetime; we layer validation on top.

## Files

| File | Purpose |
|---|---|
| `overrides/erpnext/timesheet/timesheet.py` | Server-side validate hooks + `get_timesheet_validation_context` whitelisted API |
| `overrides/erpnext/timesheet/timesheet.js` | Client-side validation, auto-defaults, daily summary rendering |
| `overrides/erpnext/timesheet_detail/timesheet_detail.js` | Unused (commented out in hooks.py); logic merged into timesheet.js |
| `customize/customize_fields.py` | `custom_timesheet()` adds `custom_daily_hours_summary` (HTML field after `time_logs`) |

## Hooks (hooks.py)

```python
doctype_js = { "Timesheet": "overrides/erpnext/timesheet/timesheet.js" }

doc_events = {
    "Timesheet": {
        "validate": [
            "...timesheet.update_completed_from_task",
            "...timesheet.clear_free_activity_fields",
            "...timesheet.validate_timesheet_rules",   # the custom rules
        ]
    }
}
```

## Validation Rules (both JS + Python)

1. **Max daily hours**: Total hours per calendar date across all rows cannot exceed `Company.custom_total_working_hours` (Duration field, stored as seconds, converted to float hours via `/ 3600`).

2. **Leave deduction**: Approved leave on a date reduces the max allowed hours. Full-day leave blocks entry entirely. Hourly leave (`custom_use_single_date=1`) subtracts `custom_total_leave_time` (also seconds). Leave data is fetched via `timesheet_checkin.get_leave_hours_for_date()`.

3. **Date range** (checkin-enabled employees only): `from_time` date must be within the last 6 calendar days. Only applies to new rows or rows where the date changed — existing rows with older dates can be edited (hours, activity, etc.) without restriction. No future-date limit. Users without `custom_enable_timesheet_checkin` have no date restriction. JS clears the field; Python throws.

4. **Next-day overflow**: `from_time + hours` must not cross midnight (i.e., `getdate(from_time) == getdate(to_time)`). Prevents e.g. 18:00 + 8h = 02:00 next day.

## Client-Side Behavior

### Validation context (`frm._ts_ctx`)
Fetched once on refresh via `get_timesheet_validation_context(employee, company)`. Returns:
```json
{
  "company_working_hours": 8.0,
  "start_working_hour": "09:00:00",
  "leave_data": { "2026-05-25": 0, "2026-05-26": 2.5, ... },
  "submitted_hours": { "2026-05-25": 8.0, ... },
  "checkin_enabled": true
}
```
`leave_data` covers -14 to +7 days from today (ensures both current and previous week are fully covered). `submitted_hours` maps dates to hours already logged in submitted (docstatus=1) timesheets for the same employee — used by the daily summary to reduce available hours and hide fully-consumed dates. `checkin_enabled` reflects the employee's `custom_enable_timesheet_checkin` flag and controls whether date restrictions apply. Validations degrade gracefully if `_ts_ctx` is null.

### Auto-set from_time (Rule 4)
On `time_logs_add`:
- First row of the timesheet: `today + company start_working_hour`
- Subsequent rows: chains to previous row's `to_time` if available, otherwise falls back to the previous row's date + company start time
- Skips if target date has full-day leave

### Daily Hours Summary (`custom_daily_hours_summary`)
HTML field rendered client-side. Always shows all weekdays (Mon–Fri) of the timesheet's week, plus any extra dates with time_logs outside that range. Columns: Date | Day | Logged hours | Available hours. Available hours = company working hours − approved leave − hours already logged in submitted timesheets for that date. Annotations in the Available column note leave and submitted hours separately. Dates where available ≤ 0 (fully consumed by leave + submitted timesheets) are hidden entirely. Rows turn red when logged > available. Updates on every field change (not just save).

## Server-Side Utilities

`_get_company_working_hours_float(company)`: reads `custom_total_working_hours` (seconds) and returns float hours. Duplicated in `timesheet_checkin.py` as `_get_company_working_hours()` -- same logic.

## Other Validate Hooks

- `clear_free_activity_fields`: Nulls project/task fields on rows where `activity_type` is "Free" or "Documents".
- `update_completed_from_task`: Sets `row.completed = 1` if the linked Task is Completed/Closed and `from_time >= completed_on`.

## Company Custom Fields (relevant)

| Fieldname | Type | Notes |
|---|---|---|
| `custom_start_working_hour` | Time | Default start time for new rows |
| `custom_end_working_hour` | Time | Used by checkin enforcer EOD timer |
| `custom_total_working_hours` | Duration (read-only) | Max daily hours; stored as seconds |
