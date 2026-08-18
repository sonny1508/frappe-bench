"""
Food poll extraction from Matrix.

Reads MSC3381 poll events out of a Matrix room and turns them into structured
vote data for the Food Poll DocType.

The Element fork used here (see element-web/customizations/OPEN_POLL.md) adds an
"Undo vote" button, but does so in a spec-compliant way: an un-vote is sent as a
poll response with an empty `answers` array — a "spoiled" response per MSC3381.
So no fork-specific handling is needed. The standard tally rules cover it:

  1. Only responses sent after the poll start and (if ended) at or before the
     poll end event count.
  2. Per sender, only the most recent response counts.
  3. Answer IDs not defined by the poll are discarded; the remainder is
     truncated to `max_selections`.
  4. A response left with no valid answers is spoiled — that sender has no vote.

A sender whose latest response is spoiled but who *had* voted earlier is
recorded as "Withdrawn" rather than dropped, since those are usually the people
who DM the producer afterwards.
"""

import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, unquote

import frappe
from frappe.utils import convert_utc_to_system_timezone

from gs_customizations.matrix import bot

POLL_START_TYPES = ("org.matrix.msc3381.poll.start", "m.poll.start")
POLL_RESPONSE_TYPES = ("org.matrix.msc3381.poll.response", "m.poll.response")
POLL_END_TYPES = ("org.matrix.msc3381.poll.end", "m.poll.end")

# MSC1767 extensible-events text keys, most specific first
TEXT_KEYS = ("org.matrix.msc1767.text", "m.text", "body")

ROOM_ID_RE = re.compile(r"![A-Za-z0-9_\-+/=.]+:[A-Za-z0-9\-.]+")
ROOM_ALIAS_RE = re.compile(r"#[A-Za-z0-9_\-+/=.]+:[A-Za-z0-9\-.]+")
EVENT_ID_RE = re.compile(r"\$[A-Za-z0-9_\-+/=]+")

RELATIONS_PAGE_LIMIT = 100
RELATIONS_MAX_PAGES = 50  # safety bound; 5000 events is far beyond any real poll


# ---------------------------------------------------------------------------
# Parsing the producer's input
# ---------------------------------------------------------------------------

def parse_poll_reference(text):
	"""Extract (room_id, event_id) from whatever the producer pasted.

	Accepts:
	  - a matrix.to permalink
	    https://matrix.to/#/!room:server/$event?via=server
	  - an Element permalink (/#/room/!room:server/$event)
	  - the raw event source JSON copied out of Element
	  - a bare "!room:server/$event" pair

	Room aliases (#food:server) are resolved to a room ID via the directory API.
	"""
	if not text or not text.strip():
		frappe.throw("Paste a Matrix poll link (or the poll's event source) first.")

	text = text.strip()

	# Raw event JSON copied from Element's "View source"
	if text.startswith("{"):
		try:
			data = json.loads(text)
		except ValueError:
			frappe.throw(
				"That looks like JSON but could not be parsed. "
				"Paste the matrix.to link instead — it is all that is needed."
			)
		room_id = data.get("room_id")
		event_id = data.get("event_id")
		if not (room_id and event_id):
			frappe.throw(
				"That JSON has no room_id/event_id. Copy the poll's permalink "
				'("Share" on the poll message) and paste that instead.'
			)
		return room_id, event_id

	decoded = unquote(text)

	event_match = EVENT_ID_RE.search(decoded)
	if not event_match:
		frappe.throw(
			"Could not find an event ID (the <code>$...</code> part) in that link.<br><br>"
			"Use the poll message's <b>Share</b> option in Element to copy a link "
			"that looks like:<br>"
			"<code>https://matrix.to/#/!room:server/$event?via=server</code>"
		)
	event_id = event_match.group(0)

	room_match = ROOM_ID_RE.search(decoded)
	if room_match:
		return room_match.group(0), event_id

	alias_match = ROOM_ALIAS_RE.search(decoded)
	if alias_match:
		return resolve_room_alias(alias_match.group(0)), event_id

	frappe.throw(
		"Could not find a room ID (the <code>!...</code> part) in that link. "
		"Copy the poll's permalink again using <b>Share</b> on the poll message."
	)


def resolve_room_alias(alias, settings=None):
	"""GET /_matrix/client/v3/directory/room/{alias} — alias to room ID."""
	settings = settings or bot.get_settings()
	response = bot._request(
		"GET", settings, f"/_matrix/client/v3/directory/room/{quote(alias, safe='')}"
	)
	room_id = (response.json() or {}).get("room_id")
	if not room_id:
		frappe.throw(f"Could not resolve room alias {alias}.")
	return room_id


# ---------------------------------------------------------------------------
# Matrix reads
# ---------------------------------------------------------------------------

def _q(value):
	"""URL-encode a path segment (room and event IDs contain !, $, : and /)."""
	return quote(value or "", safe="")


def fetch_poll_event(room_id, event_id, settings=None):
	"""GET the poll start event itself."""
	settings = settings or bot.get_settings()
	try:
		response = bot._request(
			"GET", settings, f"/_matrix/client/v3/rooms/{_q(room_id)}/event/{_q(event_id)}"
		)
	except Exception as e:
		frappe.logger("matrix").error(f"Food poll: failed to read {event_id} in {room_id}: {e}")
		frappe.throw(
			f"Could not read that poll from Matrix.<br><br>"
			f"Room: <code>{frappe.utils.escape_html(room_id)}</code><br>"
			f"Event: <code>{frappe.utils.escape_html(event_id)}</code><br><br>"
			f"The bot must be a member of the room to read its history. Details: {e}"
		)

	event = response.json() or {}
	if event.get("type") not in POLL_START_TYPES:
		frappe.throw(
			f"That event is a <code>{frappe.utils.escape_html(event.get('type') or 'unknown')}</code>, "
			"not a poll. Make sure you copied the link from the poll message itself, "
			"not from a reply or a vote."
		)
	return event


def fetch_poll_relations(room_id, event_id, settings=None):
	"""Collect every event related to the poll via m.reference (votes + end)."""
	settings = settings or bot.get_settings()
	events = []
	from_token = None

	for _ in range(RELATIONS_MAX_PAGES):
		path = (
			f"/_matrix/client/v1/rooms/{_q(room_id)}/relations/"
			f"{_q(event_id)}/m.reference?limit={RELATIONS_PAGE_LIMIT}"
		)
		if from_token:
			path += f"&from={quote(from_token, safe='')}"

		data = bot._request("GET", settings, path).json() or {}
		events.extend(data.get("chunk") or [])

		from_token = data.get("next_batch")
		if not from_token:
			break

	return events


def fetch_display_names(room_id, settings=None):
	"""Map matrix_user_id -> display name for current room members.

	Best-effort: voters who have since left the room simply get no display name,
	and the Employee link (or the raw user ID) carries the identity instead.
	"""
	settings = settings or bot.get_settings()
	try:
		data = bot._request(
			"GET", settings, f"/_matrix/client/v3/rooms/{_q(room_id)}/joined_members"
		).json() or {}
	except Exception as e:
		frappe.logger("matrix").warning(f"Food poll: could not read members of {room_id}: {e}")
		return {}

	return {
		user_id: (info or {}).get("display_name") or ""
		for user_id, info in (data.get("joined") or {}).items()
	}


# ---------------------------------------------------------------------------
# Tallying
# ---------------------------------------------------------------------------

def _content_block(content, types):
	"""Pull the unstable-or-stable poll block out of an event's content."""
	for key in types:
		block = (content or {}).get(key)
		if isinstance(block, dict):
			return block
	return None


def _text(obj):
	"""Read the human-readable text out of an MSC1767 extensible-events block."""
	if isinstance(obj, str):
		return obj.strip()
	if not isinstance(obj, dict):
		return ""
	for key in TEXT_KEYS:
		value = obj.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip()
		# m.text can also be a list of {"body": ...} representations
		if isinstance(value, list):
			for rep in value:
				if isinstance(rep, dict) and (rep.get("body") or "").strip():
					return rep["body"].strip()
	return ""


def ts_to_system_datetime(ts_ms):
	"""Matrix origin_server_ts (ms since epoch, UTC) -> site-timezone datetime."""
	if not ts_ms:
		return None
	utc_naive = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
	return convert_utc_to_system_timezone(utc_naive).replace(tzinfo=None)


def tally_poll(start_event, related_events, display_names=None):
	"""Apply the MSC3381 tally rules. Returns a structured result dict."""
	display_names = display_names or {}

	content = start_event.get("content") or {}
	block = _content_block(content, POLL_START_TYPES) or {}

	question = _text(block.get("question")) or _text(content) or "Poll"
	try:
		max_selections = max(1, int(block.get("max_selections") or 1))
	except (TypeError, ValueError):
		max_selections = 1

	options = []
	option_order = {}
	for index, answer in enumerate(block.get("answers") or []):
		if not isinstance(answer, dict):
			continue
		option_id = answer.get("id")
		if not option_id or option_id in option_order:
			continue
		option_order[option_id] = index
		options.append(
			{
				"option_id": option_id,
				"option_text": _text(answer) or option_id,
				"vote_count": 0,
			}
		)
	valid_option_ids = set(option_order)

	poll_sender = start_event.get("sender") or ""
	start_ts = start_event.get("origin_server_ts") or 0

	# Poll end: per spec, only the poll's creator (or a redaction-capable user)
	# may end it, and the earliest such event wins. Prefer the creator's; fall
	# back to any end event so a room-admin close is still honoured.
	end_ts = None
	fallback_end_ts = None
	for event in related_events:
		if event.get("type") not in POLL_END_TYPES:
			continue
		ts = event.get("origin_server_ts") or 0
		if event.get("sender") == poll_sender:
			end_ts = ts if end_ts is None else min(end_ts, ts)
		else:
			fallback_end_ts = ts if fallback_end_ts is None else min(fallback_end_ts, ts)
	if end_ts is None:
		end_ts = fallback_end_ts

	# Per sender: their most recent response, and their most recent real vote.
	latest = {}
	latest_valid = {}
	for event in related_events:
		if event.get("type") not in POLL_RESPONSE_TYPES:
			continue
		sender = event.get("sender")
		if not sender:
			continue

		ts = event.get("origin_server_ts") or 0
		if ts < start_ts:
			continue
		if end_ts is not None and ts > end_ts:
			continue

		response_block = _content_block(event.get("content") or {}, POLL_RESPONSE_TYPES) or {}
		raw_answers = response_block.get("answers")
		picks = []
		if isinstance(raw_answers, list):
			seen = set()
			for answer_id in raw_answers:
				if isinstance(answer_id, str) and answer_id in valid_option_ids and answer_id not in seen:
					seen.add(answer_id)
					picks.append(answer_id)
			picks = picks[:max_selections]

		# Order by (timestamp, event_id) so the result is deterministic on ties.
		key = (ts, event.get("event_id") or "")
		if sender not in latest or key > latest[sender][0]:
			latest[sender] = (key, picks)
		if picks and (sender not in latest_valid or key > latest_valid[sender][0]):
			latest_valid[sender] = (key, picks)

	counts = {option_id: 0 for option_id in valid_option_ids}
	option_text = {opt["option_id"]: opt["option_text"] for opt in options}
	votes = []

	for sender, (key, picks) in latest.items():
		if picks:
			for option_id in picks:
				counts[option_id] += 1
				votes.append(
					{
						"matrix_user_id": sender,
						"display_name": display_names.get(sender, ""),
						"option_id": option_id,
						"option_text": option_text.get(option_id, option_id),
						"status": "Voted",
						"source": "Matrix",
						"voted_on": ts_to_system_datetime(key[0]),
					}
				)
			continue

		# Latest response was spoiled — an undo. Record what they had picked.
		withdrawn = latest_valid.get(sender)
		if not withdrawn:
			continue
		for option_id in withdrawn[1]:
			votes.append(
				{
					"matrix_user_id": sender,
					"display_name": display_names.get(sender, ""),
					"option_id": option_id,
					"option_text": option_text.get(option_id, option_id),
					"status": "Withdrawn",
					"source": "Matrix",
					"voted_on": ts_to_system_datetime(withdrawn[0][0]),
				}
			)

	for option in options:
		option["vote_count"] = counts.get(option["option_id"], 0)

	# Voted before Withdrawn, then poll option order, then name.
	votes.sort(
		key=lambda v: (
			v["status"] == "Withdrawn",
			option_order.get(v["option_id"], 999),
			(v["display_name"] or v["matrix_user_id"]).lower(),
		)
	)

	return {
		"question": question,
		"room_id": start_event.get("room_id"),
		"poll_event_id": start_event.get("event_id"),
		"poll_sender": poll_sender,
		"started_on": ts_to_system_datetime(start_ts),
		"poll_ended": 1 if end_ts is not None else 0,
		"ended_on": ts_to_system_datetime(end_ts),
		"max_selections": max_selections,
		"options": options,
		"votes": votes,
		"total_votes": sum(counts.values()),
	}


def read_poll(matrix_link):
	"""Full read: parse the link, fetch everything, return the tally."""
	room_id, event_id = parse_poll_reference(matrix_link)
	settings = bot.get_settings()

	start_event = fetch_poll_event(room_id, event_id, settings)
	related = fetch_poll_relations(room_id, event_id, settings)
	names = fetch_display_names(room_id, settings)

	result = tally_poll(start_event, related, names)
	# The event's own room_id is authoritative over whatever was in the link.
	result["room_id"] = start_event.get("room_id") or room_id
	result["poll_event_id"] = start_event.get("event_id") or event_id

	frappe.logger("matrix").info(
		f"Food poll read: {result['poll_event_id']} — "
		f"{len(result['options'])} options, {result['total_votes']} votes, "
		f"{len(related)} related events"
	)
	return result


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def resolve_employee(matrix_user_id, cache=None):
	"""Map @thong.nguyen.01:server -> Employee, via User.username.

	Mirrors bot.get_matrix_user_id() in reverse. Returns None when there is no
	matching User or Employee — voters without HR records are kept as raw
	Matrix IDs rather than blocking the import.
	"""
	if cache is None:
		cache = {}
	if matrix_user_id in cache:
		return cache[matrix_user_id]

	localpart = (matrix_user_id or "").split(":", 1)[0].lstrip("@")
	employee = None
	if localpart:
		user = frappe.db.get_value("User", {"username": localpart}, "name")
		if user:
			employee = frappe.db.get_value(
				"Employee", {"user_id": user, "status": "Active"}, "name"
			) or frappe.db.get_value("Employee", {"user_id": user}, "name")

	cache[matrix_user_id] = employee
	return employee


# ---------------------------------------------------------------------------
# Import entry point (called from the Food Poll list view)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def import_poll(matrix_link):
	"""Create or refresh a Food Poll from a Matrix poll link.

	Idempotent on poll_event_id: re-importing the same poll refreshes the
	existing document rather than creating a duplicate.
	"""
	room_id, event_id = parse_poll_reference(matrix_link)

	name = frappe.db.get_value("Food Poll", {"poll_event_id": event_id}, "name")
	if name:
		doc = frappe.get_doc("Food Poll", name)
		created = False
	else:
		doc = frappe.new_doc("Food Poll")
		created = True

	doc.matrix_link = (matrix_link or "").strip()
	doc.sync_from_matrix()
	doc.save()

	return {
		"name": doc.name,
		"created": created,
		"question": doc.question,
		"total_votes": doc.total_votes,
	}
