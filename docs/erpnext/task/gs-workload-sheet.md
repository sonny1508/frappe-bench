# GS Workload Sheet and GS Task Pool

`gs_customizations/report/gs_workload_sheet/` and `gs_customizations/report/gs_task_pool/`
— the people view of task assignments, for deciding who should take more or less work.

Both are Script Reports on `Task`, for managers only: roles `GS - Projects Manager`
and `System Manager`, and `execute()` refuses anyone `is_manager()` says no to.

Unlike the other GS reports neither has a period filter. They always show the
current state.

## GS Workload Sheet

A tree: one row per employee, expanding to the tasks assigned to them now. Opens
collapsed (`initial_depth: 0`).

### Who is listed

Active employees whose user holds `GS - Projects User` (the role tasks are assigned
to), plus anyone else who currently holds a task. Employees with no tasks are listed
on purpose — they are who a manager is looking for.

Assignments come from `ToDo` (`status = "Open"`, `reference_type = "Task"`) and are
matched to the Employee through `user_id`. `Task.custom_assign_to_employee` is only
a display name and is not used.

A task counts when it is not Completed, Closed, Cancelled or Template, and is not a
group or template task. Group tasks only hold their children, and the hours sit on
those.

### Active and Submitted

| Count | Statuses |
|---|---|
| Active Tasks | Every other unfinished status: Open, Working, QA Feedback, Client Feedback, and any status added later |
| Submitted Tasks | QA Pending, QA Reviewing, QA Approved, Delivered (`SUBMITTED_STATUSES`) |

Submitted is the explicit list so the two always add up to the total. The feedback
statuses count as active because the task is back with the artist.

Under each employee, active tasks are listed before submitted ones, then soonest
`exp_end_date` first.

### Filters

| Filter | Notes |
|---|---|
| Department | Exact match on `Employee.department` |
| Grade | Exact match on `Employee.grade` |
| Active Tasks Fewer Than | 1–5. Keeps employees whose Active Tasks is below it; `1` means no active task at all |

### Columns

```
ID | Name | Department | Grade | Active Tasks | Submitted Tasks | Overdue Tasks
| Project | Status | Expected Start Date | Expected End Date
| Expected Time (In Hours) | Utilization
```

One column set serves both row types. `ID` is a Dynamic Link on the row's hidden
`row_doctype`, so it links to the Employee on employee rows and the Task on task rows.
Labels follow the Task field each column comes from.

- **Overdue Tasks** — `exp_end_date` before today on an unfinished task
  (`is_past_deadline`, the same test as the [Overdue priority](task-overrides.md#overdue-priority)).
  Late deadlines show in red.
- **Utilization** — hours logged ÷ hours estimated. Hours are summed live from
  `Timesheet Detail` with `docstatus < 2`, **draft timesheets included**:
  `Task.actual_time` counts submitted timesheets only, and a timesheet stays in draft
  until its week is submitted. So this can differ from the Task's own Utilization
  field. Blank when nothing is estimated.

Summary cards: Employees, With No Active Tasks, Overdue Tasks, and Unassigned Tasks
(the size of GS Task Pool).

### Sorting and Expand All

Only the employee totals — Active, Submitted, Overdue, Expected Time, Utilization —
keep a column menu (`"dropdown": False` on the rest in `get_columns()`).

The datatable's own sort orders every row on its own, which pulls tasks away from
their employee. `sort_by_employee()` in the JS replaces `_sortRows` on this report's
datatable instance so each employee moves together with its tasks. Ties keep the
department / name order, and a blank total sorts as the lowest.

> `_sortRows` is internal to frappe-datatable. Check sorting still works after a
> Frappe upgrade.

A sort redraws every row, open or not, so an `onSortColumn` handler shows again only
the tasks of employees that were expanded.

The **Expand All / Collapse All** toolbar button goes through the report's own
`expand_all_rows()` / `collapse_all_rows()`, so the footer buttons stay in step. It
resets to Expand All on every refresh, because the report opens collapsed.

## GS Task Pool

Unfinished tasks with no `Open` ToDo — the work waiting to be handed out. Group and
template tasks are left out. Soonest `exp_end_date` first.

Filter: Project.

```
ID | Subject | Project | Type | Priority | Expected Time (In Hours)
| Expected Start Date | Expected End Date | Days Left
```

Days Left is negative once the deadline has passed.

It can't be part of GS Task Sheet: that report always filters on `completed_on` or
`exp_start_date`, and an unassigned task has neither, because `exp_start_date` is
stamped on assignment.

Note that a planned `exp_start_date` set on a pool task is overwritten with the
assignment day once someone is assigned (`set_exp_start_date_from_assignment`, see
[task-overrides.md](task-overrides.md)).
