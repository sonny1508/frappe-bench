app_name = "gs_customizations"
app_title = "GS Customizations"
app_publisher = "Sonny Nguyen"
app_description = "Customized for Glenda Studio"
app_email = "sonnynguyen.0001@gmail.com"
app_license = "mit"

# fixtures = [
#     {"dt": "Custom Field"},
#     {"dt": "Property Setter"}
# ]

boot_session = "gs_customizations.boot.boot_session"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "gs_customizations",
# 		"logo": "/assets/gs_customizations/logo.png",
# 		"title": "GS Customizations",
# 		"route": "/gs_customizations",
# 		"has_permission": "gs_customizations.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/gs_customizations/css/gs_customizations.css"
# app_include_js = "/assets/gs_customizations/js/gs_customizations.js"

# include js, css files in header of web template
# web_include_css = "/assets/gs_customizations/css/gs_customizations.css"
# web_include_js = "/assets/gs_customizations/js/gs_customizations.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "gs_customizations/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

web_include_css = [
    "/assets/gs_customizations/css/login_slideshow.css?v=2"
]

web_include_js = [
    "/assets/gs_customizations/js/login_slideshow.js"
]

app_include_css = [
    "/assets/gs_customizations/css/kanban.css?v=23",
    "/assets/gs_customizations/css/kanban_inline_edit.css?v=13",
    # "/assets/gs_customizations/css/kanban_collapsible.css",
]

app_include_js = [
    # "/assets/gs_customizations/js/kanban.js",
    # "/assets/gs_customizations/js/kanban_inline_edit.js",
    # "/assets/gs_customizations/js/kanban_collapsible.js",
    # "/assets/gs_customizations/js/kanban_filters.js",

    "/assets/gs_customizations/js/kanban_customizations.js?v=34",
    "/assets/gs_customizations/js/kanban_optimizations.js?v=14",
    "/assets/gs_customizations/js/list_view_customizations.js?v=02",

    "/assets/gs_customizations/js/erpnext/task/task.js?v=02",
    "/assets/gs_customizations/js/hrms/monthly_attendance_sheet/monthly_attendance_sheet.js?v=02",

    "/assets/gs_customizations/js/timesheet_checkin_enforcer.js?v=04",

    # "/assets/gs_customizations/js/global_overrides.js",
    "/assets/gs_customizations/js/general/sidebar.js?v=3",
]

doctype_js = {
    "Leave Application": "overrides/hrms/leave_application/leave_application.js",
    "Leave Allocation": "overrides/hrms/leave_allocation/leave_allocation.js",

    "Task": "overrides/erpnext/task/task.js",
    "Timesheet": "overrides/erpnext/timesheet/timesheet.js",
    # "Timesheet Detail": "overrides/erpnext/timesheet_detail/timesheet_detail.js",
    # Current not working
    # "Workspace": "overrides/frappe/workspace/workspace.js"
}

doctype_list_js = {
    "Attendance": "overrides/hrms/attendance/attendance_list.js",
    "Task": "overrides/erpnext/task/task_list.js"
}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "gs_customizations/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "gs_customizations.utils.jinja_methods",
# 	"filters": "gs_customizations.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "gs_customizations.install.before_install"
# after_install = "gs_customizations.install.after_install"

after_install = "gs_customizations.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "gs_customizations.uninstall.before_uninstall"
# after_uninstall = "gs_customizations.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "gs_customizations.utils.before_app_install"
# after_app_install = "gs_customizations.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "gs_customizations.utils.before_app_uninstall"
# after_app_uninstall = "gs_customizations.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "gs_customizations.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

permission_query_conditions = {
    "Task": "gs_customizations.validate.permissions.project_query_conditions",
    "Task": "gs_customizations.overrides.erpnext.task.task_permissions.task_query_conditions",
}

# has_permission = {
#     "Task": "gs_customizations.validate.permissions.has_project_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

override_doctype_class = {
    "Attendance": "gs_customizations.overrides.hrms.attendance.attendance.CustomAttendance",
    "Shift Type": "gs_customizations.overrides.hrms.shift_type.shift_type.CustomShiftType",
    "Leave Application": "gs_customizations.overrides.hrms.leave_application.leave_application.CustomLeaveApplication",
    "Leave Allocation": "gs_customizations.overrides.hrms.leave_allocation.leave_allocation.CustomLeaveAllocation",
    "Leave Ledger Entry": "gs_customizations.overrides.hrms.leave_ledger_entry.leave_ledger_entry.CustomLeaveLedgerEntry",
    "Leave Policy Assignment": "gs_customizations.overrides.hrms.leave_policy_assignment.leave_policy_assignment.CustomLeavePolicyAssignment",

    "Task": "gs_customizations.overrides.erpnext.task.task.CustomTask",
    "Notification Log": "gs_customizations.overrides.frappe.notification_log.notification_log.CustomNotificationLog",
}

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    "ToDo": {
        "before_insert": "gs_customizations.validate.permissions.block_assign",
        "after_insert": [
            "gs_customizations.synology.synology.notify_todo_insert",
            "gs_customizations.matrix.notifications.notify_todo_insert"
        ]
    },
    "Company": {
        "validate": "gs_customizations.overrides.erpnext.company.company.validate"
    },
    "Task": {
        "before_load": "gs_customizations.utils.network_access.check_doctype_access",
        "before_insert": "gs_customizations.utils.network_access.check_doctype_access",
        "validate": "gs_customizations.overrides.erpnext.task.task.custom_validate",
        "on_change": "gs_customizations.overrides.erpnext.task.task.on_change",
        "on_update": [
            "gs_customizations.synology.synology.notify_task_update",
            "gs_customizations.matrix.notifications.notify_task_update"
        ],
    },
    "Employee": {
        "on_update": "gs_customizations.matrix.provisioning.on_employee_update"
    },
    "Timesheet": {
        "validate": [
            "gs_customizations.overrides.erpnext.timesheet.timesheet.update_completed_from_task",
            "gs_customizations.overrides.erpnext.timesheet.timesheet.clear_free_activity_fields"
        ]
    },
    # Currently not working for some reason
    "Kanban Board": {
        "before_insert": "gs_customizations.overrides.frappe.kanban_board.kanban_board.set_default_indicators",
        "validate": "gs_customizations.overrides.frappe.kanban_board.kanban_board.set_default_indicators", 
    },
    # Currently not working for some reason
    "Workspace": {
        "before_insert": "gs_customizations.overrides.frappe.workspace.workspace.validate_workspace_permission",
        "before_save": "gs_customizations.overrides.frappe.workspace.workspace.validate_workspace_permission",
        "on_trash": "gs_customizations.overrides.frappe.workspace.workspace.validate_workspace_delete",
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"gs_customizations.tasks.all"
# 	],
# 	"daily": [
# 		"gs_customizations.tasks.daily"
# 	],
# 	"hourly": [
# 		"gs_customizations.tasks.hourly"
# 	],
# 	"weekly": [
# 		"gs_customizations.tasks.weekly"
# 	],
# 	"monthly": [
# 		"gs_customizations.tasks.monthly"
# 	],
# }

scheduler_events = {
	"daily_long": [
		"gs_customizations.utils.hrms.allocate_earned_leaves",
	]
    # "cron": {
    #     "0 17 * * *": [
    #         "gs_customizations.synology.synology_schedule.schedule_daily_timesheet"
    #     ]
    # }
}

# Testing
# -------

# before_tests = "gs_customizations.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "gs_customizations.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "gs_customizations.task.get_dashboard_data"
# }

override_whitelisted_methods = {
    "frappe.desk.desktop.get_workspace_sidebar_items": "gs_customizations.overrides.frappe.desk.desktop.get_workspace_sidebar_items",

    "frappe.desk.doctype.kanban_board.kanban_board.update_order": "gs_customizations.overrides.frappe.kanban_board.kanban_board.update_order",
    "frappe.desk.doctype.kanban_board.kanban_board.update_order_for_single_card": "gs_customizations.overrides.frappe.kanban_board.kanban_board.update_order_for_single_card",
    "frappe.desk.doctype.kanban_board.kanban_board.add_card": "gs_customizations.overrides.frappe.kanban_board.kanban_board.add_card",

    # "erpnext.projects.doctype.task.task.make_timesheet": "gs_customizations.overrides.erpnext.task.task.make_timesheet",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["gs_customizations.utils.before_request"]
# after_request = ["gs_customizations.utils.after_request"]

before_request = ["gs_customizations.utils.network_access.block_restricted_routes"]

# Job Events
# ----------
# before_job = ["gs_customizations.utils.before_job"]
# after_job = ["gs_customizations.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"gs_customizations.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

