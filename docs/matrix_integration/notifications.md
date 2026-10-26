# notifications.py — Task Notification Hooks

`gs_customizations/matrix/notifications.py`

Mirrors the Synology notification logic (`synology/synology.py`) but delivers
messages via Matrix server notices. The Synology hooks are commented out in
`hooks.py`; only Matrix sends.

## Hooks

Wired in `hooks.py`:

```python
doc_events = {
    "ToDo": {"after_insert": [..., "gs_customizations.matrix.notifications.notify_todo_insert"]},
    "Task": {"on_update": ["gs_customizations.matrix.notifications.notify_task_update"]},
}
scheduler_events = {
    "cron": {"* * * * *": ["gs_customizations.matrix.notifications.send_due_task_notifications"]},
}
```

### `notify_todo_insert(doc, method)`

Fires when a ToDo is created (task assignment) and sends straight away. Only
triggers if:
1. The ToDo references a Task (`reference_type == "Task"`)
2. The ToDo status is Open
3. Matrix integration is enabled (global check)
4. The "Open" status config has `notify_assignees: True`

### `notify_task_update(doc, method)`

Fires on Task save and **only queues** the notice — see
[the 2-minute hold](#the-2-minute-hold). Queues if:
1. Matrix integration is enabled
2. The task is not new, and its status actually changed (compares with
   `get_doc_before_save()`). A new task has nobody assigned yet; its assignees
   hear from `notify_todo_insert`.
3. A notice for this task is already held, or the new status notifies someone
   in `STATUS_NOTIFICATIONS`

It never raises: a failure is written to the Error Log and the status change
goes through without its notice.

### `send_due_task_notifications()`

Runs every minute. Sends the held notices whose hold has run out — see below.

## The 2-minute hold

A Task status change is announced only once the status has held for
`NOTIFY_DELAY_MINUTES` (2). This is for misclicks: a card dragged into the
wrong Kanban column and straight back sends nothing.

The held notices are rows of **Matrix Pending Notification**, one per task,
named after it:

| Field | Meaning |
|---|---|
| `task` | The task |
| `from_status` | Status before the first change in this hold. Kept when later changes restart the hold |
| `to_status` | Latest status, for information |
| `send_after` | Pushed back to now + 2 minutes on every further status change |

When `send_after` has passed, the minute job deletes the row, commits, then
looks at the task **as it is now**:

| Task now | Result |
|---|---|
| Back to `from_status` | Nothing sent: a misclick undone |
| Any other status | Notice for the current status, to whoever `STATUS_NOTIFICATIONS` names for it |
| Deleted | Nothing sent |

So only the status a task settles on is announced. Working → QA Pending → QA
Reviewing within 2 minutes announces QA Reviewing only, which tells nobody: the
reviewer has already picked it up.

Notices go out between 2 and 3 minutes after the last change (the job runs once
a minute). To cancel one, delete its row in `/app/matrix-pending-notification`.

Why the row is deleted and committed *before* sending: if sending then fails,
that one notice is lost (and logged), as an inline send always was, instead of
being repeated every minute.

The row is written in the Task save's own transaction, so a save that fails
leaves no notice behind. When notices were sent from inside the save, a save
that failed afterwards (e.g. the Kanban Board save) had already sent one.

**Before `bench migrate`** has created the table, `notify_task_update` sends
straight away as it used to, so updating the code alone loses no notices.

### Performance, measured 2026-10-26

Holding the notice was not where the 5–10 s Kanban wait came from. Measured on
this site:

- The server side of a Kanban drag (`update_order_for_single_card`) takes
  75–115 ms without the Matrix send.
- A Synapse round trip from Frappe takes about 35 ms (the hostname resolves to
  the LAN).
- For real QA Feedback / QA Approved / Client Feedback moves that day, Synapse
  stored the assignee's notice 0.07–0.21 s after the Task save started (read
  from `origin_server_ts` in the notice rooms vs `tabTask.modified`).

## Status notification config

Defined in code (not in the DocType), same structure as the Synology site_config:

```python
STATUS_NOTIFICATIONS = {
    "Open":            {"notify_assignees": True,  "notify_subscribers": False},
    "Working":         {"notify_assignees": False, "notify_subscribers": False},
    "QA Pending":      {"notify_assignees": False, "notify_subscribers": True},
    "QA Reviewing":    {"notify_assignees": False, "notify_subscribers": False},
    "QA Feedback":     {"notify_assignees": True,  "notify_subscribers": False},
    "QA Approved":     {"notify_assignees": True,  "notify_subscribers": False},
    "Client Feedback": {"notify_assignees": True,  "notify_subscribers": False},
    "Completed":       {"notify_assignees": True,  "notify_subscribers": False},
}
```

- **Assignees**: Users assigned to the task via ToDo (status=Open)
- **Subscribers**: Users in the project's `custom_notification` Portal User table

To change which statuses notify whom, edit this dict directly.

## Recipient resolution

1. `get_task_assignees(task_name)` — queries ToDo for open assignments,
   looks up `User.username` for each `allocated_to` email
2. `get_project_subscribers(project_name)` — queries Portal User rows
   where `parentfield == "custom_notification"`, looks up `User.username`
3. `get_recipients(status_config, assignees, subscribers)` — merges lists
   based on the status config flags

All functions return **usernames** (e.g. `sonny.nguyen.01`), not emails or
Matrix user IDs.

## Per-employee opt-in

Before sending, `_send_to_recipients()` checks each username against the
Employee's `custom_enable_matrix_notifications` flag:

```python
def _is_matrix_enabled_for_user(username):
    user_email = frappe.db.get_value("User", {"username": username}, "name")
    enabled = frappe.db.get_value("Employee", {"user_id": user_email},
                                  "custom_enable_matrix_notifications")
    return bool(enabled)
```

This custom Check field lives on the Employee DocType (added via
`customize/customize_fields.py`). Employees without the flag enabled are
silently skipped — no error, no log. This allows gradual rollout during
migration: enable per-employee as they get Matrix accounts.

## Message format

Built by `build_message(doc, assignees)`. Uses `*bold*` and `` `code` ``
notation which `bot.py`'s `_markdown_to_html()` converts to HTML for Element
rendering.

## Delivery

`_send_to_recipients()` iterates usernames, builds Matrix user IDs via
`bot.get_matrix_user_id()`, and calls `bot.send_server_notice()` for each.
Failures are caught per-user and logged — one user's error doesn't block
others. For Task status changes this runs in the minute job, through
`_announce_task_status()`, not inside the save.

## Differences from Synology

| Aspect | Synology (`synology.py`) | Matrix (`notifications.py`) |
|---|---|---|
| Config source | `frappe.conf` (site_config.json) | `STATUS_NOTIFICATIONS` dict in code |
| Delivery | Webhook POST to Synology Chat API | Server notice via Synapse admin API |
| Recipient lookup | Username → webhook URL from config | Username → Matrix user ID derived at runtime |
| Per-user gating | None | `custom_enable_matrix_notifications` on Employee |
| Message format | Plain text | Plain text + HTML (bold/code rendered in Element) |
