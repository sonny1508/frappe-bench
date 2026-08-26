# gs_customizations — Documentation

Customisations for the Glenda Studio ERPNext site (`glenda-studio-portal.me`).
Mostly overrides of stock ERPNext/HRMS behaviour, plus a Matrix chat integration.

Start here if you are new to the app, then read the area you are working in.

## Directory map

| Path | What lives there |
|---|---|
| `overrides/<app>/<doctype>/` | Controller overrides, mirroring the upstream app's own layout |
| `customize/customize_fields.py` | Every Custom Field and Property Setter, declared in code |
| `gs_customizations/report/` | Script reports (GS Task Sheet, GS Timesheet, GS PTO Sheet) |
| `maintenance/` | One-off `bench execute` data scripts — see [maintenance-scripts.md](maintenance-scripts.md) |
| `patches/` + `patches.txt` | Migration patches that run on `bench migrate` |
| `matrix/`, `matrix_integration/` | Element/Matrix notifications and Food Poll doctypes |
| `validate/permissions.py` | Shared permission helpers (`is_manager`, `MANAGER_ROLES`) |
| `utils/` | `network_access.py`, `hrms.py`, `timesheet_checkin.py` |
| `public/` | Desk CSS/JS assets (kanban customisations, login slideshow) |

## Conventions

**Overrides mirror upstream.** `overrides/<upstream_app>/<snake_case_doctype>/<snake_case_doctype>.py`,
class named `Custom<DocType>`. There are **no `__init__.py` files** under `overrides/` —
the tree relies on PEP-420 implicit namespace packages.

**Hooks live in `hooks.py`, handlers live with their feature.** A handler is placed
next to the code it belongs to, not next to the doctype that fires it. `ToDo`
`after_insert` handlers, for example, live in `overrides/erpnext/task/task.py` and
`matrix/notifications.py`, because in both cases the logic is about Tasks and about
notifications respectively — not about ToDos.

**Custom fields are declared in code, not fixtures.** Fixtures are deliberately off.
Add fields to `customize/customize_fields.py`; `install.py` runs on both
`after_install` and `after_migrate`, so they reapply on every `bench migrate`.

> Note: this does **not** cover Property Setters made through the Customize Form UI.
> Several exist in the database that are not in `customize_fields.py` — notably the
> `permlevel` settings on Task. See [task-overrides.md](erpnext/task/task-overrides.md).

**Logging and errors.**

```python
frappe.logger("<channel>").info(...)          # integration diagnostics
frappe.log_error(frappe.get_traceback(), "gs_customizations: <what failed>")
frappe.throw(msg, title=...)                  # user-facing
```

Anything running inside another document's transaction (a hook on a ToDo insert, a
notification) wraps its body in `try/except` so it can never fail the parent action.

## Two sources of truth for "who is a manager"

This trips people up. There are **two independent definitions**:

| Where | What it reads |
|---|---|
| `validate/permissions.py` → `MANAGER_ROLES` | Hardcoded `{"GS - Projects Manager", "System Manager"}` |
| `frappe.conf.get("manager_roles")` | From `site_config.json` |

`is_manager()` uses the first; `task.py`, `network_access.py` and `permissions.block_assign`
use the second. They are not guaranteed to agree. `block_assign` and `is_restricted_network`
also have no `or []` guard, so they raise `TypeError` if `manager_roles` is absent from
site_config.

## Documented areas

- [Task overrides](erpnext/task/task-overrides.md) — `CustomTask`, assignment-driven fields, permissions
- [GS Task Sheet report](erpnext/task/gs-task-sheet.md) — filters, columns, export behaviour
- [Leave Ledger Entry](hrms/leave-ledger-entry.md) — the override and the upstream data-loss bug it fixes
- [Maintenance scripts](maintenance-scripts.md) — `bench execute` one-offs and how to write one
- [Timesheet overrides](erpnext/timesheet/timesheet_overrides.md), [Timesheet check-in](erpnext/timesheet/timesheet_checkin.md)
- [Matrix integration](matrix_integration/overview.md) — 8 documents, start with the overview

## Not documented yet

Worth writing when someone next works in these areas:

- `overrides/hrms/leave_application/` (997 lines — the largest single override)
- `overrides/hrms/leave_allocation/`, `leave_policy_assignment/`
- `overrides/hrms/report/monthly_attendance_sheet/`, `leave_ledger/`, `employee_leave_balance/`
- `overrides/hrms/attendance/`, `employee_checkin/`, `shift_type/`
- `overrides/frappe/kanban_board/` and `public/js/kanban/`
- `utils/network_access.py` (route blocking / restricted network)
