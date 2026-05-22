# notifications.py — Task Notification Hooks

`gs_customizations/matrix/notifications.py`

Mirrors the Synology notification logic (`synology/synology.py`) but delivers
messages via Matrix server notices. Both systems fire side-by-side through
list-style hooks in `hooks.py`.

## Hooks

Wired in `hooks.py` → `doc_events`:

```python
"ToDo": {
    "after_insert": [
        "gs_customizations.synology.synology.notify_todo_insert",     # Synology
        "gs_customizations.matrix.notifications.notify_todo_insert"   # Matrix
    ]
},
"Task": {
    "on_update": [
        "gs_customizations.synology.synology.notify_task_update",     # Synology
        "gs_customizations.matrix.notifications.notify_task_update"   # Matrix
    ],
},
```

### `notify_todo_insert(doc, method)`

Fires when a ToDo is created (task assignment). Only triggers if:
1. The ToDo references a Task (`reference_type == "Task"`)
2. The ToDo status is Open
3. Matrix integration is enabled (global check)
4. The "Open" status config has `notify_assignees: True`

### `notify_task_update(doc, method)`

Fires on Task save. Only triggers if:
1. Matrix integration is enabled
2. The task's status actually changed (compares with `get_doc_before_save()`)
3. The new status exists in `STATUS_NOTIFICATIONS`

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
others.

## Differences from Synology

| Aspect | Synology (`synology.py`) | Matrix (`notifications.py`) |
|---|---|---|
| Config source | `frappe.conf` (site_config.json) | `STATUS_NOTIFICATIONS` dict in code |
| Delivery | Webhook POST to Synology Chat API | Server notice via Synapse admin API |
| Recipient lookup | Username → webhook URL from config | Username → Matrix user ID derived at runtime |
| Per-user gating | None | `custom_enable_matrix_notifications` on Employee |
| Message format | Plain text | Plain text + HTML (bold/code rendered in Element) |
