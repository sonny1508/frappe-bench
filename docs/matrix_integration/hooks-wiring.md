# Hooks Wiring

How Matrix integration connects to Frappe's doc_events system.

## Current hook configuration (hooks.py)

Both Synology and Matrix hooks fire side-by-side using Python lists:

```python
doc_events = {
    "ToDo": {
        "after_insert": [
            "gs_customizations.synology.synology.notify_todo_insert",
            "gs_customizations.matrix.notifications.notify_todo_insert"
        ]
    },
    "Task": {
        "on_update": [
            "gs_customizations.synology.synology.notify_task_update",
            "gs_customizations.matrix.notifications.notify_task_update"
        ],
    },
    "Employee": {
        "on_update": "gs_customizations.matrix.provisioning.on_employee_update"
    },
}
```

## How to disable Synology

When migration is complete, remove the Synology entries from the lists:

```python
# Before (both systems):
"after_insert": [
    "gs_customizations.synology.synology.notify_todo_insert",
    "gs_customizations.matrix.notifications.notify_todo_insert"
]

# After (Matrix only):
"after_insert": "gs_customizations.matrix.notifications.notify_todo_insert"
```

Then restart workers (`sudo supervisorctl restart all`).

The Synology code (`synology/synology.py`) can stay in the codebase — it's
harmless if not wired in hooks. It reads config from `frappe.conf` which can
also be removed from site_config.json when ready.

## Guard rails

Each hook function has its own early-return checks:

1. **Global enable**: `_is_matrix_enabled()` checks the Matrix Settings
   singleton's `enabled` flag
2. **Status relevance**: Only fires for statuses listed in
   `STATUS_NOTIFICATIONS`
3. **Status change**: `notify_task_update` skips if the status hasn't
   actually changed (compares with `get_doc_before_save()`)
4. **Per-employee**: `_is_matrix_enabled_for_user()` checks the employee's
   `custom_enable_matrix_notifications` flag
5. **Error isolation**: Each recipient is wrapped in try/except — one
   failure doesn't block others

## Adding new hooks

To add Matrix notifications for other DocTypes:

1. Create a new hook function in `notifications.py` (or a new file)
2. Wire it in `hooks.py` → `doc_events`
3. The function receives `(doc, method)` — standard Frappe hook signature
4. Use `bot.send_server_notice()` for DMs, `bot.send_message()` for groups
5. Always check `_is_matrix_enabled()` first
6. Always check `_is_matrix_enabled_for_user()` per recipient
7. Wrap sends in try/except to prevent blocking the document save
