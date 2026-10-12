"""
Managed spaces: keeps people in every space and room under the root spaces
chosen in Matrix Settings → Spaces, at their minimum role or above.

Rules agreed with management:
- Power levels are restored on every sync. The sync never demotes anyone.
- A person is added to a room once. If they leave afterwards, that is respected.
- Taking someone off the steward list only stops enforcement for them.

How the bot gets authority in a room: being a Synapse admin gives no power
inside a room, because power levels are room state. make_room_admin borrows
the power of the most powerful local member still joined (usually
@administrator) to raise gs.bot to the same level, once per room. After that
the bot acts as an ordinary room admin. A room whose admins have all left
cannot be taken over; it is marked "Needs Admin" until someone with power
rejoins.

The engine does not care where a Matrix Room Member row came from: every row
with Enforce ticked in a managed room is enforced. Steward rows are generated
from the steward list; rows added any other way are enforced the same way.
"""

import copy

import frappe
import requests
from frappe.utils import now_datetime
from frappe.utils.file_lock import LockTimeoutError
from frappe.utils.synchronization import filelock

from gs_customizations.matrix import bot

ROLE_LEVELS = {"Default": 0, "Moderator": 50, "Admin": 100}

MEMBERSHIP_LABELS = {
	"join": "Joined",
	"invite": "Invited",
	"leave": "Left",
	"ban": "Banned",
}

SPACE_TYPE = "m.space"
LOCK_NAME = "matrix_space_sync"
REALTIME_EVENT = "matrix_space_sync"

ROOM_DT = "Matrix Room"
MEMBER_DT = "Matrix Room Member"


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

def matrix_user_id_for_employee(employee, settings=None):
	"""Employee → User → username → @username:server, or None if any link is missing."""
	user_id = frappe.db.get_value("Employee", employee, "user_id")
	if not user_id:
		return None
	username = frappe.db.get_value("User", user_id, "username")
	if not username:
		return None
	return bot.get_matrix_user_id(username, settings)


# ---------------------------------------------------------------------------
# Room state
# ---------------------------------------------------------------------------

class RoomState:
	"""The parts of a room's current state the sync cares about."""

	def __init__(self, room_id, events):
		self.room_id = room_id
		self.name = None
		self.room_type = None
		self.join_rule = None
		self.power_levels = None
		self.membership = {}
		self.children = []

		for event in events:
			etype = event.get("type")
			content = event.get("content") or {}
			if etype == "m.room.create":
				self.room_type = content.get("type")
			elif etype == "m.room.name":
				self.name = content.get("name")
			elif etype == "m.room.join_rules":
				self.join_rule = content.get("join_rule")
			elif etype == "m.room.power_levels":
				self.power_levels = content
			elif etype == "m.room.member":
				self.membership[event.get("state_key")] = content.get("membership")
			elif etype == "m.space.child" and content.get("via"):
				# A child entry with empty content (no "via") means "removed"
				self.children.append(event.get("state_key"))

	@property
	def is_space(self):
		return self.room_type == SPACE_TYPE

	@property
	def joined_count(self):
		return sum(1 for m in self.membership.values() if m == "join")

	def joined(self, user_id):
		return self.membership.get(user_id) == "join"

	def power_level(self, user_id):
		pl = self.power_levels or {}
		return int(pl.get("users", {}).get(user_id, pl.get("users_default", 0)))

	def required_level(self, max_target):
		"""Power the bot needs here: edit power levels, invite, and grant max_target."""
		pl = self.power_levels or {}
		change_pl = pl.get("events", {}).get("m.room.power_levels", pl.get("state_default", 50))
		return max(int(change_pl), int(pl.get("invite", 0)), max_target)

	def lendable_level(self, server_name):
		"""Highest level make_room_admin could hand out: the strongest joined local user
		listed in the power levels. None if there is nobody to borrow from."""
		users = (self.power_levels or {}).get("users", {})
		levels = [
			int(level) for user_id, level in users.items()
			if user_id.endswith(f":{server_name}") and self.joined(user_id)
		]
		return max(levels, default=None)


def _fetch_state(room_id):
	events = bot.get_room_state(room_id)
	return None if events is None else RoomState(room_id, events)


def _walk(root_id, seen):
	"""Collect a root space's tree, top-down (a space before anything inside it).

	Breadth-first, so the bot and the people being added are in a space before
	they are pulled into its rooms. Rooms already in `seen` (cycles, or a room
	reachable from two managed roots) are visited only once.

	Returns (nodes, complete): nodes is a list of (room_id, parent_id, RoomState);
	complete is False if any state fetch failed, in which case rooms missing
	from this walk must not be treated as removed.
	"""
	nodes = []
	complete = True
	queue = [(root_id, None)]

	while queue:
		room_id, parent_id = queue.pop(0)
		if room_id in seen:
			continue
		seen.add(room_id)

		try:
			state = _fetch_state(room_id)
		except Exception as e:
			frappe.logger("matrix").error(f"Space sync: cannot read state of {room_id}: {e}")
			complete = False
			continue

		if state is None:
			# Listed by a space but deleted from the server
			continue

		nodes.append((room_id, parent_id, state))
		if state.is_space:
			queue.extend((child, room_id) for child in state.children)

	return nodes, complete


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_root_spaces():
	"""Register every root space on the server as a Matrix Room, so it can be
	picked as a managed root in Matrix Settings.

	A root space is a space with members that no other live space lists as a
	child. Empty spaces (no joined members) are ignored.
	"""
	spaces = [
		r for r in bot.list_rooms()
		if r.get("room_type") == SPACE_TYPE and r.get("joined_members")
	]

	child_ids = set()
	for space in spaces:
		state = _fetch_state(space["room_id"])
		if state:
			child_ids.update(state.children)

	roots = [s for s in spaces if s["room_id"] not in child_ids]
	new = 0
	for space in roots:
		values = {
			"room_name": space.get("name") or "",
			"room_type": "Space",
			"parent_space": None,
			"root_space": space["room_id"],
			"join_rule": space.get("join_rules") or "",
			"joined_members": space.get("joined_members") or 0,
		}
		if _upsert_room(space["room_id"], values):
			new += 1

	return {"found": len(roots), "new": new}


# ---------------------------------------------------------------------------
# Sync entry points
# ---------------------------------------------------------------------------

def scheduled_sync():
	"""Scheduler entry point (every 10 minutes, see hooks.py)."""
	settings = frappe.get_single("Matrix Settings")
	if not settings.enabled or not settings.spaces_sync_enabled:
		return
	sync_managed_spaces()


def enqueue_sync(notify_user=None):
	"""Run a sync in the background. Repeated clicks collapse into one job."""
	frappe.enqueue(
		"gs_customizations.matrix.spaces.sync_managed_spaces",
		queue="long",
		job_id=LOCK_NAME,
		deduplicate=True,
		notify_user=notify_user,
	)


def sync_managed_spaces(notify_user=None):
	"""Bring every managed space and room in line with its Matrix Room Member rows."""
	try:
		with filelock(LOCK_NAME, timeout=1):
			summary = _sync()
	except LockTimeoutError:
		frappe.logger("matrix").info("Space sync already running — skipped.")
		return {"skipped": "already running"}

	if notify_user:
		frappe.publish_realtime(REALTIME_EVENT, summary, user=notify_user)
	return summary


def _sync():
	settings = bot.get_settings()
	if not settings.bot_is_admin:
		frappe.throw("Space sync needs the bot to have Synapse admin privileges.")

	bot_id = settings.bot_user_id
	server_name = bot._server_name(settings)
	roots = [row.space for row in settings.managed_root_spaces]
	stewards = _steward_targets(settings)

	summary = {
		"rooms": 0, "ok": 0, "needs_admin": 0, "errors": 0,
		"joined": 0, "promoted": 0, "unmanaged": 0,
	}

	# 1. Walk every managed tree
	seen = set()
	managed = []  # (room_id, root_id, parent_id, state), top-down
	complete_roots = set()
	for root_id in roots:
		nodes, complete = _walk(root_id, seen)
		managed.extend((room_id, root_id, parent_id, state) for room_id, parent_id, state in nodes)
		if complete:
			complete_roots.add(root_id)

	# 2. Stop enforcing for anyone taken off the steward list
	_delete_rows({"source": "Steward", "matrix_user_id": ["not in", list(stewards) or [""]]})

	# 3. Enforce room by room, top-down
	for room_id, root_id, parent_id, state in managed:
		summary["rooms"] += 1
		_upsert_room(room_id, {
			"room_name": state.name or "",
			"room_type": "Space" if state.is_space else "Room",
			"parent_space": parent_id,
			"root_space": root_id,
		})
		_ensure_steward_rows(room_id, stewards)

		try:
			result = _enforce_room(room_id, state, bot_id, server_name)
		except Exception as e:
			frappe.logger("matrix").exception(f"Space sync failed for {room_id}")
			result = {"status": "Error", "error": _error_text(e), "state": state}

		final = result["state"]
		frappe.db.set_value(ROOM_DT, room_id, {
			"status": result["status"],
			"last_error": result.get("error") or "",
			"join_rule": final.join_rule or "",
			"joined_members": final.joined_count,
			"bot_power_level": final.power_level(bot_id) if final.joined(bot_id) else 0,
			"last_synced": now_datetime(),
		}, update_modified=False)

		summary["joined"] += result.get("joined", 0)
		summary["promoted"] += result.get("promoted", 0)
		key = {"OK": "ok", "Needs Admin": "needs_admin"}.get(result["status"], "errors")
		summary[key] += 1
		frappe.db.commit()

	# 4. Rooms that dropped out of a managed tree (or whose root was unticked)
	managed_ids = {room_id for room_id, *_ in managed}
	for room in frappe.get_all(
		ROOM_DT,
		filters={"status": ["!=", "Not Managed"]},
		fields=["name", "root_space"],
	):
		if room.name in managed_ids:
			continue
		if room.root_space in roots and room.root_space not in complete_roots:
			continue  # walk was incomplete — can't tell whether it really left
		frappe.db.set_value(ROOM_DT, room.name, "status", "Not Managed", update_modified=False)
		_delete_rows({"source": "Steward", "room": room.name})
		summary["unmanaged"] += 1

	frappe.db.set_single_value("Matrix Settings", {
		"spaces_last_sync": now_datetime(),
		"spaces_last_sync_summary": _summary_text(summary),
	}, update_modified=False)
	frappe.db.commit()

	frappe.logger("matrix").info(f"Space sync complete: {summary}")
	return summary


# ---------------------------------------------------------------------------
# Per-room enforcement
# ---------------------------------------------------------------------------

def _enforce_room(room_id, state, bot_id, server_name):
	"""Get the bot power in the room, add people once, raise power levels.

	Returns {"status", "error", "state", "joined", "promoted"}.
	"""
	rows = frappe.get_all(
		MEMBER_DT,
		filters={"room": room_id, "enforce": 1},
		fields=["name", "matrix_user_id", "min_role", "joined_before"],
	)
	max_target = max((ROLE_LEVELS.get(r.min_role, 0) for r in rows), default=0)
	needed = state.required_level(max_target)

	# --- The bot needs power before it can do anything else
	if not (state.joined(bot_id) and state.power_level(bot_id) >= needed):
		if state.power_level(bot_id) < needed:
			lendable = state.lendable_level(server_name)
			if lendable is None or lendable <= state.power_level(bot_id):
				_record_rows(rows, state)
				return {
					"status": "Needs Admin",
					"error": _no_admin_message(state),
					"state": state,
				}
			bot.make_room_admin(room_id, bot_id)  # also invites the bot if needed
			state = _fetch_state(room_id)

		if not state.joined(bot_id):
			bot.join_room(room_id)
			state = _fetch_state(room_id)

		have = state.power_level(bot_id)
		if not state.joined(bot_id) or have < needed:
			_record_rows(rows, state)
			return {
				"status": "Needs Admin",
				"error": (
					f"gs.bot could only get power level {have} here; it needs {needed}. "
					"Someone with Admin power must rejoin the room, then sync again."
				),
				"state": state,
			}

	# --- Add people who have never been in the room
	errors = {}
	joined = 0
	now = now_datetime()
	for row in rows:
		membership = state.membership.get(row.matrix_user_id)
		if membership in ("join", "leave", "ban"):
			# Joined, or already left (incl. kicked / rejected invite) — either way
			# the one-time add is spent.
			if not row.joined_before:
				frappe.db.set_value(MEMBER_DT, row.name, "joined_before", 1)
				row.joined_before = 1
			continue
		if row.joined_before:
			continue  # was in the room before and left — respect it

		try:
			bot.force_join_room(room_id, row.matrix_user_id)
			frappe.db.set_value(MEMBER_DT, row.name, {"joined_before": 1, "added_by_bot_on": now})
			row.joined_before = 1
			joined += 1
		except Exception as e:
			errors[row.name] = f"Could not add to room: {_error_text(e)}"

	if joined:
		state = _fetch_state(room_id)

	# --- Raise power levels (never lower). Only people currently in the room.
	promoted = 0
	raise_to = {}
	for row in rows:
		target = ROLE_LEVELS.get(row.min_role, 0)
		if state.joined(row.matrix_user_id) and state.power_level(row.matrix_user_id) < target:
			raise_to[row.matrix_user_id] = target

	if raise_to:
		content = copy.deepcopy(state.power_levels or {})
		content.setdefault("users", {}).update(raise_to)
		try:
			bot.set_power_levels(room_id, content)
			promoted = len(raise_to)
			state = _fetch_state(room_id)
		except Exception as e:
			message = f"Could not set power level: {_error_text(e)}"
			for row in rows:
				if row.matrix_user_id in raise_to:
					errors[row.name] = message

	_record_rows(rows, state, errors)
	return {
		"status": "Error" if errors else "OK",
		"error": f"{len(errors)} member(s) failed — see Matrix Room Member" if errors else "",
		"state": state,
		"joined": joined,
		"promoted": promoted,
	}


def _record_rows(rows, state, errors=None):
	"""Write what the server says back onto each member row, only where it changed."""
	errors = errors or {}
	for row in rows:
		current = frappe.db.get_value(
			MEMBER_DT, row.name, ["membership", "current_power_level", "last_error"], as_dict=True,
		)
		values = {
			"membership": MEMBERSHIP_LABELS.get(state.membership.get(row.matrix_user_id), "Not Joined"),
			"current_power_level": state.power_level(row.matrix_user_id),
			"last_error": errors.get(row.name, ""),
		}
		changed = {k: v for k, v in values.items() if (current.get(k) or "") != (v or "")}
		if changed:
			frappe.db.set_value(MEMBER_DT, row.name, changed)


def _no_admin_message(state):
	if not state.joined_count:
		return "Nobody is in this room any more."
	return (
		"Nobody with power is left in this room, so gs.bot cannot be made admin. "
		"Someone who used to be Admin here must rejoin, then sync again."
	)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def _upsert_room(room_id, values):
	"""Create or update a Matrix Room. Returns True if it was created.

	Fetched copies on Matrix Room Member rows are refreshed when the room's
	name, type or root changes.
	"""
	if not frappe.db.exists(ROOM_DT, room_id):
		doc = frappe.get_doc({"doctype": ROOM_DT, "room_id": room_id, **values})
		doc.flags.ignore_links = True  # a root space is its own root_space
		doc.insert(ignore_permissions=True)
		return True

	current = frappe.db.get_value(ROOM_DT, room_id, list(values), as_dict=True)
	changed = {k: v for k, v in values.items() if (current.get(k) or "") != (v or "")}
	if changed:
		frappe.db.set_value(ROOM_DT, room_id, changed)
		fetched = {k: changed[k] for k in ("room_name", "room_type", "root_space") if k in changed}
		if fetched:
			frappe.db.set_value(MEMBER_DT, {"room": room_id}, fetched, update_modified=False)
	return False


def _steward_targets(settings):
	"""{matrix_user_id: {"employee", "min_role"}} from the steward table."""
	targets = {}
	for row in settings.stewards:
		matrix_id = matrix_user_id_for_employee(row.employee, settings)
		if not matrix_id:
			frappe.logger("matrix").warning(
				f"Space sync: steward {row.employee} has no User username — skipped."
			)
			continue
		targets[matrix_id] = {"employee": row.employee, "min_role": row.min_role or "Moderator"}
	return targets


def _ensure_steward_rows(room_id, stewards):
	"""One Steward row per steward in this room, with the steward's current role.

	The Enforce checkbox is left alone, so unticking it on a single room is a
	lasting exception for that person in that room.
	"""
	existing = {
		r.matrix_user_id: r for r in frappe.get_all(
			MEMBER_DT,
			filters={"room": room_id, "matrix_user_id": ["in", list(stewards) or [""]]},
			fields=["name", "matrix_user_id", "source", "min_role"],
		)
	}
	for matrix_id, steward in stewards.items():
		row = existing.get(matrix_id)
		if row is None:
			frappe.get_doc({
				"doctype": MEMBER_DT,
				"room": room_id,
				"employee": steward["employee"],
				"matrix_user_id": matrix_id,
				"source": "Steward",
				"min_role": steward["min_role"],
				"enforce": 1,
			}).insert(ignore_permissions=True)
		elif row.source != "Steward" or row.min_role != steward["min_role"]:
			frappe.db.set_value(MEMBER_DT, row.name, {
				"source": "Steward", "min_role": steward["min_role"],
			})


def _delete_rows(filters):
	for name in frappe.get_all(MEMBER_DT, filters=filters, pluck="name"):
		frappe.delete_doc(MEMBER_DT, name, ignore_permissions=True, force=True)


def _error_text(e):
	"""Prefer Synapse's own error message over the generic HTTPError text."""
	response = getattr(e, "response", None)
	if isinstance(e, requests.exceptions.HTTPError) and response is not None:
		try:
			body = response.json()
			return f"HTTP {response.status_code} {body.get('errcode', '')}: {body.get('error', '')}"[:500]
		except ValueError:
			return f"HTTP {response.status_code}: {response.text}"[:500]
	return str(e)[:500]


def _summary_text(s):
	return (
		f"{s['rooms']} rooms: {s['ok']} OK, {s['needs_admin']} need an admin, "
		f"{s['errors']} with errors. Added {s['joined']} member(s), "
		f"raised {s['promoted']} power level(s). {s['unmanaged']} room(s) no longer managed."
	)
