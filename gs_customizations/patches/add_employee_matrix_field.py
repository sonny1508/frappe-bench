"""
Patch: add custom_enable_matrix_notifications field to Employee.

Opt-in flag for Matrix/Element notifications. Defaults to 0, so
employees without a Matrix account won't receive notifications until
explicitly enabled.
"""

from gs_customizations.customize.customize_fields import custom_employee


def execute():
    custom_employee()
