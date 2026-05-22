# Troubleshooting

Issues encountered during development and their fixes. Ordered by likelihood
of recurrence.

## PAT expired / 401 on any API call

**Symptom**: Any Matrix API call returns 401. Error message in Frappe:
"Matrix bot access token is invalid or expired."

**Fix**: Generate a new PAT in the MAS admin panel at
`account.glenda-studio-chat.com`. Update the token in Matrix Settings →
Bot Access Token. The old PAT is invalid immediately.

**Note**: MAS PATs can expire. Check the expiry when creating them — set a
long duration or no expiry if possible.

## Code changes not taking effect

**Symptom**: You edited a Python file but the behavior doesn't change.

**Cause**: Gunicorn runs with `--preload`, which loads all code once at
startup. Workers share the preloaded code.

**Fix**: Restart all supervisord processes:
```bash
sudo supervisorctl restart all
```

`bench restart` alone may not be sufficient.

## Room creation hangs / times out

**Symptom**: `create_dm_room()` or "Provision DM Rooms" hangs for 60 seconds
then times out.

**Cause**: Wrong domain in Matrix user IDs. If user IDs use the API hostname
(`matrix.glenda-studio-chat.com`) instead of the server name
(`glenda-studio-chat.com`), Synapse tries to federate to a nonexistent
server and hangs.

**Fix**: Ensure `bot_user_id` in Matrix Settings is
`@gs.bot:glenda-studio-chat.com` (server name, NOT API hostname). The code
extracts the domain from this field.

**Verify**: Run from bench console:
```python
from gs_customizations.matrix.bot import get_matrix_user_id
print(get_matrix_user_id("sonny.nguyen.01"))
# Should print: @sonny.nguyen.01:glenda-studio-chat.com
# NOT: @sonny.nguyen.01:matrix.glenda-studio-chat.com
```

## 403 on send_server_notice (power levels)

**Symptom**: `send_server_notice` returns 403 with "user_level (0) <
send_level (50)".

**Cause**: The `system_mxid_localpart` in homeserver.yaml is set to an
existing user (like `gs.bot`) that has power level 0 in pre-existing rooms.

**Fix**: Change `system_mxid_localpart` to a dedicated name like
`server.notices` and restart Synapse (helm upgrade). See
[server-notices.md](server-notices.md) for details.

## 403 on m.direct account_data

**Symptom**: `get_existing_dm_room()` returns None with a 403 log message.

**Cause**: MAS Personal Access Tokens lack scope for the account_data
endpoint. This is expected behavior.

**Impact**: None. The function is best-effort — when it returns None, the
provisioning code creates a new room instead of reusing an existing one.
This may result in duplicate rooms but doesn't break functionality.

## 500 on PUT send_message

**Symptom**: Sending a message to a group room returns 500 Internal Server
Error.

**Cause**: Our Synapse + reverse proxy setup doesn't support PUT on the
send endpoint (the Matrix spec's preferred method with transaction ID).

**Fix**: Use POST instead of PUT. The code already does this. If someone
changes it back to PUT, they'll hit this issue again.

## Log file permission error

**Symptom**: `frappe.logger("matrix")` fails to write, or the log file is
empty.

**Cause**: `logs/matrix.log` was created by gunicorn (running as root) and
isn't writable by the bench user.

**Fix**:
```bash
sudo rm /home/uriel-server-01/frappe-bench/logs/matrix.log
touch /home/uriel-server-01/frappe-bench/logs/matrix.log
chmod 777 /home/uriel-server-01/frappe-bench/logs/matrix.log
```

## Login endpoint 404

**Symptom**: `POST /_matrix/client/v3/login` returns 404.

**Cause**: ESS Helm uses MAS (Matrix Authentication Service) for all auth.
MAS disables Synapse's native login endpoint. You cannot obtain a token via
login — you must create a PAT in the MAS admin panel.

**Impact**: Do not attempt to add a "login with password" flow. It will
never work with ESS Helm + MAS. Always use static PATs.

## frappe.utils.password import error

**Symptom**: `AttributeError: module 'frappe.utils' has no attribute
'password'`.

**Cause**: `frappe.utils.password` is not auto-imported when you access
`frappe.utils`.

**Fix**: Use explicit import:
```python
from frappe.utils.password import get_decrypted_password
```
