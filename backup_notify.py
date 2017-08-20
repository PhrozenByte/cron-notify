import croniter, datetime, dbus, dbus.mainloop.glib, errno, hashlib, logging, os, re, subprocess, sys, threading
from gi.repository import GObject
from xdg import BaseDirectory

try:
    import pynotify
except ImportError:
    import notify2 as pynotify

__version__ = "1.0.0"

class BackupNotify(object):
    _STATUS_SUCCESS = 0
    _STATUS_WARNING = 1
    _STATUS_ERROR = 2

    _app = "backup-notify"

    _id = None
    _commands = None
    _blocking = True

    _name = None
    _cronExpression = "0 8 * * *"
    _sleepTime = 3600

    _cachePath = None

    _lastExecution = None
    _nextExecution = None

    _backupId = 0
    _lock = None

    _bus = None

    _timeoutId = None
    _timeoutTime = None

    _notification = None
    _notificationAction = None
    _notificationTimeoutId = None
    _notificationTimeoutTime = None

    _backupStreams = { "stdin": None, "stdout": None, "stderr": None }

    _logger = None

    _backupName = ( "backup", 'backup "{}"' )
    _notificationData = {
        "summary": "Backup",
        "message": "It's time to backup your data! Your next {} is on schedule.",
        "icon": "appointment-soon"
    }
    _statusNotificationData = {
        _STATUS_SUCCESS: {
            "summary": "Backup",
            "message": "Your recent {} was successful. Yay!",
            "icon": "dialog-information"
        },
        _STATUS_WARNING: {
            "summary": "Backup",
            "message": "Your recent {} finished with warnings. " +
                "This might not be a problem, but you should check your logs.",
            "icon": "dialog-warning"
        },
        _STATUS_ERROR: {
            "summary": "Backup",
            "message": "Your recent {} failed due to a misconfiguration. " +
                "Check your logs, your backup didn't run!",
            "icon": "dialog-error"
        }
    }

    def __init__(self, commands, blocking=True):
        if not commands or len(commands) == 0:
            raise ValueError("Invalid commands given")

        self._id = hashlib.sha1(str(commands).encode("utf-8")).hexdigest()
        self._commands = commands
        self._blocking = blocking

        logHandler = logging.StreamHandler(stream=sys.stderr)
        logHandler.setFormatter(logging.Formatter("%(asctime)s: %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

        self._logger = logging.getLogger("{}.{}.{}.{}".format(__name__, self._app, os.getpid(), self._id))
        self._logger.addHandler(logHandler)
        self._logger.setLevel(logging.WARNING)

        self._cachePath = BaseDirectory.save_cache_path(self._app)

        self._lock = threading.Lock()

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, id):
        id = str(id)
        if not re.match("^[\w.-]*$", id):
            raise ValueError("Invalid id given")
        self._id = id

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        self._name = str(name)

    @property
    def cronExpression(self):
        return self._cronExpression

    @cronExpression.setter
    def cronExpression(self, cronExpression):
        croniter.croniter(cronExpression, datetime.datetime.today()).get_next(datetime.datetime)
        self._cronExpression = cronExpression

    @property
    def sleepTime(self):
        return self._sleepTime

    @sleepTime.setter
    def sleepTime(self, sleepTime):
        self._sleepTime = int(sleepTime)

    @property
    def backupStreams(self):
        return self._backupStreams

    @backupStreams.setter
    def backupStreams(self, backupStreams):
        self._backupStreams = {
            "stdin": backupStreams.get("stdin"),
            "stdout": backupStreams.get("stdout"),
            "stderr": backupStreams.get("stderr")
        }

    @property
    def logger(self):
        return self._logger

    def main(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        self._bus = dbus.SystemBus()
        if not self._bus:
            self._logger.error("Failed to initialize DBus system bus")
            raise RuntimeError("Failed to initialize DBus system bus")

        self._initNotificationService()

        self._monitorResuming()
        self._timeout(0)

    def resetCache(self):
        try:
            self._logger.info("Resetting cache...")
            os.remove(self._cachePath + "/" + self._id)
        except OSError as error:
            if error.errno != errno.ENOENT:
                self._logger.error(
                    "While resetting the cache, a exception occurred: %s: %s",
                    type(error).__name__,
                    error
                )
                raise

    def backup(self, blocking=None):
        self._backupId += 1

        if blocking is None:
            blocking = self._blocking

        if not blocking:
            logPrefix = "[#{}] ".format(self._backupId)
            backupThread = threading.Thread(target=self._backup, kwargs={ "logPrefix": logPrefix })
            backupThread.start()
            return None
        else:
            return self._backup()

    def _backup(self, logPrefix=""):
        self._logger.debug("%sAcquiring lock...", logPrefix)
        self._lock.acquire()

        overallStatus = self._STATUS_SUCCESS
        for command in self._commands:
            self._logger.info("%sExecuting `%s`...", logPrefix, " ".join(command))

            try:
                subprocess.check_call(command, **self._backupStreams)
            except OSError as error:
                if overallStatus < self._STATUS_ERROR:
                    overallStatus = self._STATUS_ERROR

                if error.errno == errno.ENOENT:
                    self._logger.error(
                        "%sExecution of `%s` failed: No such file or directory",
                        logPrefix,
                        " ".join(command)
                    )
                elif error.errno == errno.EACCES:
                    self._logger.error(
                        "%sExecution of `%s` failed: Permission denied",
                        logPrefix,
                        " ".join(command)
                    )
                else:
                    self._logger.error(
                        "%sExecution of `%s` failed: %s: %s",
                        logPrefix,
                        " ".join(command),
                        type(error).__name__,
                        error
                    )
                    raise
            except subprocess.CalledProcessError as error:
                if overallStatus < self._STATUS_WARNING:
                    overallStatus = self._STATUS_WARNING

                self._logger.warning(
                    "%sExecution of `%s` failed with exit status %s",
                    logPrefix,
                    " ".join(command),
                    error.returncode
                )

        if overallStatus == self._STATUS_SUCCESS:
            self._logger.info("%sBackup finished successfully", logPrefix)
        elif overallStatus == self._STATUS_WARNING:
            self._logger.warning("%sBackup finished with warnings", logPrefix)
        elif overallStatus == self._STATUS_ERROR:
            self._logger.error("%sBackup failed", logPrefix)

        self._showStatusNotification(overallStatus)

        self._lock.release()
        return overallStatus != self._STATUS_ERROR

    def getLastExecution(self):
        lastExecution = None
        try:
            with open(self._cachePath + "/" + self._id, "rt") as cacheFile:
                lastExecutionTime = cacheFile.read(20)
                if lastExecutionTime:
                    lastExecution = datetime.datetime.fromtimestamp(int(lastExecutionTime))
        except IOError as error:
            if error.errno != errno.ENOENT:
                self._logger.error(
                    "While reading the last execution time, a exception occurred: %s: %s",
                    type(error).__name__,
                    error
                )
                raise

        return lastExecution

    def getNextExecution(self, lastExecution):
        nextExecutionCroniter = croniter.croniter(self._cronExpression, lastExecution)
        return nextExecutionCroniter.get_next(datetime.datetime)

    def updateLastExecution(self):
        with open(self._cachePath + "/" + self._id, "wt") as cacheFile:
            timestamp = int((datetime.datetime.utcnow() - datetime.datetime(1970, 1, 1)).total_seconds())
            cacheFile.write(str(timestamp))

    def _monitorResuming(self):
        try:
            self._logger.info("Registering system suspend/hibernate callback...")

            self._bus.add_signal_receiver(
                self._resumeCallback,
                dbus_interface="org.freedesktop.login1.Manager",
                signal_name="PrepareForSleep",
                bus_name="org.freedesktop.login1",
                path="/org/freedesktop/login1"
            )
        except dbus.exceptions.DBusException:
            self._logger.warning("Unable to register suspend/hibernate callback")
            pass

    def _resumeCallback(self, isPreparing):
        if not isPreparing:
            assert not ((self._timeoutId is not None) and (self._notificationTimeoutId is not None))

            self._logger.debug("System resumes from suspend/hibernate")

            if self._timeoutId is not None:
                GObject.source_remove(self._timeoutId)

                timeDifference = int((self._timeoutTime - datetime.datetime.today()).total_seconds())
                sleepTime = max(timeDifference, 120)

                self._timeoutId = None
                self._timeoutTime = None

                self._timeout(sleepTime)

            if self._notificationTimeoutId is not None:
                GObject.source_remove(self._notificationTimeoutId)

                timeDifference = int((self._notificationTimeoutTime - datetime.datetime.today()).total_seconds())
                sleepTime = max(timeDifference, 120)

                self._notificationTimeoutId = None
                self._notificationTimeoutTime = None

                self._notificationTimeout(sleepTime)

    def _wait(self):
        if self._waitUntilScheduled():
            if self._waitUntilMainPower():
                self._initNotification()

                self._notificationTimeout(self._sleepTime)

                self._logger.info("Sending notification...")
                if not self._showNotification(self._notification):
                    self._resetNotificationTimeout()
                    self._resetNotification()
                    self._timeout(0)

    def _waitUntilScheduled(self):
        self._lastExecution = self.getLastExecution()
        if self._lastExecution is not None:
            nextExecution = self.getNextExecution(self._lastExecution)
            timeDifference = int((nextExecution - datetime.datetime.today()).total_seconds())

            logLevel = logging.DEBUG if nextExecution == self._nextExecution and timeDifference > 0 else logging.INFO
            self._logger.log(logLevel, "Last execution was on %s", self._lastExecution)
            self._logger.log(logLevel, "Next execution is scheduled for %s", nextExecution)

            self._nextExecution = nextExecution

            if timeDifference > 0:
                sleepTime = min(timeDifference, 3600)
                self._timeout(sleepTime)
                return False

            return True

        self._logger.info("Command has never been executed")
        return True

    def _timeout(self, timeout):
        assert self._timeoutId is None
        assert self._timeoutTime is None

        self._timeoutId = GObject.timeout_add(timeout * 1000, self._timeoutCallback)
        self._timeoutTime = datetime.datetime.today() + datetime.timedelta(0, timeout)

        if timeout > 0:
            self._logger.debug("Sleeping for %s seconds...", timeout)

    def _timeoutCallback(self):
        self._timeoutId = None
        self._timeoutTime = None

        self._wait()
        return False

    def _waitUntilMainPower(self):
        try:
            upower = self._bus.get_object("org.freedesktop.UPower", "/org/freedesktop/UPower")
            onBattery = upower.Get("org.freedesktop.UPower", "OnBattery", dbus_interface=dbus.PROPERTIES_IFACE)
            self._logger.info("System is currently on %s power", (onBattery and "battery" or "main"))

            if onBattery:
                self._bus.add_signal_receiver(
                    self._batteryCallback,
                    dbus_interface="org.freedesktop.DBus.Properties",
                    signal_name="PropertiesChanged",
                    bus_name="org.freedesktop.UPower",
                    path="/org/freedesktop/UPower"
                )

                self._logger.info("Sleeping until the system is connected to main power...")
                return False
        except dbus.exceptions.DBusException:
            self._logger.warning("Unable to check the system's power source; assuming it's on main power")
            pass

        return True

    def _batteryCallback(self, interfaceName, changedProperties, invalidatedProperties):
        if "OnBattery" in changedProperties:
            if not changedProperties["OnBattery"]:
                self._bus.remove_signal_receiver(
                    self._batteryCallback,
                    dbus_interface="org.freedesktop.DBus.Properties",
                    signal_name="PropertiesChanged",
                    path="/org/freedesktop/UPower"
                )

                self._logger.info("System is now connected to main power")
                self._wait()

    def _initNotificationService(self):
        if not pynotify.init("{}.{}.{}".format(__name__, self._app, os.getpid())):
            self._logger.error("Failed to initialize notification service")
            raise RuntimeError("Failed to initialize notification service")

    def _initNotification(self):
        assert self._notification is None
        assert self._notificationAction is None

        self._logger.debug("Initializing notification...")

        backupName = self._backupName[1].format(self._name) if self._name else self._backupName[0]

        notificationData = self._notificationData.copy()
        notificationData["message"] = notificationData["message"].format(backupName)

        self._notification = pynotify.Notification(**notificationData)

        self._notification.set_urgency(pynotify.URGENCY_NORMAL)
        self._notification.set_timeout(pynotify.EXPIRES_NEVER)
        self._notification.set_category("presence")

        self._notification.add_action("start", "Start", self._notificationCallback)
        self._notification.add_action("skip", "Skip", self._notificationCallback)
        self._notification.add_action("default", "Not Now", self._notificationCallback)
        self._notification.connect("closed", self._notificationCloseCallback)

    def _resetNotification(self):
        assert self._notification is not None

        self._notification = None
        self._notificationAction = None

    def _notificationCallback(self, notification, action):
        assert notification == self._notification

        if action != "default":
            self._notificationAction = action

    def _notificationCloseCallback(self, notification):
        assert notification == self._notification

        if self._notificationTimeoutId is not None:
            self._resetNotificationTimeout()

        if self._notificationAction is None:
            self._logger.info("User dismissed the notification")

            self._resetNotification()

            self._timeout(self._sleepTime)
            return
        elif self._notificationAction != "ignore":
            self._logger.info("User requested to %s the backup", self._notificationAction)

            self.updateLastExecution()

            if self._notificationAction == "start":
                self.backup()

        self._logger.debug("Notification closed")

        self._resetNotification()

        self._timeout(0)

    def _notificationTimeout(self, timeout):
        assert self._notification is not None
        assert self._notificationTimeoutId is None
        assert self._notificationTimeoutTime is None

        self._notificationTimeoutId = GObject.timeout_add(timeout * 1000, self._notificationTimeoutCallback)
        self._notificationTimeoutTime = datetime.datetime.today() + datetime.timedelta(0, timeout)

        if timeout > 0:
            self._logger.debug("Giving user %s seconds to respond...", timeout)

    def _resetNotificationTimeout(self):
        assert self._notificationTimeoutId is not None

        GObject.source_remove(self._notificationTimeoutId)

        self._notificationTimeoutId = None
        self._notificationTimeoutTime = None

    def _notificationTimeoutCallback(self):
        assert self._notification is not None

        self._notificationTimeoutId = None
        self._notificationTimeoutTime = None

        self._notificationAction = "ignore"
        self._logger.info("User ignored the notification")

        try:
            self._notification.close()
        except dbus.exceptions.DBusException:
            self._logger.warning("DBus interface died, re-initializing...")
            self._initNotificationService()

            self._notificationAction = None
            self._notification = None

            self._timeout(0)

        return False

    def _showStatusNotification(self, status):
        assert status in ( self._STATUS_SUCCESS, self._STATUS_WARNING, self._STATUS_ERROR )

        if not pynotify.is_initted():
            self._initNotificationService()

        backupName = self._backupName[1].format(self._name) if self._name else self._backupName[0]

        notificationData = self._statusNotificationData[status].copy()
        notificationData["message"] = notificationData["message"].format(backupName)

        notification = pynotify.Notification(**notificationData)
        notification.set_urgency(pynotify.URGENCY_NORMAL)
        notification.set_timeout(pynotify.EXPIRES_NEVER)
        notification.set_category("presence")

        self._logger.info("Sending status notification...")
        self._showNotification(notification)

    def _showNotification(self, notification):
        assert notification is not None

        notificationShown = False

        try:
            notificationShown = notification.show()
        except dbus.exceptions.DBusException:
            self._logger.warning("DBus interface died, re-initializing...")
            self._initNotificationService()
        except Exception as error:
            self._logger.error(
                "While sending a notification, a exception occurred: %s: %s",
                type(error).__name__,
                error
            )
            raise

        if not notificationShown:
            self._logger.error("Failed to send notification")
            return False

        return True
