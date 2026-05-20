# Matrix Integration — Overview

Sends task notifications to employees via Element/Matrix, replacing the older
Synology Chat webhook system. Both systems currently run side-by-side — Synology
hooks are untouched and fire independently until manually disabled.

## Infrastructure

- **Homeserver**: Self-hosted Synapse via ESS Helm (Element Server Suite)
- **Client**: Element Web / Element mobile apps
- **Auth**: MAS (Matrix Authentication Service) — handles all user login via OIDC.
  Synapse's native `/_matrix/client/v3/login` is disabled.
- **Bot user**: `@gs.bot:glenda-studio-chat.com` — a Synapse admin

### Domain split (important)

ESS Helm separates two things that look similar but are different:

| Concept | Value | Used for |
|---|---|---|
| API hostname | `matrix.glenda-studio-chat.com` | All HTTP API calls (homeserver_url) |
| Matrix server name | `glenda-studio-chat.com` | The part after `:` in user IDs |

The bot_user_id is `@gs.bot:glenda-studio-chat.com` (server name), but API
requests go to `https://matrix.glenda-studio-chat.com` (API hostname). The
code extracts the server name from `bot_user_id`, NOT from `homeserver_url`.
Getting this wrong causes room creation to hang forever (Synapse tries to
federate to a nonexistent server).

## How notifications are delivered

**DM notifications** (task status changes, new assignments) use **Synapse Server
Notices** via the admin API (`/_synapse/admin/v1/send_server_notice`). Synapse
auto-creates a notice room per user — no room provisioning or lookup is needed.
The server notice sender is a dedicated internal user configured in
homeserver.yaml (`system_mxid_localpart`), separate from the bot user.

**Group room messages** (future use) use the **Matrix client API**
(`/_matrix/client/v3/rooms/{room_id}/send/m.room.message`) with the bot sending
directly to rooms listed in the Group Rooms child table.

## Authentication

A single PAT (Personal Access Token) for gs.bot, generated in the MAS admin
panel (`account.glenda-studio-chat.com`), authenticates ALL API calls — both
client API and admin API. Synapse checks if the authenticated user has admin
privileges when admin endpoints are hit. The PAT is stored encrypted in the
`bot_access_token` Password field on Matrix Settings.

**Do not** attempt to use `/_matrix/client/v3/login` — MAS disables this
endpoint. Always use a static PAT.

## File structure

```
gs_customizations/
  matrix/                              # Business logic
    __init__.py
    bot.py                             # HTTP client — all Matrix/Synapse API calls
    provisioning.py                    # DM room creation logic
    notifications.py                   # Task notification hooks (mirrors synology.py)

  matrix_integration/                  # Frappe module (DocTypes)
    __init__.py
    doctype/
      matrix_settings/                 # Singleton — bot config, room tables, dev tools
        matrix_settings.json
        matrix_settings.py
        matrix_settings.js
      matrix_dm_room/                  # Child table for DM rooms
        matrix_dm_room.json
        matrix_dm_room.py
      matrix_group_room/               # Child table for group rooms
        matrix_group_room.json
        matrix_group_room.py
```

## Related files (not in matrix/)

- `hooks.py` — doc_events wiring for Task on_update, ToDo after_insert, Employee on_update
- `customize/customize_fields.py` — `custom_enable_matrix_notifications` Check field on Employee
- `patches/add_employee_matrix_field.py` — migration patch for the custom field
- `modules.txt` — includes "Matrix Integration" as a Frappe module
