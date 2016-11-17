from backup_notify import BackupNotify

class BorgNotify(BackupNotify):
    _app = "borg-notify"

    _backupName = ( "Borg Backup", 'Borg Backup "{}"' )
    _notificationData = {
        "summary": "Borg Backup",
        "message": "It's time to backup your data! Your next {} is on schedule.",
        "icon": "borg"
    }
    _statusNotificationData = {
        BackupNotify._STATUS_SUCCESS: {
            "summary": "Borg Backup",
            "message": "Your recent {} was successful. Yay!",
            "icon": "borg"
        },
        BackupNotify._STATUS_WARNING: {
            "summary": "Borg Backup",
            "message": "Your recent {} finished with warnings. " +
                "This might not be a problem, but you should check your logs.",
            "icon": "borg"
        },
        BackupNotify._STATUS_ERROR: {
            "summary": "Borg Backup",
            "message": "Your recent {} failed due to a misconfiguration. " +
                "Check your logs, your backup didn't run!",
            "icon": "dialog-error"
        }
    }
