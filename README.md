cron-notify
===========

`cron-notify` is a FreeDesktop.org-compatible notification service to periodically ask for acknowledgement before executing a cronjob. It is often used for backup software and was previously known as `borg-notify`, referring to its original purpose as a notification service for [Borg Backup](http://borgbackup.readthedocs.io/).

Install
-------

You can find the list of Python packages `cron-notify` depends on in the `requirements.txt`. However, please note that PyGObject explicitly disallows building itself using `distutils`. You aren't required to use PyPI in general, you will likely find the required Python packages in the package sources of your distribution. If you e.g. use Debian Jessie, you will have to install the `python3-croniter`, `python3-dbus`, `python3-gi`, `python3-notify2` and `python3-xdg` packages (or their Python 2 equivalents).

`cron-notify` works with both Python 2 and Python 3. It was tested with Python 2.7 and 3.4 under Debian Jessie, however, it *should* work with any other distribution. If not, please don't hesitate to open a new [Issue on GitHub](https://github.com/PhrozenByte/cron-notify/issues).

Usage
-----

```
$ cron-notify --help
usage: cron-notify [OPTION]... [CONFIG]...

cron-notify is a FreeDesktop.org-compatible notification service to
periodically ask for acknowledgement before executing a cronjob. It is often
used for backup software.

Arguments:
  CONFIG                File to read configuration from. You can either
                        specify a filename ('config.ini'), a absolute path
                        ('/path/to/config.ini'), or a relative path
                        ('./config.ini'). By specifying a filename, cron-
                        notify searches for a accordingly named file in the
                        configuration search path of 'cron-notify' as
                        specified by the XDG Base Directory specification
                        (e.g. '~/.config/cron-notify/'). Defaults to 'cron-
                        notify.ini'

Application options:
  --critical            Work on log level CRITICAL
  --error               Work on log level ERROR
  -q, --quiet, --warning
                        Work on log level WARNING
  --info                Work on log level INFO (default)
  -v, --verbose, --debug
                        Work on log level DEBUG

Help options:
  --help                Display this help message and exit
  --version             Output version information and exit

Please report bugs using GitHub at <https://github.com/PhrozenByte/cron-
notify>. Besides, you will find general help and information about cron-notify
there.
```

Config
------

`cron-notify` reads its config from `cron-notify.ini` in `~/.config/cron-notify/` by default. A config file for Borg Backup might look like the following:

```ini
[DEFAULT]
app = borg-notify
name_tpl = Borg Backup "{}"
name_tpl_empty = Borg Backup

notification_summary = Borg Backup
notification_message = It's time to backup your data! Your next {} is on schedule.
notification_icon = borg

success_summary = Borg Backup
success_message = Your recent {} was successful. Yay!
success_icon = borg

warning_summary = Borg Backup
warning_message = Your recent {} finished with warnings. 
    This might not be a problem, but you should check your logs.
warning_icon = borg

failure_summary = Borg Backup
failure_message = Your recent {} failed due to a misconfiguration. 
    Check your logs, your backup didn't run!
failure_icon = dialog-error

[lunch-backup]
command = borg-lunch-backup
name = Lunch Backup
cron = 30 12 * * *
sleep = 1800
```

In the above example, `cron-notify` shows a notification every day at 12:30 (`cron = 30 12 * * *`), asking the user to start or skip the "Lunch Backup" (`name = Lunch Backup`). If the system is currently not on main power, the notification is deferred until it is on main power. If the user dismisses/ignores this notification, `cron-notify` shows it half an hour (1800 seconds; `sleep = 1800`) later again. If the user decides to start the backup, `cron-notify` executes `borg-lunch-backup` (`command = borg-lunch-backup`). If the command returns the special exit status 75 (`EX_TEMPFAIL`), `cron-notify` treats it as if the user dismissed the notification. Any other exit status yields a appropiate status notification. As usual, exit status 0 indicates success, whereas any nonzero exit status indicates some sort of failure. The special exit status 254 indicates that the action was taken, but something non-essential went wrong ("finished with warnings").

License & Copyright
-------------------

Copyright (C) 2016-2017  Daniel Rudolf <http://www.daniel-rudolf.de/>

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3 of the License only.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the [GNU General Public License](LICENSE) for more details.
