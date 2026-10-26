# Task Kanban board

Frappe 15.91's Kanban board, with a Task-specific layer on both ends:

| File | Role |
|---|---|
| `overrides/frappe/kanban_board/kanban_board.py` | Replaces the board's three server calls (`override_whitelisted_methods`) and sorts Task columns by priority |
| `public/js/kanban/kanban_customizations.js` | Card renderer (names instead of avatars, inline editing, collapse), drops without a redraw, board filters, scroll keeping |
| `public/js/kanban/kanban_optimizations.js` | Reloads an idle Task Kanban after 5 minutes |
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

## Opening a board

Frappe calls `update_order` every time a board opens, with every card on
screen. For Task boards the override:

- never moves a card. The screen was drawn from the database a moment before,
  so a card in another column means someone moved it in between; Frappe's
  version moved it back, undoing their change and sending its notices again;
- re-sorts the columns in one query, and saves the board only if an order changed.

Before 2026-10-26 this was one query per card, one per column, and a board save
on every open: 513 queries for "All". Now 3 when nothing changed, about 42 when
the board is saved. Both versions return the same column orders on every board.

Frappe then draws the board a second time with the order it got back.
`skipUnchangedOrder()` skips that when the order came back as it already was.

`applyBoardFilters()` clears and re-adds the board's filters on opening, which
reloads the board. It now leaves them alone when they are already the board's.

## Dropping a card

Frappe's drop freezes the screen, calls `update_order_for_single_card`, and when
it answers **redraws every column and every card** on the board. On a board of
100–460 cards that is the wait people saw.

`saveDroppedCard()` intercepts that call:

1. It lifts Frappe's freeze at once. The card stays where it was dropped,
   dimmed while it saves.
2. On success, `settleDroppedCard()` updates just that card: its status field,
   its place by priority in the new column (`reorderColumnByPriority`), and the
   card and column objects in Frappe's store (`cardObjects`, `columnObjects`),
   so a later redraw keeps it in the new column. Changing those objects in
   place does not set off the store's watchers.
3. On failure Frappe's own handler runs: it puts the board back as it was, with
   one full redraw, and the server's message is shown.

Only Task Kanban boards (`isKanbanView()`) are handled this way.

## The listener leak in Frappe 15.91

Each column Frappe draws registers a store watcher that redraws its cards, and
never releases it. Every full redraw creates a new set of columns, so after N
redraws a single refresh draws the board N+1 times, mostly into columns no
longer on screen. Frappe fixed it upstream in July 2026 (commits `330ad46beb`,
`43f0179c5a` on `version-15`).

Here the card renderer returns early when its column is no longer in the page,
which makes the leaked watchers cheap. With drops no longer redrawing the board,
few columns are replaced anyway.

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
