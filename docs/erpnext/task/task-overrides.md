# Task Overrides

`overrides/erpnext/task/` — `CustomTask` plus the automation that keeps several
Task fields server-owned.

| File | Role |
|---|---|
| `task.py` | `CustomTask(Task)` + doc_event handlers + field automation |
| `overdue_priority.py` | The Overdue priority rules — see [below](#overdue-priority) |
| `task.js` | Form script (`doctype_js`) |
| `task_list.js` | List/gantt settings (`doctype_list_js`) |
| `task_permissions.py` | `permission_query_conditions` handler |

## Wiring (hooks.py)

```python
override_doctype_class = {"Task": "...task.task.CustomTask"}

doc_events = {
    "ToDo": {
        "before_insert": "...validate.permissions.block_assign",
        "after_insert": [
            "...task.task.set_exp_start_date_from_assignment",
            "...task.task.set_assignee_from_assignment",
            "...matrix.notifications.notify_todo_insert",
        ],
    },
    "Task": {
        "validate": "...task.task.custom_validate",
        "on_change": "...task.task.on_change",
        "on_update": ["...matrix.notifications.notify_task_update"],
    },
}
```

Order in the `after_insert` list matters: `notify_todo_insert` does an unguarded
`frappe.get_doc("Task", ...)`, so anything that must run regardless goes before it.

## Assignment is a ToDo, not a Task field

This is the single most important thing to understand here.

Assigning someone **inserts a ToDo row — it does not save the Task.** So none of
the Task's own `validate`/`on_update` logic runs on assignment. Any Task field that
should reflect assignment has to be written from a ToDo hook.

Un-assigning **never deletes the ToDo**; it only flips `status`:

| Action | Effect on the ToDo |
|---|---|
| `assign_to.add()` | Inserts a new row, `status="Open"` |
| `assign_to.remove()` | `status="Cancelled"` |
| `close_all_assignments()` | `status="Closed"` |
| `assign_to.clear()` | `status="Cancelled"` |

So `tabToDo` is a complete, durable assignment history. `ToDo.creation` is the
assignment timestamp — **`ToDo.date` is the due date**, not the assignment date.

`assign_to.add()` refuses a second `Open` ToDo for a user who is already assigned,
so a new row appears only on a genuine remove-then-re-add. That is what makes
"re-stamp on every reassignment" work without any extra bookkeeping.

## Server-owned fields

| Field | Written by | When |
|---|---|---|
| `exp_start_date` | `set_exp_start_date_from_assignment` | ToDo insert; skipped if `act_start_date` is set |
| `custom_assign_to_employee` / `_id` | `set_assignee_from_assignment` + `auto_set_fields_on_todo` | ToDo insert, and every Task validate |
| `completed_by` / `custom_completed_by_employee` | `auto_set_fields_on_todo` | Task validate, on Completed/Closed |
| `custom_reviewer` | `auto_set_reviewer` | Task validate |
| `custom_utilization` | `CustomTask.update_utilization` | Task on_update |
| `color` | `set_color_by_priority` | Task validate + on_change |
| `priority` (Overdue only) / `custom_priority_before_overdue` | `apply_overdue_priority` | Task validate, and once a day — see [below](#overdue-priority) |

### Why these use `frappe.db.set_value(..., update_modified=False)`

The ToDo hooks write directly to the database rather than calling `doc.save()`:

- `doc.save()` from inside a ToDo insert would re-run the whole Task lifecycle —
  `validate_task_fields_permissions` (which throws for non-managers), `update_project`
  (re-costs the entire Project), the nested-set rebuild, and a Matrix HTTP call.
- `update_modified=False` keeps `modified` still. The assigning manager has the Task
  form open — the desk sidebar re-renders its avatars but **never reloads the doc** —
  so bumping `modified` would hand them *"Document has been modified"* on their next save.
- It matches the framework's own precedent: `ToDo.update_in_reference()` writes the
  parent's `_assign` exactly this way, from this exact event.

The cost: **no Version row**, so these changes do not appear in the Task's document
history. `tabToDo` is the audit trail.

## Overdue priority

There is no Overdue **status**. A task past its deadline is marked by the
**priority** `Overdue` instead, and its status is left alone.

ERPNext's own behaviour was to switch Open/Working tasks past `exp_end_date` to
status Overdue. That pulled the task out of its workflow stage, and
`validate_status_transition` gave artists no way to move it on again. The status was
dropped from the options and the Overdue Kanban column archived
(`patches/archive_task_overdue_kanban_column.py`).

The rules, for a task that is not Completed, Closed or Cancelled:

| Situation | Result |
|---|---|
| `exp_end_date` is before today | Priority becomes Overdue. The previous priority is kept in hidden `custom_priority_before_overdue` |
| Still late, someone changes the priority | Refused (`Priority Locked`) |
| `exp_end_date` moved to today or later, or cleared | The kept priority comes back |
| Overdue picked by hand on a task that isn't late | Refused (`Priority Not Allowed`) |

The deadline day itself is still on time. A **finished** task is left as it is, so
one that finished late keeps Overdue as the record of it, and its priority can be
changed freely.

All of this is `resolve_priority()`, a pure function over scalars. Two paths call it:

- `custom_validate` → `apply_overdue_priority()`, on every save. It runs **after**
  `validate_task_fields_permissions`, so a priority the system sets does not count
  as a restricted change by an artist.
- ERPNext's daily `set_tasks_as_overdue` job, which calls `CustomTask.update_status()`
  for every task not Cancelled/Completed. That method now saves a task that has just
  gone late instead of setting the status. It uses a full `save()` (bumps `modified`,
  writes a Version row) so a stale open form is refused rather than writing the old
  priority back, and a savepoint so one failing task does not stop the loop.

`workflow_priority()` reads the kept priority while a task is Overdue, so a late
**Support** task keeps the Open → Working → Completed workflow.

The Task form (`task.js`) and the Kanban inline editor leave Overdue out of the
dropdown, and the form locks the field while an unfinished task is Overdue. The
server enforces both anyway. Overdue sorts first on Kanban (`TASK_PRIORITY_ORDER`
and `PRIORITY_ORDER`).

## Landmines

**The priority colour map exists twice** — `set_color_by_priority` in `task.py` and
in `task.js` — and they must match. The form sets the colour and saves the task on
refresh whenever the colour disagrees with its map, and the server then sets it back
to its own, so a mismatch means an extra save every time the form is opened.

**Do not hook `ToDo.on_update` to catch un-assignment.** `close_all_assignments()`
runs inside `CustomTask.validate_status()`, at which point the Task's *stored* status
is still the old one. A Completed/Closed guard would not have flipped yet, so closing
a task would wipe its assignee. Un-assignment reconciles on the Task's next save
instead, via `auto_set_fields_on_todo`.

**`exp_start_date` has validation bounds.** ERPNext throws if
`exp_start_date > exp_end_date`, or if it is after the Project's `expected_end_date`.
Because the hooks write straight to the DB they bypass both at write time — a bad
value would only detonate on the *next* ordinary save and leave the task un-editable.
`exp_start_date_block_reason()` refuses the write instead. Never "clamp" to the bound:
a clamped date is silently wrong data that looks correct.

**Several Task fields are permlevel 1.** Set via Customize Form, so they are **not**
in `customize_fields.py`. `GS - Projects Manager` has permlevel-1 write;
`GS - Projects User` has read only.

```
exp_start_date  exp_end_date  expected_time  priority  project  subject  type
is_group  is_milestone  is_template  parent_task  department  duration  issue
start  task_weight  depends_on  depends_on_tasks  completed_by  completed_on
```

Two consequences. Non-managers are protected by the framework —
`validate_higher_perm_levels()` resets those fields from a fresh DB read *before*
validate runs. Managers are not, which is why `preserve_exp_start_date()` exists:
a manager's stale form would otherwise write a blank over a server-set value.

**`CustomTask.validate()` and `on_update()` re-list the parent's calls without
`super()`.** Anything ERPNext adds to those methods upstream is silently dropped.
Check them after an ERPNext upgrade.

**`CustomTask.validate()` runs *before* the `custom_validate` doc_event.**
`Document.hook` composes the controller method first. So anything set in
`custom_validate` has already escaped `validate_dates()` — which is why
`preserve_exp_start_date()` only ever restores a previously bound-checked value and
never derives a new date.

**`block_assign` applies to every ToDo insert site-wide**, not just Tasks — it has no
`reference_type` guard. Only users holding a `manager_roles` role can create any ToDo.

**Dead code:** `overrides/erpnext/todo/todo.py` is wired to nothing, has the wrong
signature for a doc_event, and writes to `custom_assign_to` — a column that exists in
`tabTask` but has no Custom Field behind it. Ignore it; do not build on it.

## Permissions

`task_permissions.task_query_conditions` limits non-managers to tasks with an `Open`
ToDo allocated to them. Note the ToDo status filters are inconsistent across the app —
`task_permissions.py` and `matrix/notifications.py` use `status == "Open"`, while
`auto_set_fields_on_todo` uses `not in ("Closed", "Cancelled")` and
`check_user_assignment` uses `!= "Cancelled"`. A Closed task therefore drops out of
list visibility while still passing `check_user_assignment`.

`validate_task_fields_permissions` restricts non-managers to changing `status` only,
and `validate_status_transition` constrains which transitions are legal by priority.
