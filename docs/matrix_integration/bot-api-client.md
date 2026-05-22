# bot.py — Matrix/Synapse HTTP Client

`gs_customizations/matrix/bot.py`

All Matrix and Synapse API calls go through this module. Nothing else in the
codebase makes HTTP requests to the homeserver directly.

## Configuration

Reads from the **Matrix Settings** singleton:
- `homeserver_url` — API base URL (`https://matrix.glenda-studio-chat.com`)
- `bot_user_id` — full Matrix user ID (`@gs.bot:glenda-studio-chat.com`)
- `bot_access_token` — PAT stored as a Frappe Password field (encrypted at rest)
- `bot_is_admin` — Check field, gates admin-only operations like force-join

## Key design decisions

### Server name extraction

Matrix user IDs contain the server name (`@user:glenda-studio-chat.com`), which
differs from the API hostname (`matrix.glenda-studio-chat.com`). The function
`_server_name()` extracts the domain from `bot_user_id` by splitting on `:`.

```python
# @gs.bot:glenda-studio-chat.com → glenda-studio-chat.com
parts = bot_user_id.split(":", 1)
server_name = parts[1]
```

This is used by `get_matrix_user_id(username)` to build user IDs:
```
sonny.nguyen.01 → @sonny.nguyen.01:glenda-studio-chat.com
```

**Never** derive the server name from `homeserver_url`. This was the root cause
of a critical bug during initial development — room creation hung indefinitely
because Synapse tried to federate invites to `matrix.glenda-studio-chat.com`
(which doesn't exist as a Matrix server).

### POST vs PUT for send_message

The Matrix spec defines PUT for sending messages (with a transaction ID for
idempotency). Our Synapse + reverse proxy setup returns 500 on PUT. We use
POST instead, which works correctly. No transaction ID is needed since we
don't retry failed sends.

### HTML formatting

Matrix clients like Element don't auto-render markdown in plain `body` text.
To get bold/code formatting, messages must include both:
- `body` — plain text fallback (with `*bold*` and `` `code` `` notation)
- `formatted_body` — HTML version
- `format` — set to `"org.matrix.custom.html"`

The helper `_markdown_to_html()` converts our simple notation:
- `*text*` → `<strong>text</strong>`
- `` `text` `` → `<code>text</code>`
- newlines → `<br>`

## Functions

### `get_settings()`
Reads the Matrix Settings singleton. Throws if `enabled` is unchecked.

### `get_matrix_user_id(username, settings=None)`
Builds a full Matrix user ID from a plain username.
```
sonny.nguyen.01 → @sonny.nguyen.01:glenda-studio-chat.com
```

### `test_connection()`
`GET /_matrix/client/v3/account/whoami` — verifies the PAT is valid. Returns
the bot's identity JSON. Called from the "Test Connection" button in Matrix
Settings.

### `send_server_notice(target_matrix_user_id, message_text)`
`POST /_synapse/admin/v1/send_server_notice` — sends a DM notification.
Synapse auto-creates a notice room per user. This is the primary delivery
method for task notifications. Uses `msgtype: "m.text"` (triggers desktop
notifications).

Requires:
- Server notices enabled in homeserver.yaml
- `system_mxid_localpart` set to a **dedicated** user (not gs.bot) in homeserver.yaml
- The PAT user (gs.bot) must be a Synapse admin

### `send_message(room_id, message_text)`
`POST /_matrix/client/v3/rooms/{room_id}/send/m.room.message` — sends a
message to a group room. Uses `msgtype: "m.notice"` (does not trigger desktop
notifications, conventional for bot messages).

### `create_dm_room(target_matrix_user_id)`
`POST /_matrix/client/v3/createRoom` — creates a direct-message room with
`is_direct: true` and invites the target user. Uses 60s timeout (room creation
involves invite processing). Returns the room_id.

### `force_join_room(room_id, target_matrix_user_id)`
`POST /_synapse/admin/v1/join/{room_id}` — forces a user into a room via the
Synapse admin API. Only runs if `bot_is_admin` is checked. Used after
`create_dm_room()` to ensure the user is in the room even if they haven't
accepted the invite.

### `get_existing_dm_room(target_matrix_user_id)`
`GET /_matrix/client/v3/user/{bot_user_id}/account_data/m.direct` — checks if
a DM room already exists. Best-effort: returns None on 403 (MAS PATs lack
scope for account_data) or 404 (no m.direct data yet). Provisioning creates a
new room if this returns None.

## Error handling

### 401 responses
`_request()` catches 401 and throws a clear error telling the admin to
regenerate the PAT via the MAS admin panel. All 401s are also logged to the
`matrix` logger.

### Timeouts
Default: 10s (Synapse is on the same machine). Room creation and force-join
use 60s because they involve invite processing.

### Logging
All significant events logged via `frappe.logger("matrix")`. Log file:
`logs/matrix.log`. If this file was created by gunicorn (running as root), it
may need `chmod 777` to be writable by the bench user.
