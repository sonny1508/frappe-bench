"""
Matrix/Synapse HTTP client for the GS bot.

All Matrix API calls go through this module. Functions read credentials from the
Matrix Settings singleton and talk to the local Synapse instance.

Authentication: Uses a single long-lived PAT (Personal Access Token) generated
via the MAS admin panel for the gs.bot user. Since gs.bot is a Synapse admin,
this one token authenticates both:
- Matrix client API calls (send_message, createRoom, whoami)
- Synapse admin API calls (server notices, force-join)

If the token expires (401), calls raise a clear error so the admin knows to
replace it in Matrix Settings → Bot Access Token.
"""

import frappe
from frappe.utils.password import get_decrypted_password
import requests

TIMEOUT = 10  # seconds — Synapse is on the same machine


def get_settings():
	"""Read the Matrix Settings singleton."""
	settings = frappe.get_single("Matrix Settings")
	if not settings.enabled:
		frappe.throw("Matrix integration is not enabled.")
	return settings


def _get_access_token():
	"""Get the decrypted access token from Matrix Settings."""
	token = get_decrypted_password(
		"Matrix Settings", "Matrix Settings", "bot_access_token"
	)
	if not token:
		frappe.throw("Bot access token is not configured in Matrix Settings.")
	return token


def _server_name(settings=None):
	"""Extract the Matrix server name from the bot's own user ID.

	The server name in Matrix user IDs (e.g. glenda-studio-chat.com) is often
	different from the API hostname (e.g. matrix.glenda-studio-chat.com).
	The bot_user_id field already contains the correct server name.

	e.g. @gs.bot:glenda-studio-chat.com  →  glenda-studio-chat.com
	"""
	if settings is None:
		settings = get_settings()
	bot_user_id = settings.bot_user_id or ""
	# @gs.bot:glenda-studio-chat.com → glenda-studio-chat.com
	parts = bot_user_id.split(":", 1)
	if len(parts) == 2:
		return parts[1]
	frappe.throw(
		f"Cannot extract server name from bot_user_id: {bot_user_id}. "
		"Expected format: @botname:server.domain"
	)


def get_matrix_user_id(username, settings=None):
	"""Build a full Matrix user ID from a plain username.

	e.g. sonny.nguyen.01 → @sonny.nguyen.01:glenda-studio-chat.com
	"""
	domain = _server_name(settings)
	return f"@{username}:{domain}"


def _api_url(settings, path):
	"""Build the full API URL for a Matrix client or admin endpoint."""
	base = settings.homeserver_url.rstrip("/")
	return f"{base}{path}"


def _request(method, settings, path, **kwargs):
	"""Make an authenticated request to the Matrix API.

	Raises a clear error on 401 so the admin knows the token needs replacing.
	"""
	token = _get_access_token()
	headers = {"Authorization": f"Bearer {token}"}
	kwargs.setdefault("timeout", TIMEOUT)
	kwargs["headers"] = headers

	url = _api_url(settings, path)
	response = requests.request(method, url, **kwargs)

	if response.status_code == 401:
		error_msg = (
			"Matrix bot access token is invalid or expired. "
			"Generate a new long-lived token via the MAS admin panel "
			"(account.glenda-studio-chat.com) or Synapse admin API, "
			"then update it in Matrix Settings."
		)
		frappe.logger("matrix").error(error_msg)
		frappe.throw(error_msg)

	response.raise_for_status()
	return response


# ---------------------------------------------------------------------------
# Matrix Client API
# ---------------------------------------------------------------------------

def test_connection():
	"""GET /_matrix/client/v3/account/whoami — verify bot token is valid."""
	settings = get_settings()
	response = _request("GET", settings, "/_matrix/client/v3/account/whoami")
	return response.json()


def create_dm_room(target_matrix_user_id):
	"""Create a direct-message room and invite the target user.

	POST /_matrix/client/v3/createRoom

	Returns the room_id string (e.g. "!abc123:glenda-studio-chat.com").
	"""
	settings = get_settings()

	payload = {
		"is_direct": True,
		"invite": [target_matrix_user_id],
		"preset": "trusted_private_chat",
	}

	url = _api_url(settings, "/_matrix/client/v3/createRoom")
	frappe.logger("matrix").info(f"createRoom -> URL: {url} | invite: {target_matrix_user_id}")

	# Room creation can be slow (federation checks, invite processing) — use a longer timeout
	response = _request("POST", settings, "/_matrix/client/v3/createRoom", json=payload, timeout=60)
	result = response.json()
	frappe.logger("matrix").info(f"createRoom -> success: {result}")
	return result["room_id"]


def force_join_room(room_id, target_matrix_user_id):
	"""Force-join a user into a room via Synapse admin API.

	POST /_synapse/admin/v1/join/{room_id}

	Requires the bot to have Synapse admin privileges (bot_is_admin=True).
	"""
	settings = get_settings()

	if not settings.bot_is_admin:
		frappe.logger("matrix").warning(
			f"Cannot force-join {target_matrix_user_id} — bot is not a Synapse admin."
		)
		return None

	response = _request(
		"POST", settings, f"/_synapse/admin/v1/join/{room_id}",
		json={"user_id": target_matrix_user_id},
		timeout=60,
	)
	return response.json()


def get_existing_dm_room(target_matrix_user_id):
	"""Check if the bot already has a DM room with the target user.

	Reads the bot's m.direct account data, which maps user IDs to lists of
	room IDs that are marked as direct messages.

	Best-effort: returns None if the endpoint is inaccessible (403 with MAS
	Personal Access Tokens, 404 if no m.direct data set yet). Provisioning
	will just create a new room in that case.

	Returns the room_id string if found, or None.
	"""
	settings = get_settings()
	bot_user_id = settings.bot_user_id

	try:
		response = _request(
			"GET", settings,
			f"/_matrix/client/v3/user/{bot_user_id}/account_data/m.direct",
		)
		dm_map = response.json()

		# dm_map looks like: {"@user:domain": ["!roomA:domain", "!roomB:domain"], ...}
		rooms = dm_map.get(target_matrix_user_id, [])
		if rooms:
			return rooms[0]
	except requests.exceptions.HTTPError as e:
		if e.response is not None and e.response.status_code in (403, 404):
			# 403 = MAS token lacks scope for account_data (common with PATs)
			# 404 = No m.direct data set yet
			frappe.logger("matrix").info(
				f"Cannot check existing DM rooms for {target_matrix_user_id} "
				f"(HTTP {e.response.status_code}) — will create a new room instead."
			)
			return None
		raise
	except Exception as e:
		frappe.logger("matrix").warning(
			f"Could not query existing DM rooms for {target_matrix_user_id}: {e}"
		)

	return None


def _markdown_to_html(text):
	"""Convert our simple markdown-like notation to HTML for Matrix.

	Supports:
	- *text* → <strong>text</strong>  (bold)
	- `text` → <code>text</code>     (inline code)
	- newlines → <br>
	"""
	import re
	html = text
	# Bold: *text* → <strong>text</strong> (non-greedy, no nesting)
	html = re.sub(r'\*([^*]+)\*', r'<strong>\1</strong>', html)
	# Inline code: `text` → <code>text</code>
	html = re.sub(r'`([^`]+)`', r'<code>\1</code>', html)
	# Newlines → <br>
	html = html.replace('\n', '<br>\n')
	return html


def send_server_notice(target_matrix_user_id, message_text):
	"""Send a server notice to a user via the Synapse admin API.

	POST /_synapse/admin/v1/send_server_notice

	Synapse auto-creates a notice room per user — no room provisioning needed.
	Requires server_notices to be enabled in homeserver.yaml and the bot token
	to have admin privileges.

	Sends both plain-text body and HTML formatted_body so Element renders
	bold/code formatting correctly.
	"""
	settings = get_settings()

	payload = {
		"user_id": target_matrix_user_id,
		"content": {
			"msgtype": "m.text",
			"body": message_text,
			"format": "org.matrix.custom.html",
			"formatted_body": _markdown_to_html(message_text),
		},
	}

	response = _request(
		"POST", settings,
		"/_synapse/admin/v1/send_server_notice",
		json=payload,
	)
	return response.json()


def send_message(room_id, message_text):
	"""Send a text message to a room.

	POST /_matrix/client/v3/rooms/{room_id}/send/m.room.message

	Uses msgtype m.notice (conventional for bot messages — does not trigger
	desktop notifications on most clients).

	Sends both plain-text body and HTML formatted_body so Element renders
	bold/code formatting correctly.
	"""
	settings = get_settings()

	payload = {
		"msgtype": "m.notice",
		"body": message_text,
		"format": "org.matrix.custom.html",
		"formatted_body": _markdown_to_html(message_text),
	}

	response = _request(
		"POST", settings,
		f"/_matrix/client/v3/rooms/{room_id}/send/m.room.message",
		json=payload,
	)
	return response.json()


# ---------------------------------------------------------------------------
# Synapse Admin API
# ---------------------------------------------------------------------------

def list_rooms(search_term=None):
	"""List rooms from Synapse admin API with pagination.

	GET /_synapse/admin/v1/rooms
	"""
	settings = get_settings()

	if not settings.bot_is_admin:
		frappe.throw("Bot must have Synapse admin privileges to list rooms.")

	all_rooms = []
	offset = 0
	limit = 100

	while True:
		params = {"from": offset, "limit": limit, "dir": "f"}
		if search_term:
			params["search_term"] = search_term

		response = _request("GET", settings, "/_synapse/admin/v1/rooms", params=params)
		data = response.json()

		rooms = data.get("rooms", [])
		all_rooms.extend(rooms)

		if "next_batch" not in data or not rooms:
			break

		offset = data["next_batch"]

	return all_rooms


def delete_room(room_id):
	"""Delete and purge a room via Synapse admin API.

	POST /_synapse/admin/v1/rooms/{room_id}/delete  (synchronous)
	"""
	settings = get_settings()

	if not settings.bot_is_admin:
		frappe.throw("Bot must have Synapse admin privileges to delete rooms.")

	response = _request(
		"POST", settings,
		f"/_synapse/admin/v1/rooms/{room_id}/delete",
		json={"purge": True},
		timeout=30,
	)
	return response.json()
