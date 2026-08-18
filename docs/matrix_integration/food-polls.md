# Food Polls — Extracting Daily Vote Data

Records the daily food vote held in the Element room so the producer has a
documented order history on the web.

- `gs_customizations/matrix/polls.py` — reads and tallies Matrix poll events
- `matrix_integration/doctype/food_poll/` — the record (parent)
- `matrix_integration/doctype/food_poll_option/` — one row per menu option
- `matrix_integration/doctype/food_poll_vote/` — one row per person

Deliberately separate from **Matrix Settings**, which holds the bot token and
must stay System-Manager-only. The producer needs write access to Food Poll and
nothing else.

## Producer workflow

1. In Element, hover the poll message → **Options** → **Share** → copy link.
2. In Frappe: **Food Poll** list → **Import from Matrix** → paste → Import.
3. Check the result, fix the date/meal if needed, add any late votes by hand.

The poll's permalink is all that's needed:

```
https://matrix.to/#/!KdCLFxTrmjZNfcvrnT:glenda-studio-chat.com/$wb2rskNlsf23ibAZairKENNS7Z6Ki1OYJMKe84pNe7s?via=glenda-studio-chat.com
```

`parse_poll_reference()` also accepts an Element permalink, a bare
`!room:server/$event` pair, or the raw event JSON from "View source" — from
which it extracts only the two IDs and then fetches from the homeserver anyway.

**Pasting the event JSON alone cannot work.** The poll start event contains the
question and the answer definitions, but the votes live in separate events; the
JSON lists only their event IDs under `m.relations`. The votes must be read from
the homeserver regardless.

## How the data is read

Three calls, all as `@gs.bot` (already a member of the food room):

| Call | Purpose |
|---|---|
| `GET /_matrix/client/v3/rooms/{room}/event/{event}` | The poll: question, options, `max_selections` |
| `GET /_matrix/client/v1/rooms/{room}/relations/{event}/m.reference` | Every vote + the poll-end event (paginated) |
| `GET /_matrix/client/v3/rooms/{room}/joined_members` | Display names, in one call rather than per-user profile lookups |

The bot must be **joined to the room** — this is a client-API read, not an admin
one. Synapse admin rights do not grant room history access on their own.

## Tally rules (MSC3381)

1. Only responses sent after the poll start, and at or before the poll end event
   (if the poll was ended), count.
2. Per sender, only the most recent response counts. Ties break on event ID so
   results are deterministic.
3. Answer IDs not defined by the poll are discarded; the rest is truncated to
   `max_selections`.
4. A response left with no valid answers is **spoiled** — that sender has no vote.

### The Element fork's "Undo vote" needs no special handling

`element-web/customizations/OPEN_POLL.md` adds an undo button, but implements it
as a spec-compliant spoiled response (empty `answers`). Rule 4 already covers it.

A sender whose latest response is spoiled but who *had* voted earlier is stored
with status **Withdrawn** rather than dropped, showing which option they had
picked. Withdrawn rows are never counted in the totals — they are kept because
those are usually the people who DM the producer afterwards.

Verified against a real poll (`$wb2rskNlsf23ibAZairKENNS7Z6Ki1OYJMKe84pNe7s`):
14 related events, 10 voters, 3 undos → 7 votes, matching Element's own
"Final result based on 7 votes".

## Editing after import

The document stays editable forever — it is not submittable. Every row in both
child tables is tagged:

- **Matrix** — imported. Replaced wholesale on every re-sync.
- **Manual** — added by hand. Never touched by a re-sync.

So a late vote that arrived by DM is added as a Manual row and survives any
number of re-syncs. Counts, the total, and the summary are recomputed on save.

Hand-typed votes have no MSC3381 answer ID, so `link_votes_to_options()` adopts
the ID of the option whose name matches (case-insensitively) before counting.
Without this, "Phở tái nạm" typed by hand would be counted as a second, separate
menu item. `dedupe_options()` then collapses option rows naming the same item.

An option named in a Manual vote that isn't on the poll (an off-menu request)
gets its own option row automatically, tagged Manual.

## Identity

`resolve_employee()` reverses `bot.get_matrix_user_id()`:

```
@thong.nguyen.01:glenda-studio-chat.com  →  User.username  →  Employee.user_id
```

Active Employees are preferred, falling back to any status. A voter with no
matching record is kept with their raw Matrix ID and display name rather than
blocking the import — the sync result reports how many were unresolved.

## Fields worth knowing

| Field | Notes |
|---|---|
| `poll_event_id` | Identifies the poll. Re-importing the same link updates the existing document rather than duplicating it. Enforced in `check_duplicate_poll()`. |
| `poll_date` / `meal` | Set once on first import from the poll's timestamp (before 14:00 → Lunch, else Dinner), then never overwritten by a re-sync. |
| `summary` | Regenerated on save: `3 x Phở tái nạm` etc., most-ordered first — copy-paste straight to the restaurant. |
| `total_votes` | Counts `Voted` rows only. |

## Gotchas

- **Timestamps.** `origin_server_ts` is milliseconds UTC; `ts_to_system_datetime()`
  converts to site timezone. Getting this wrong shifts polls onto the wrong day.
- **Both event-type namespaces.** Events may use the unstable
  `org.matrix.msc3381.poll.*` prefix or the stable `m.poll.*`. Every type check
  accepts both — Element currently sends unstable.
- **Poll end sender.** Per spec only the poll creator may end a poll. The
  creator's earliest end event wins; a non-creator end event is used only as a
  fallback so a room-admin close still registers.
- **`poll_event_id` is not a unique DB index.** Manually created polls have no
  event ID, and multiple empty strings would collide. Uniqueness is enforced in
  `validate()` instead, which also gives a linked error message.
