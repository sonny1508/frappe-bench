"""The "Filter Based On" period selection shared by the GS reports."""

from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_last_day, getdate

# Glenda Studio Interactive's month runs from the 26th of the previous month to
# the 25th of the month it is named after: March 2026 is 26/02/2026 - 25/03/2026.
GSI_MONTH = "Glenda Studio Interactive"
GSI_MONTH_START_DAY = 26


def set_period_dates(filters):
	"""Resolve the Filter Based On selection into filters.start_date / end_date.

	Every option ends up as the same inclusive date pair, so the reports filter
	on start_date / end_date alone and never branch on which option was picked.
	Any start/end dates the client sent for a month option are stale values from
	the hidden Date Range inputs, and are overwritten.
	"""
	based_on = filters.get("filter_based_on")

	if based_on == "Date Range":
		if not (filters.get("start_date") and filters.get("end_date")):
			frappe.throw(_("Please set the date range."))

		start, end = getdate(filters.start_date), getdate(filters.end_date)
		if start > end:
			frappe.throw(_("Start date cannot be greater than end date."))

	elif based_on in ("Month", GSI_MONTH):
		# Month/Year always have a sensible value, so fall back to today's rather
		# than throwing on an empty one.
		today = getdate()
		month_start = date(
			cint(filters.get("year")) or today.year, cint(filters.get("month")) or today.month, 1
		)

		if based_on == "Month":
			start, end = month_start, get_last_day(month_start)
		else:
			start = (month_start - timedelta(days=1)).replace(day=GSI_MONTH_START_DAY)
			end = month_start.replace(day=GSI_MONTH_START_DAY - 1)

			# A period that is still running stops at today.
			if start <= today < end:
				end = today

	else:
		frappe.throw(_("Please select Filter Based On"))

	filters.start_date, filters.end_date = start, end
