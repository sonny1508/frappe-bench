# Synapse Server Notices

Server notices are the primary mechanism for DM notifications. This doc covers
the Synapse-side configuration and how it interacts with our code.

## What server notices are

A Synapse feature where a dedicated internal user sends messages to users
automatically. Synapse creates a "Server Notices" room per user on first
contact — no room provisioning needed on our side.

## Synapse configuration (homeserver.yaml)

```yaml
server_notices:
  system_mxid_localpart: "server.notices"
  system_mxid_display_name: "GS Notifications"
  room_name: "Server Notices"
```

### Critical: system_mxid_localpart

This must be a **dedicated user**, NOT the bot user (`gs.bot`). If set to
`gs.bot`, the server notice rooms may reuse existing DM rooms where gs.bot
has power level 0, causing 403 errors:

```
"You don't have permission to post that to the room.
 user_level (0) < send_level (50)"
```

With a dedicated user like `server.notices`, Synapse creates fresh rooms
where the notice user gets power level 50 automatically.

After changing this value, run `helm upgrade` (or restart Synapse) and the
new user is auto-created.

## API call

```
POST /_synapse/admin/v1/send_server_notice
Authorization: Bearer <PAT>

{
  "user_id": "@sonny.nguyen.01:glenda-studio-chat.com",
  "content": {
    "msgtype": "m.text",
    "body": "plain text fallback",
    "format": "org.matrix.custom.html",
    "formatted_body": "<strong>bold</strong> HTML version"
  }
}
```

The PAT must belong to a **Synapse admin** user. The admin user (gs.bot)
makes the API call; the `system_mxid_localpart` user (server.notices) is the
one that actually appears as the sender in the room.

## How our code uses it

1. `notifications.py` hook fires on Task update or ToDo insert
2. Resolves recipients (assignees/subscribers) to usernames
3. Filters by `custom_enable_matrix_notifications` per employee
4. For each recipient: `bot.get_matrix_user_id(username)` → `bot.send_server_notice()`
5. `send_server_notice()` sends both `body` and `formatted_body` for rich text

## Server notices vs bot DM rooms

| Aspect | Server Notices | Bot DM Rooms |
|---|---|---|
| Room creation | Automatic by Synapse | Manual via provisioning |
| Sender | `@server.notices:...` | `@gs.bot:...` |
| API | Admin API (`/_synapse/admin/`) | Client API (`/_matrix/client/`) |
| msgtype | `m.text` (triggers notifications) | `m.notice` (silent) |
| Used for | Task DM notifications | Not currently used |
| Room listed in | Not stored in our DB | DM Rooms child table |

## Troubleshooting

### 403 "user_level (0) < send_level (50)"
The `system_mxid_localpart` in homeserver.yaml is set to a user that has
power level 0 in existing rooms. Fix: change to a dedicated user name that
has never been used, then helm upgrade.

### 403 on admin API (not a server admin)
The PAT user is not flagged as a Synapse admin. In ESS Helm, admin status is
managed via MAS admin settings.

### 401 on send_server_notice
PAT expired. Generate a new one in the MAS admin panel
(`account.glenda-studio-chat.com`) and update Matrix Settings.
