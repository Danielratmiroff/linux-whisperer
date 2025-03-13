import notify2


def show_notification(title, message, icon="dialog-information"):
    """Show a desktop notification."""
    notification = notify2.Notification(title, message, icon)
    notification.show()
