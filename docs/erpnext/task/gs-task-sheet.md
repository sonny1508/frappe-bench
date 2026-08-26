# GS Task Sheet Report

`gs_customizations/report/gs_task_sheet/` — per-employee task listing with
expected-vs-actual time and utilisation.

Script Report on `Task`. Roles: `GS - Projects Manager`, `GS - Projects User`,
`Projects Manager`.

## Filters

| Filter | Notes |
|---|---|
| Filter Based On | `Month` or `Date Range`. Required. |
| Date Filter On | Which column the range applies to: `completed_on` (default) or `exp_start_date` |
| Month / Year | Shown when Filter Based On is `Month` |
| Start / End Date | Shown when Filter Based On is `Date Range` |
| Status | `Both` (default), `Completed`, `Closed`, `All` |
| Group By Assignee | Tree view with per-assignee subtotal rows |
| Show MDs | Reveals the two "In Days" columns. Display only — see below |

### Status "All" switches the date field

Unfinished tasks have no `completed_on`, so filtering the range on it hides almost
everything `All` exists to show — 135 unfinished tasks collapse to 8. Selecting
`All` therefore switches **Date Filter On** to `exp_start_date` automatically and
raises a `show_alert` so the change is not silent.

One-directional: switching back to `Both` leaves the date field alone, because
`Both` + Expected Start Date is a legitimate query in its own right.

`All` is written as `status NOT IN ('Cancelled', 'Template')`, not as a list of every
current status. An inclusion list silently drops any status added to Task later,
which is the kind of failure nobody notices.

### Only tasks with an assignee

The query requires `custom_assign_to_employee` to be non-empty.

`completed_by` / `custom_completed_by_employee` are only populated once a task reaches
Completed or Closed, so they cannot identify the employee on an open task. The report
keys off the assignee instead, which is populated at assignment time.

Side effect: tasks that never carried an assignee do not appear at all. When this
filter was introduced the default `Both` view went from 1469 to 998 rows — most of the
difference being older Closed tasks whose assignee field was never written (see
[task-overrides.md](task-overrides.md); `auto_set_fields_on_todo` skips the assignee
branch entirely for Completed/Closed). Roughly 405 of those are recoverable from ToDo
history if a backfill is ever wanted.

## Columns

Fixed order, identical whether or not grouping is on:

```
Assigned To | ID | Subject | Project Name | Issue Name | Status | Type | Is Group
| Expected Start Date | Completed By | Completed By Employee | Completed On
| Expected Time (Hours) | Actual Time In Timesheet | Expected Time (Days)*
| Actual Time In Timesheet (Days)* | % Utilization | Reviewer
```

`*` hidden unless **Show MDs** is ticked.

The column order used to change when grouping was enabled — the completed-by columns
jumped to the front. That is gone; one list, always.

## Show MDs and the Excel export

**The export always contains all 18 columns, whatever the toggle says.**

`Export` re-runs the report server-side with the same filters
(`frappe/desk/query_report.py` → `run(...)`) and never looks at the page. So hiding is
done in the **DOM only** — `get_columns()` always returns everything.

Things that do *not* work for this, and why:

- Dropping the columns in `get_columns()` when the toggle is off — the export re-runs
  with the same filters and loses them too.
- Marking the columns `hidden` — `build_xlsx_data` skips hidden columns explicitly.
- The `include_hidden_columns` flag in the export payload — the dialog never renders
  that field and no server code reads it. It is vestigial.

Implementation notes for anyone touching it:

- Applied from `after_datatable_render`, **not** `get_datatable_options`. The latter
  only fires when the datatable is first constructed and is skipped on every
  subsequent filter change (`query_report.js` takes a `datatable.refresh()` branch).
- Column indices come from `datamanager.getColumns()`, the same array that assigns
  `colIndex`, so the serial-number column cannot cause an off-by-one.
- CSS rules are scoped to a wrapper class. `.dt-cell--col-N` is shared by every
  datatable in the desk; an unscoped rule would follow the user to the next report.
- The toggle deliberately does **not** refresh the report — it is display only.

The same scoping trick sizes the filter inputs (`size_filters_to_content`). Query
report filters render as bare inputs with no width of their own and fall back to
roughly 180px each, which overflows the row and orphans the last checkbox.

## Grouping

`Group By Assignee` builds a tree: one bold summary row per assignee with totals,
then that assignee's tasks indented beneath.

`process_grouped_data` uses `itertools.groupby`, which **only works on input already
sorted by the group key** — so `ORDER BY` leads with `custom_assign_to_employee`. If
you change the group key, change the sort too.

## Non-manager visibility

Raw SQL bypasses `permission_query_conditions`, so the lock is re-applied in
`get_conditions`:

```sql
AND (completed_by IN %(own_ids)s OR custom_assign_to_id = %(own_user)s)
```

`completed_by` holds the **Employee ID**; `custom_assign_to_id` holds the **User
email**. Both arms are needed — the `completed_by` arm alone would show a non-manager
an empty report under the `All` status filter, since none of their unfinished tasks
have a `completed_by`.

## Safety note

`Date Filter On` is interpolated into the `WHERE` clause, because `frappe.db.sql`
cannot parameterise a column name. It resolves through the `DATE_FIELDS` whitelist in
`get_date_field()`. **Keep it that way** — never let a filter value reach the query
directly.
