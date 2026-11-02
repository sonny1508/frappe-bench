# Task Kanban board

Frappe 15.91's Kanban board, with a Task-specific layer on both ends:

| File | Role |
|---|---|
| `overrides/frappe/kanban_board/kanban_board.py` | Replaces the board's three server calls (`override_whitelisted_methods`) and sorts Task columns by priority |
| `public/js/kanban/kanban_customizations.js` | Card renderer (names instead of avatars, inline editing, collapse), refreshes and drops without rebuilding the board, board filters, scroll keeping |
| `public/js/kanban/kanban_optimizations.js` | Reloads an idle Task Kanban after 5 minutes, and an old page as soon as it wakes up |
| `public/js/kanban/kanban_util.js` | Click-and-drag horizontal scrolling |

The board itself is Frappe's `kanban_board.bundle.js`. Its Vuex store is private
to that file, so everything here works around it: by replacing the global
`frappe.views.KanbanBoardCard` / wrapping `frappe.views.KanbanBoardColumn`, and by
intercepting `frappe.call` for the board's server methods.

## Column order is by priority

For Task boards the order people drag cards into is never kept. Every server
call re-sorts the affected columns by `TASK_PRIORITY_ORDER` (Overdue first), and
within one priority by most recently modified. `get_task_column_orders()` does
this for any number of columns in one query.

Only the board's **first** filter is applied when sorting (usually the project),
so a Closed column still gets an order on boards that hide Closed tasks.

The order is computed without the user's permissions, and written straight to
the `Kanban Board Column` rows (`save_task_column_orders()`), never with
`board.save()`:

- Sorting what each person may see gave a different order per person, so nearly
  every open by someone else rewrote the board, which then redrew.
- A drop loads the board, saves the Task, then saves the board. Anyone saving the
  board in between failed the whole drop with `TimestampMismatchError` (HTTP 417),
  and the card went back. With about 11,000 opens on a workday, that was a live
  race.
- Kanban Board's `on_change` clears Task's doctype cache and everyone's user
  settings. Harmless for a real board change, not for one on every open.

## Opening a board

Frappe calls `update_order` every time a board opens, with every card on
screen. For Task boards the override:

- never moves a card. The screen was drawn from the database a moment before,
  so a card in another column means someone moved it in between; Frappe's
  version moved it back, undoing their change and sending its notices again;
- re-sorts the columns in one query, and writes only the columns whose order changed.

Before 2026-10-26 this was one query per card, one per column, and a board save
on every open: 513 queries for "All".

Frappe then draws the board a second time with the order it got back, and a third
if the request fails. `saveOpeningOrder()` replaces both with
`sortColumnsByOrder()`, which only sorts the cards already on screen.

`applyBoardFilters()` clears and re-adds the board's filters on opening, which
reloads the board. It now leaves them alone when they are already the board's.

## Refreshes

Frappe's `ListView` calls `refresh()` **every 5 minutes**
(`patch_refresh_and_load_lib`), whatever the person is doing. On a Kanban view,
stock Frappe then:

1. empties the page and rebuilds the board from scratch (`render()` →
   `$result.empty()` → `init()`), which also sends `update_order`;
2. adds store watchers it never releases. Every old one redraws the whole board
   on the next refresh, so each refresh draws the board once more than the last.
   Running Frappe's code on a 460-card board, the 1st refresh drew 920 cards and
   the 12th drew 5,980; 12 hours without a reload would mean about 66,000 cards
   every 5 minutes, enough to lock up a tab. The idle reload was only hiding this,
   and only on tabs that were idle.

A refresh during a drag is worse. Sortable keeps hold of the old card and its old
column, so the card in hand lands in the new board next to its redrawn self
(the duplicate), or is saved against a column no longer on the page (the card
that "doesn't move"). Stock `get_fields()` also made this more likely: it adds
the board's field again on each call, so no two requests looked alike and the
list's 3-second throttle never applied, which gave a second rebuild about 2
seconds after every open. That is why dragging right after a reload was the
easiest way to hit it.

`patchBoardRender()` changes this for Task boards:

- `get_fields()` no longer grows, so the throttle works again.
- A refresh while a card is held (`Sortable.dragged`) waits for the drop.
- A refresh compares the data with what is on screen and does nothing if it is
  the same.
- If the data did change, only the cards are redrawn (`kanban.update()`), keeping
  the columns, their Sortables, the watchers and each column's scroll position.
- Frappe's own `render()` still does the first draw, and coming back from another
  board in the same tab, as its store holds one board at a time.

Board data can be older than a drop: fetched just before the save, answered just
after. `keepRecentMoves()` overlays cards moved in the last 30 seconds (or still
saving) on the data before drawing, so a redraw can't move them back.

## Dropping a card

Frappe's drop freezes the screen, calls `update_order_for_single_card`, and when
it answers **redraws every column and every card** on the board. On a board of
100–460 cards that is the wait people saw.

`saveDroppedCard()` intercepts that call:

1. It lifts Frappe's freeze at once. The card stays where it was dropped, dimmed
   and not draggable while it saves (`.kanban-card-saving`), so two saves of one
   card can't race. A drop back into the card's own column saves nothing.
2. On success, `settleDroppedCard()` updates just that card: its status field,
   its place by priority in the new column (`reorderColumnByPriority`), and the
   card and column objects in Frappe's store (`cardObjects`, `columnObjects`),
   so a later redraw keeps it in the new column. Changing those objects in
   place does not set off the store's watchers.
3. On failure `restoreDroppedCard()` returns the card to the column it came from,
   and the server's message is shown. Frappe's handler, which would redraw the
   whole board, never runs: the action gets a resolved promise, not the request.

Anything that re-inserts cards waits until the card in hand has been dropped
(`afterDrag`), and looks columns up within this board only (`findColumn()`):
Frappe keeps other boards' pages in the DOM, and jQuery copies a card appended to
more than one column.

Only Task Kanban boards (`isKanbanView()`) are handled this way.

## The idle reload

`kanban_optimizations.js` reloads a Task Kanban after 5 minutes without activity,
checked once a minute.

Timers stop while the computer sleeps or the browser freezes a background tab, so
nothing checks until the page wakes up. If the mouse moved first, that used to
count as activity and cancel the reload, leaving hours-old data on screen. Now
any activity first checks the time since the last activity, and an old page
reloads there and then. Tab switches and the network coming back check too. It
waits for `navigator.onLine`, as reloading without a connection leaves the
browser's error page.

An idle tab keeps its login alive, as each reload counts as activity to the
12-hour `session_expiry` in System Settings. A tab that was asleep past that goes
to the login page when it reloads, and returns to the board afterwards.

## The listener leak in Frappe 15.91

Each column Frappe draws registers a store watcher that redraws its cards, and
never releases it. Frappe fixed it upstream in July 2026 (commits `330ad46beb`,
`43f0179c5a` on `version-15`).

Here the board is no longer rebuilt on refresh, so the watchers stop multiplying
(see [Refreshes](#refreshes)). The card renderer also returns early when its
column is no longer in the page, for the few rebuilds that remain.

## Landmines

- **Hooks are cached, assets are cached harder.** The JS files are served from
  `/assets` with a one-year cache, keyed by the `?v=` in `hooks.py`
  `app_include_js`. Bump it when a file changes, then `bench clear-cache`, or
  browsers keep the old file.
- **`frappe.call` is patched once**, in `patchFrappeCallForScrollPreservation()`.
  Add handling for further board methods there, not with a second patch.
- **Upgrading Frappe** to a release with the upstream leak fix leaves the
  `isConnected` check harmless. Frappe 16 replaces this board entirely (optimistic
  drops, virtual scrolling, `kanban_v2`); most of this file would need redoing.
