# Copyright (c) 2026, GS and contributors
# For license information, please see license.txt

"""
Food Poll — documents the daily food vote held in Element.

Data comes from a Matrix poll (see gs_customizations/matrix/polls.py), but the
document stays fully editable afterwards: people forget to vote and DM the
producer later, so rows added by hand are first-class. Rows are tagged Matrix or
Manual, and a re-sync only ever replaces the Matrix ones.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from gs_customizations.matrix import polls


class FoodPoll(Document):
	def validate(self):
		self.link_votes_to_options()
		self.dedupe_options()
		self.ensure_options_for_votes()
		self.recalculate_counts()
		self.build_summary()
		self.set_title()
		self.check_duplicate_poll()

	# -- derived fields ---------------------------------------------------

	def normalized_text(self, option_text):
		return (option_text or "").strip().casefold()

	def option_key(self, option_id, option_text):
		"""Votes match an option by ID when it came from Matrix, else by text."""
		if option_id:
			return ("id", option_id)
		return ("text", self.normalized_text(option_text))

	def link_votes_to_options(self):
		"""Give hand-entered votes the answer ID of the menu item they name.

		A vote typed in by hand has no MSC3381 answer ID. Without this it would
		not match the Matrix option row of the same name, and would be counted as
		a separate menu item.
		"""
		by_text = {}
		for option in self.options:
			key = self.normalized_text(option.option_text)
			if option.option_id and key and key not in by_text:
				by_text[key] = option.option_id

		for vote in self.votes:
			if vote.option_id:
				continue
			option_id = by_text.get(self.normalized_text(vote.option_text))
			if option_id:
				vote.option_id = option_id

	def dedupe_options(self):
		"""Collapse option rows that name the same item.

		An off-menu item added by hand and later offered in the poll proper would
		otherwise end up with one row from each source.
		"""
		seen_ids = set()
		seen_texts = set()
		kept = []
		for option in self.options:
			text_key = self.normalized_text(option.option_text)
			if option.option_id and option.option_id in seen_ids:
				continue
			if text_key and text_key in seen_texts:
				continue
			if option.option_id:
				seen_ids.add(option.option_id)
			if text_key:
				seen_texts.add(text_key)
			kept.append(option)

		if len(kept) != len(self.options):
			self.set("options", kept)
			for index, option in enumerate(self.options, start=1):
				option.idx = index

	def ensure_options_for_votes(self):
		"""Add an option row for any hand-entered item that isn't listed yet.

		Keeps the Options table a complete picture when the producer records an
		off-menu request that came in by DM.
		"""
		known_ids = {o.option_id for o in self.options if o.option_id}
		known_texts = {self.normalized_text(o.option_text) for o in self.options}

		for vote in self.votes:
			text = (vote.option_text or "").strip()
			if not text:
				continue
			if vote.option_id and vote.option_id in known_ids:
				continue
			if self.normalized_text(text) in known_texts:
				continue
			if vote.option_id:
				known_ids.add(vote.option_id)
			known_texts.add(self.normalized_text(text))
			self.append("options", {
				"option_text": text,
				"option_id": vote.option_id,
				"source": vote.source or "Manual",
				"vote_count": 0,
			})

	def recalculate_counts(self):
		"""Per-option vote counts and the document total.

		Withdrawn votes are recorded but never counted — they are the Element
		"Undo vote" cases, kept so the producer can see who changed their mind.
		"""
		counts = {}
		for vote in self.votes:
			if vote.status != "Voted":
				continue
			key = self.option_key(vote.option_id, vote.option_text)
			counts[key] = counts.get(key, 0) + 1

		for option in self.options:
			key = self.option_key(option.option_id, option.option_text)
			option.vote_count = counts.get(key, 0)

		self.total_votes = sum(counts.values())

	def build_summary(self):
		"""A copy-pasteable order list, most-ordered first."""
		ordered = sorted(
			[o for o in self.options if (o.vote_count or 0) > 0],
			key=lambda o: (-(o.vote_count or 0), (o.option_text or "").casefold()),
		)
		lines = [f"{o.vote_count} x {o.option_text}" for o in ordered]

		withdrawn = [v for v in self.votes if v.status == "Withdrawn"]
		if withdrawn:
			names = ", ".join(
				sorted(v.employee_name or v.display_name or v.matrix_user_id or "?" for v in withdrawn)
			)
			lines.append("")
			lines.append(f"Withdrawn ({len(withdrawn)}): {names}")

		self.summary = "\n".join(lines)

	def set_title(self):
		parts = [str(self.poll_date or ""), self.meal or ""]
		if self.question:
			parts.append(self.question)
		self.title = " - ".join(p for p in parts if p)

	def check_duplicate_poll(self):
		"""One document per Matrix poll. Blank event IDs (manual polls) are exempt."""
		if not self.poll_event_id:
			return
		existing = frappe.db.get_value(
			"Food Poll",
			{"poll_event_id": self.poll_event_id, "name": ("!=", self.name)},
			"name",
		)
		if existing:
			frappe.throw(
				f"This Matrix poll is already recorded in "
				f"<a href='/app/food-poll/{existing}'>{existing}</a>."
			)

	# -- Matrix sync ------------------------------------------------------

	@frappe.whitelist()
	def sync_from_matrix(self):
		"""Refresh Matrix-sourced rows from the homeserver, in place.

		Manual rows in both child tables are preserved untouched. Returns a
		summary dict for the UI.
		"""
		result = polls.read_poll(self.matrix_link or self.build_permalink())

		manual_options = [o for o in self.options if o.source == "Manual"]
		manual_votes = [v for v in self.votes if v.source == "Manual"]

		self.room_id = result["room_id"]
		self.poll_event_id = result["poll_event_id"]
		self.poll_sender = result["poll_sender"]
		self.poll_ended = result["poll_ended"]
		self.started_on = result["started_on"]
		self.ended_on = result["ended_on"]
		self.question = result["question"]

		# Only fill the business fields on first import — never clobber edits.
		if not self.poll_date and result["started_on"]:
			started = get_datetime(result["started_on"])
			self.poll_date = started.date()
			if not self.meal:
				self.meal = "Lunch" if started.hour < 14 else "Dinner"

		self.set("options", [])
		for option in result["options"]:
			self.append("options", {
				"option_id": option["option_id"],
				"option_text": option["option_text"],
				"vote_count": option["vote_count"],
				"source": "Matrix",
			})
		for option in manual_options:
			self.append("options", {
				"option_id": option.option_id,
				"option_text": option.option_text,
				"source": "Manual",
			})

		employee_cache = {}
		self.set("votes", [])
		for vote in result["votes"]:
			self.append("votes", {
				"employee": polls.resolve_employee(vote["matrix_user_id"], employee_cache),
				"matrix_user_id": vote["matrix_user_id"],
				"display_name": vote["display_name"],
				"option_id": vote["option_id"],
				"option_text": vote["option_text"],
				"status": vote["status"],
				"source": "Matrix",
				"voted_on": vote["voted_on"],
			})
		for vote in manual_votes:
			self.append("votes", {
				"employee": vote.employee,
				"matrix_user_id": vote.matrix_user_id,
				"display_name": vote.display_name,
				"option_id": vote.option_id,
				"option_text": vote.option_text,
				"status": vote.status,
				"source": "Manual",
				"voted_on": vote.voted_on,
				"note": vote.note,
			})

		self.synced_on = now_datetime()
		self.synced_by = frappe.session.user

		unresolved = len([v for v in self.votes if v.source == "Matrix" and not v.employee])
		return {
			"matrix_votes": len(result["votes"]),
			"manual_votes": len(manual_votes),
			"options": len(result["options"]),
			"unresolved": unresolved,
		}

	@frappe.whitelist()
	def fetch_from_matrix(self):
		"""Sync and save — the form button."""
		summary = self.sync_from_matrix()
		self.save()
		return summary

	def build_permalink(self):
		"""Reconstruct a permalink from stored IDs so re-sync works without the link."""
		if self.room_id and self.poll_event_id:
			return f"https://matrix.to/#/{self.room_id}/{self.poll_event_id}"
		frappe.throw("Paste the poll's Matrix link first, then use Fetch from Matrix.")
