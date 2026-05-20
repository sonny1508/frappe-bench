# Matrix Settings — DocType Reference

`gs_customizations/matrix_integration/doctype/matrix_settings/`

Singleton DocType. All Matrix configuration lives on this single page.
Accessible at: `/app/matrix-settings`

## Sections and fields

### Bot Configuration

| Field | Type | Notes |
|---|---|---|
| `enabled` | Check | Master on/off for the entire integration |
| `homeserver_url` | Data | API base URL: `https://matrix.glenda-studio-chat.com` |
| `bot_user_id` | Data | Full Matrix user ID: `@gs.bot:glenda-studio-chat.com` |
| `bot_access_token` | Password | PAT from MAS admin panel. Encrypted at rest by Frappe. |
| `bot_display_name` | Data | Optional display name |
| `bot_is_admin` | Check | Enables admin API features (force-join, server notices) |

**Critical**: `bot_user_id` must use the Matrix server name
(`glenda-studio-chat.com`), not the API hostname
(`matrix.glenda-studio-chat.com`). The server name is extracted from this
field to build all other user IDs.

### Room Provisioning

| Field | Type | Notes |
|---|---|---|
| `auto_provision_rooms` | Check | Auto-create DM room on Employee update |

### DM Rooms (child table: Matrix DM Room)

| Field | Type | Notes |
|---|---|---|
| `username` | Data | Employee's User.username (e.g. `sonny.nguyen.01`) |
| `room_id` | Data | Matrix room ID (read-only, filled by provisioning) |
| `status` | Select | Active / Failed (read-only) |
| `error_log` | Small Text | Last provisioning error (read-only) |

### Group Rooms (child table: Matrix Group Room)

| Field | Type | Notes |
|---|---|---|
| `room_name` | Data | Human-readable name (e.g. `design-announcements`) |
| `room_id` | Data | Matrix room ID |
| `status` | Select | Active / Failed |
| `error_log` | Small Text | Last error |

### Development / Testing (collapsible)

| Field | Type | Notes |
|---|---|---|
| `test_message` | Small Text | Message content to send |
| `test_target_type` | Select | DM or Group |
| `test_dm_username` | Data | Username for DM test (shown when target=DM) |
| `test_group_room` | Data | Room name for group test (shown when target=Group) |

## Buttons (defined in matrix_settings.js)

| Button | Group | Method | Description |
|---|---|---|---|
| Test Connection | Bot | `test_connection()` | Calls whoami to verify PAT |
| Provision DM Rooms | Rooms | `provision_all_dm_rooms()` | Bulk-provision rows without room_id |
| Send Test Message | Dev | `send_test_message()` | Send to DM (server notice) or group room |

## Controller methods (matrix_settings.py)

All three methods are `@frappe.whitelist()` and called from the JS buttons:

### `test_connection()`
Calls `bot.test_connection()` → whoami endpoint. Returns bot identity JSON.

### `send_test_message()`
Reads the dev section fields. For DM: derives Matrix user ID from
`test_dm_username` and calls `send_server_notice()`. For Group: looks up
`room_id` from the group_rooms child table by matching `room_name` and
`status == "Active"`, then calls `send_message()`.

### `provision_all_dm_rooms()`
Delegates to `provisioning.provision_all_dm_rooms()`. Returns summary dict
with provisioned/skipped/failed counts.

## Employee custom field

`custom_enable_matrix_notifications` (Check) on the Employee DocType.

- Defined in `customize/customize_fields.py` → `custom_employee()`
- Applied via patch `patches/add_employee_matrix_field.py`
- Inserted after `custom_enable_timesheet_checkin` in the Employee form
- Defaults to 0 (disabled) — employees must be explicitly opted in
- Checked by `notifications.py` → `_is_matrix_enabled_for_user()` before
  sending any notification
