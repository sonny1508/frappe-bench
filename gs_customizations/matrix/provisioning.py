"""
Room provisioning logic for Matrix DM rooms.

Handles:
- Provisioning rows that are manually added to the DM Rooms table (username
  filled, room_id empty) — via the "Provision DM Rooms" button
- Checking for existing DM rooms in Matrix before creating new ones
- Automatic provisioning when an Employee record is updated (hook)
"""

import frappe

from gs_customizations.matrix.bot import (
	create_dm_room,
	force_join_room,
	get_existing_dm_room,
	get_matrix_user_id,
	get_settings,
)


def on_employee_update(doc, method):
	"""Employee on_update hook. Provisions a DM room if the employee has a
	username and auto-provisioning is enabled.

	Enqueues the actual API work as a background job so we don't block the save.
	"""
	try:
		settings = frappe.get_single("Matrix Settings")
	except Exception:
		return

	if not settings.enabled or not settings.auto_provision_rooms:
		return

	# Get the username from the linked User
	if not doc.user_id:
		return

	username = frappe.db.get_value("User", doc.user_id, "username")
	if not username:
		return

	# Check if a DM room row already exists for this username
	existing = [r for r in settings.dm_rooms if r.username == username]
	if existing:
		return

	frappe.enqueue(
		"gs_customizations.matrix.provisioning._provision_and_add_row",
		username=username,
		queue="short",
		is_async=True,
	)


def _provision_and_add_row(username):
	"""Provision a DM room for a username and add a new row to the table.

	Used by the Employee on_update hook when the username isn't in the table yet.
	"""
	settings = frappe.get_single("Matrix Settings")
	result = _provision_single_room(username, settings)

	settings.append("dm_rooms", {
		"username": result["username"],
		"room_id": result.get("room_id", ""),
		"status": result["status"],
		"error_log": result.get("error", ""),
	})
	settings.save(ignore_permissions=True)
	frappe.db.commit()

	return result


def _provision_single_room(username, settings):
	"""Core provisioning logic for a single username.

	1. Checks if a DM room already exists in Matrix between the bot and user
	2. If yes, reuses that room_id
	3. If no, creates a new room and optionally force-joins the user

	Returns a dict: {username, room_id, status, error?}
	"""
	matrix_user_id = get_matrix_user_id(username, settings)
	frappe.logger("matrix").info(f"Provisioning room for {username} -> {matrix_user_id}")

	try:
		# Check for an existing DM room first
		existing_room_id = get_existing_dm_room(matrix_user_id)

		if existing_room_id:
			frappe.logger("matrix").info(
				f"Found existing DM room {existing_room_id} for {username}"
			)
			return {
				"username": username,
				"room_id": existing_room_id,
				"status": "Active",
			}

		# No existing room — create a new one
		room_id = create_dm_room(matrix_user_id)

		# Force-join if bot has admin privileges
		if settings.bot_is_admin:
			try:
				force_join_room(room_id, matrix_user_id)
			except Exception as e:
				frappe.logger("matrix").warning(
					f"Force-join failed for {matrix_user_id} in {room_id}: {e}"
				)

		frappe.logger("matrix").info(
			f"Provisioned DM room {room_id} for {username}"
		)
		return {
			"username": username,
			"room_id": room_id,
			"status": "Active",
		}

	except Exception as e:
		frappe.logger("matrix").error(
			f"Failed to provision DM room for {username}: {e}"
		)
		return {
			"username": username,
			"room_id": None,
			"status": "Failed",
			"error": str(e)[:500],
		}


def provision_all_dm_rooms():
	"""Provision DM rooms for rows in the table that have a username but no room_id.

	Called from the 'Provision DM Rooms' button on Matrix Settings.
	This only processes rows you've already added manually — it does NOT
	auto-discover employees.

	For each row: checks Matrix for an existing DM room first, creates one
	only if none exists, then updates the row with the room_id and status.

	Returns a summary dict: {provisioned, skipped, failed}.
	"""
	settings = frappe.get_single("Matrix Settings")
	if not settings.enabled:
		frappe.throw("Matrix integration is not enabled.")

	provisioned = 0
	skipped = 0
	failed = 0

	for row in settings.dm_rooms:
		# Skip rows that already have a room_id and are Active
		if row.room_id and row.status == "Active":
			skipped += 1
			continue

		if not row.username:
			skipped += 1
			continue

		result = _provision_single_room(row.username, settings)

		row.room_id = result.get("room_id") or ""
		row.status = result["status"]
		row.error_log = result.get("error", "")

		if result["status"] == "Active":
			provisioned += 1
		else:
			failed += 1

	settings.save(ignore_permissions=True)
	frappe.db.commit()

	summary = {"provisioned": provisioned, "skipped": skipped, "failed": failed}
	frappe.logger("matrix").info(f"Bulk provisioning complete: {summary}")
	return summary
