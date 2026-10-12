# Managed Spaces — Stewards and Room Membership

Keeps a fixed list of key people (**stewards**) in every space and room under
chosen root spaces, at Moderator or above, so nobody has to hand out power
levels room by room.

- `gs_customizations/matrix/spaces.py` — discovery + the sync engine
- `matrix_integration/doctype/matrix_room/` — registry of spaces and rooms
- `matrix_integration/doctype/matrix_room_member/` — one row per person per room
- `matrix_integration/doctype/matrix_managed_space/` — child: managed root spaces
- `matrix_integration/doctype/matrix_space_steward/` — child: the steward list
- **Matrix Settings → Spaces** tab — configuration

## Rules (agreed with management)

| Situation | What the sync does |
|---|---|
| Steward below their minimum role | Raised back on every sync. A demotion is always treated as a mistake. |
| Steward above their minimum role | Left alone. The sync never lowers anyone. |
| Steward never been in a room | Added once, by force-join. |
| Steward left (or was kicked, or rejected the invite) | Respected — never added back. Also applies to anyone who had already left before syncing started. |
| Steward taken off the list | Their Steward rows are deleted. Enforcement stops; nobody is demoted or removed. |
| Room taken out of a managed space, or root space unticked | Room becomes **Not Managed**; its Steward rows are deleted. |

## Setup

1. **Matrix Settings → Spaces → Discover Root Spaces.** Registers every root
   space with members (a space no other live space lists as a child) as a
   Matrix Room. Run again whenever a new top-level space is created.
2. Pick **Managed Root Spaces** (only root spaces are offered).
3. Fill the **Stewards** table: Employee + Minimum Role (Moderator / Admin).
4. Tick **Keep Managed Spaces in Sync** and save.
5. **Spaces → Sync Now**, or wait up to 10 minutes for the scheduler.

## How the bot gets authority in a room

Being a Synapse server admin gives **no** power inside a room: power levels are
room state, checked by the room's own auth rules. The bridge is
`make_room_admin` (Synapse admin API): Synapse sends a power-level change *as*
the most powerful local member still joined to the room — usually
`@administrator` — raising gs.bot to the same level, and invites it. The bot
then joins and from there on works as an ordinary room Admin (100).

This happens once per room. Other room admins cannot demote or kick the bot
afterwards (Matrix only allows that against someone with a *lower* level), so a
room cannot lose all its admins again while the bot is in it.

Visible side effects in the room timeline: "Administrator changed the power
level of GS Bot", "GS Bot joined", "GS Bot invited …", "GS Bot changed the power
level of … from Default to Moderator".

### Needs Admin

If nobody with power is left in a room (every admin left), `make_room_admin` has
nobody to borrow from and the room is marked **Needs Admin**. The sync detects
this from the room state and does not call the API at all, so it doesn't spam the
timeline every 10 minutes.

Fix: someone who used to be Admin there rejoins (restricted rooms let members of
the parent space walk in), then **Sync Now**. As of 2026-10-12, `HW3 | Core` and
`SCR1 | Core` in Operation are in this state — `@administrator` was their admin.

**Spaces → Rooms Needing Attention** lists every room in Needs Admin or Error.

## The sync, step by step

`sync_managed_spaces()` — scheduler every 10 minutes (`scheduled_sync`, gated by
the checkbox) and the Sync Now button (`enqueue_sync`, long queue,
deduplicated). A file lock (`sites/<site>/locks/matrix_space_sync.lock`)
stops two syncs overlapping.

1. **Walk** each managed root breadth-first via the admin state API
   (`m.space.child` events). The bot does not need to be in a room to read it.
   Spaces come before the rooms inside them, so the bot and stewards are in a
   space before being pulled into its restricted rooms. Cycle-safe; a room
   reachable from two managed roots is handled once. Children that no longer
   exist on the server (stale `m.space.child`) are skipped.
2. **Drop** Steward rows for anyone no longer on the steward list.
3. For each room, top-down:
   - upsert the **Matrix Room** record;
   - ensure one **Steward** row per steward (keeps the Enforce checkbox as the
     user left it, so unticking it on one room is a lasting exception);
   - **bot power** — if the bot is not joined with enough power (the level
     needed to edit power levels, to invite, and to grant the highest minimum
     role): `make_room_admin` → `join_room`;
   - **add once** — force-join every enforced row that has never been in the
     room (`joined_before` unticked);
   - **raise power** — one `m.room.power_levels` update for everyone in the room
     below their minimum role;
   - write membership / current power level / errors back onto the rows.
   Each room is committed on its own, so a crash mid-sync keeps what was done.
4. **Unmanage** rooms that dropped out of a managed tree. Skipped for any root
   whose walk was incomplete (a state fetch failed), so a network blip can't
   delete rows.

## Data model

### Matrix Room — one record per space *or* room

In Matrix a space is a room with a type flag; join, power levels and kicks are
the same API calls. One DocType covers both (`room_type` = Space / Room).

Named by room ID (`!abc:glenda-studio-chat.com`); `room_name` is the title, and
Link fields show the title. Written only by the sync (`in_create`, all fields
read-only). Hierarchy is plain `parent_space` / `root_space` links rather than a
Frappe tree DocType: Matrix allows a room in more than one space, which a
nested-set tree cannot represent.

| Status | Meaning |
|---|---|
| OK | Bot is Admin, everything enforced |
| Needs Admin | Nobody with power left — see above |
| Error | A call failed; see Last Error (room) or the member rows |
| Not Managed | Discovered root space not ticked, or room no longer under a managed root |

### Matrix Room Member — one row per person per room

A top-level DocType rather than a child table, because Frappe list filters,
group-by and bulk actions only work on top-level DocTypes. Department,
designation and employee status are fetched from Employee for filtering.

| Field | Notes |
|---|---|
| `employee` / `matrix_user_id` | Matrix ID always derived from the employee's User.username in `validate()`. Unique per room. |
| `source` | **Steward** (generated from the steward list, owned by the sync) or **Manual** |
| `min_role` | Default (0) / Moderator (50) / Admin (100). Raised to, never lowered. |
| `enforce` | Untick to stop managing this person in this room. |
| `membership` | As seen on the server: Joined / Invited / Left / Banned / Not Joined |
| `joined_before` | The "add once" memory. Once ticked, leaving is respected. |
| `added_by_bot_on` | When the bot force-joined them, if it did. |

The engine does not care about `source`: **any** enforced row in a managed room
is enforced the same way. Manual rows (created by hand or via Data Import) are
already honoured — that is the base for batch membership by department later.

## API calls used

| Call | API | Purpose |
|---|---|---|
| `GET /_synapse/admin/v1/rooms` | admin | Discovery: list spaces |
| `GET /_synapse/admin/v1/rooms/{room}/state` | admin | Tree walk, membership, power levels |
| `POST /_synapse/admin/v1/rooms/{room}/make_room_admin` | admin | Bootstrap bot power (once per room) |
| `POST /_matrix/client/v3/join/{room}` | client | Bot joins |
| `POST /_synapse/admin/v1/join/{room}` | admin | Force-join a person |
| `PUT /_matrix/client/v3/rooms/{room}/state/m.room.power_levels/` | client | Raise power levels |

### Rate limits

gs.bot is exempt from Synapse rate limits via
`POST /_synapse/admin/v1/users/@gs.bot:glenda-studio-chat.com/override_ratelimit`
with `messages_per_second: 0` (set 2026-10-12, `bot.override_ratelimit()`).
Synapse reads a zero there as "no rate limiting at all" — joins included.
Without it, the first sync of a large tree gets throttled after ~10 joins.

## Rollout log

| Date | Change |
|---|---|
| 2026-10-12 | Live on **Admin Test** only, steward `sonny.nguyen.01` (Moderator). 4 rooms OK. Verified: re-sync is a no-op, a demotion is restored, a leave is respected, an orphaned room is reported as Needs Admin without API calls. |
| 2026-10-12 | **Project \| Team** managed instead, with the real steward list (10: 2 Admin, 8 Moderator). 22 rooms OK; 217 steward rows joined, 3 already left and respected. Admin Test unticked → Not Managed. Operation still pending `@administrator` rejoining HW3 \| Core and SCR1 \| Core. |

## Not built yet (phase 2)

- Employee list → filter by department → **Add to Matrix rooms…** (creates
  Manual rows).
- Matrix Room Member list → **Remove from room** (kick + delete) and **Stop
  managing** (delete only) bulk actions.
- Recording members who joined on their own, so the list shows everyone and
  batch removal works on anyone.
- Refreshing fetched Department / Designation when an employee moves.
