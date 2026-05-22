# provisioning.py — DM Room Provisioning

`gs_customizations/matrix/provisioning.py`

Handles creating DM rooms between the bot and employees. Currently used for
the DM Rooms child table in Matrix Settings. Note that DM notifications
actually use **server notices** (which auto-create their own rooms), so this
provisioning is for bot-initiated DM rooms — a separate concept.

## Two entry points

### 1. Manual bulk provisioning (button)

The "Provision DM Rooms" button on Matrix Settings calls
`provision_all_dm_rooms()`. This processes rows already in the DM Rooms child
table that have a `username` but no `room_id`:

```
For each row in dm_rooms:
  - Skip if room_id exists and status is Active
  - Skip if username is empty
  - Check Matrix for existing DM room (best-effort, may 403)
  - If found → reuse room_id, set Active
  - If not found → create new room, optionally force-join, set Active
  - On error → set Failed + error_log
```

It does NOT auto-discover employees — you must add rows to the table first.

### 2. Auto-provisioning on Employee update (hook)

Wired in `hooks.py`:
```python
"Employee": {
    "on_update": "gs_customizations.matrix.provisioning.on_employee_update"
}
```

When an Employee is saved:
1. Checks if Matrix integration is enabled AND `auto_provision_rooms` is checked
2. Looks up the Employee's linked User's username
3. Checks if a DM room row already exists for this username
4. If not, enqueues `_provision_and_add_row` as a background job (doesn't
   block the save)

The background job provisions the room and appends a new row to the dm_rooms
child table.

## Core provisioning logic

`_provision_single_room(username, settings)` handles a single username:

1. Derives Matrix user ID: `username → @username:glenda-studio-chat.com`
2. Checks for existing DM room via `bot.get_existing_dm_room()` (reads
   m.direct account data). This is best-effort — returns None on 403/404
   (common with MAS PATs that lack account_data scope).
3. If existing room found → returns it with status Active
4. If not → calls `bot.create_dm_room()` (60s timeout)
5. If bot is admin → calls `bot.force_join_room()` to ensure user is in room
6. On any error → returns status Failed with error message (truncated to 500 chars)

## Notes

- Room creation can be slow (invite processing, federation checks). The
  create_dm_room call uses a 60s timeout.
- `force_join_room` failures are logged as warnings but don't fail the
  provisioning — the room is still created, the user just has a pending invite.
- The auto-provision hook uses `frappe.enqueue()` (queue="short") so the
  Employee save isn't blocked by API calls.
- After provisioning, the settings doc is saved with `ignore_permissions=True`
  and committed immediately.

## Relationship to server notices

Server notices and provisioned DM rooms are **independent**:

- **Server notices** (`send_server_notice`) — Synapse creates its own "Server
  Notices" room per user automatically. No provisioning needed. This is what
  `notifications.py` uses for task DM notifications.
- **Provisioned DM rooms** (`create_dm_room`) — bot-created rooms stored in
  the DM Rooms child table. Used for bot-initiated direct messaging (not
  server notices). Currently not used by the notification system.

The DM Rooms table and provisioning exist for potential future use where the
bot needs to send messages directly to users (as opposed to server notices).
