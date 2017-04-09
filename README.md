borg-notify
===========

`borg-notify` is a FreeDesktop.org-compatible notification service for [Borg Backup](http://borgbackup.readthedocs.io/).

Install
-------

You can find the list of Python packages `borg-notify` depends on in the `requirements.txt`. However, please note that PyGObject explicitly disallows building itself using `distutils`. You aren't required to use PyPI in general, you will likely find the required Python packages in the package sources of your distribution. If you e.g. use Debian Jessie, you will have to install the `python3-croniter`, `python3-dbus`, `python3-gi`, `python3-notify2` and `python3-xdg` packages (or their Python 2 equivalents).

`borg-notify` works with both Python 2 and Python 3. It was tested with Python 2.7 and 3.4 under Debian Jessie, however, it *should* work with any other distribution. If not, please don't hesitate to open a new [Issue on GitHub](https://github.com/PhrozenByte/borg-notify/issues).

Usage
-----

```
$ borg-notify --help
usage: borg-notify [OPTION]... COMMAND...

Send a desktop notification every CRON_EXPRESSION to inform the user that a
backup is on schedule. If the user decides to start the backup, execute
COMMAND.

Application options:
  COMMAND               command to execute when creating a backup
  -f, --force           force a immediate backup and exit
  -r, --reset           reset the last execution time of this backup command
                        and exit
  -i NAME, --info NAME  optional name for this backup
  -c CRON_EXPRESSION, --cron CRON_EXPRESSION
                        crontab-like schedule definition (defaults to every
                        day at 8:00, i.e. "0 8 * * *")
  -s SECONDS, --sleep SECONDS
                        time to sleep when the user dismisses the notification
                        (in seconds, defaults to 1 hour, i.e. 3600)
  -v, --verbose         explain what is being done

Help options:
  --help                display this help and exit
  --version             output version information and exit
```

---

`borg-notify-conf` reads its configuration from `~/.config/borg-notify/borg-notify.ini`:

```ini
[lunch-backup]
command = ~/bin/borg-lunch-backup
name = Lunch Backup
cron = 30 12 * * *
sleep = 1800
```

License & Copyright
-------------------

Copyright (C) 2016-2017  Daniel Rudolf <http://www.daniel-rudolf.de/>

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3 of the License only.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the [GNU General Public License](LICENSE) for more details.
