import frappe
from frappe.desk.doctype.notification_log.notification_log import (
    NotificationLog,
    send_notification_email,
)
from frappe.desk.doctype.notification_settings.notification_settings import (
    is_email_notifications_enabled_for_type,
)
from frappe import _


class CustomNotificationLog(NotificationLog):
    def after_insert(self):
        # Keep realtime + unseen behavior
        frappe.publish_realtime(
            "notification", after_commit=True, user=self.for_user
        )
        from frappe.desk.doctype.notification_log.notification_log import (
            set_notifications_as_unseen,
        )
        set_notifications_as_unseen(self.for_user)

        if self.type == "Assignment":
            return

        # Default behavior for everything else
        if is_email_notifications_enabled_for_type(self.for_user, self.type):
            try:
                send_notification_email(self)
            except frappe.OutgoingEmailError:
                self.log_error(_("Failed to send notification email"))