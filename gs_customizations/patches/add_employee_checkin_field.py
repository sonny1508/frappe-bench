"""
Patch: add custom_enable_timesheet_checkin field to Employee.

This applies the opt-in flag used by the Daily Timesheet Check-in
enforcement feature. The field defaults to 0, so existing employees
are unaffected until the flag is explicitly set.
"""

from gs_customizations.customize.customize_fields import custom_employee


def execute():
    custom_employee()
