""" cron-notify

FreeDesktop.org-compatible notification service to periodically ask for
acknowledgement before executing a cronjob. It is often used for backup
software.

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, version 3 of the License only.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

__version__ = "1.0.3"

__copyright__ = "Copyright (C) 2016-2019 Daniel Rudolf"
__license__ = "GPL-3"

import croniter, datetime, dbus, dbus.mainloop.glib, errno, hashlib, logging, os, re, subprocess, sys, threading
from gi.repository import GObject
from xdg import BaseDirectory

try:
    import pynotify
except ImportError:
    import notify2 as pynotify

class CronNotify(object):
    _STATUS_SUCCESS = 0
    _STATUS_TRY_AGAIN = 1
    _STATUS_WARNING = 2
    _STATUS_ERROR = 3

    _app = "cron-notify"

    _id = None
    _commands = None
    _async = True

    _name = None
    _cronExpression = "0 8 * * *"
    _sleepTime = 3600
    _mainPower = False

    _cacheFile = None

    _lastExecution = None
    _nextExecution = None

    _executionId = 0
    _lock = None

    _bus = None

    _timeoutId = None
    _timeoutTime = None

    _notification = None
    _notificationAction = None
    _notificationTimeoutId = None
    _notificationTimeoutTime = None

    _streams = { "stdin": None, "stdout": None, "stderr": None }

    _logger = None

    _nameTemplate = ( "cronjob", 'cronjob "{}"' )
    _notificationData = {
        "summary": "cron-notify",
        "message": "It's time to execute {}!",
        "icon": "appointment-soon"
    }
    _statusNotificationData = {
        _STATUS_SUCCESS: {
            "summary": "cron-notify",
            "message": "Your recent {} was successful. Yay!",
            "icon": "dialog-information"
        },
        _STATUS_WARNING: {
            "summary": "cron-notify",
            "message": "Your recent {} finished with warnings. " +
                "This might not be a problem, but you should check your logs.",
            "icon": "dialog-warning"
        },
        _STATUS_ERROR: {
            "summary": "cron-notify",
            "message": "Your recent {} failed. Check your logs!",
            "icon": "dialog-error"
        }
    }

    def __init__(self, commands, app=None, id=None, async=False):
        if not commands or len(commands) == 0:
            raise ValueError("Invalid commands given")

        if app is not None:
            if not re.match("^[\w.-]*$", app):
                raise ValueError("Invalid app given")
            self._app = app

        if id is not None:
            if not re.match("^[\w.-]*$", id):
                raise ValueError("Invalid id given")
            self._id = id
        else:
            self._id = hashlib.sha1(str(commands).encode("utf-8")).hexdigest()

        self._commands = commands
        self._async = async

        logHandler = logging.StreamHandler(stream=sys.stderr)
        logHandler.setFormatter(logging.Formatter("%(asctime)s: %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

        self._logger = logging.getLogger("{}.{}.{}.{}".format(__name__, self._app, os.getpid(), self._id))
        self._logger.addHandler(logHandler)
        self._logger.setLevel(logging.WARNING)

        self._cacheFile = BaseDirectory.save_cache_path(self._app) + "/" + self._id

        self._lock = threading.Lock()

    @property
    def app(self):
        return self._app

    @property
    def id(self):
        return self._id

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
    def mainPower(self):
        return self._mainPower

    @mainPower.setter
    def mainPower(self, mainPower):
        self._mainPower = not not mainPower

    @property
    def streams(self):
        return self._streams

    @streams.setter
    def streams(self, streams):
        self._streams = {
            "stdin": streams.get("stdin"),
            "stdout": streams.get("stdout"),
            "stderr": streams.get("stderr")
        }

    @property
    def meta(self):
        return {
            "nameTemplate": self._nameTemplate,
            "notification": self._notificationData,
            "success": self._statusNotificationData[self._STATUS_SUCCESS],
            "warning": self._statusNotificationData[self._STATUS_WARNING],
            "failure": self._statusNotificationData[self._STATUS_ERROR]
        }

    @meta.setter
    def meta(self, meta):
        if "nameTemplate" in meta:
            self._nameTemplate = meta.get("nameTemplate")
        if "notification" in meta:
            self._notificationData.update(meta.get("notification"))
        if "success" in meta:
            self._statusNotificationData[self._STATUS_SUCCESS].update(meta.get("success"))
        if "warning" in meta:
            self._statusNotificationData[self._STATUS_WARNING].update(meta.get("warning"))
        if "failure" in meta:
            self._statusNotificationData[self._STATUS_ERROR].update(meta.get("failure"))

    @property
    def logger(self):
        return self._logger

    def main(self):
        self._logger.info("Initializing...")

        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        self._bus = dbus.SystemBus()
        if not self._bus:
            self._logger.critical("Failed to initialize DBus system bus")
            raise RuntimeError("Failed to initialize DBus system bus")

        self._initNotificationService()

        self._monitorResuming()
        self._timeout(0)

    def resetCache(self):
        try:
            self._logger.info("Resetting cache...")
            os.remove(self._cacheFile)
        except OSError as error:
            if error.errno != errno.ENOENT:
                self._logger.critical(
                    "While resetting the cache, a exception occurred: %s: %s",
                    type(error).__name__,
                    str(error)
                )
                raise

    def run(self, blocking=None):
        self._executionId += 1

        if blocking is None:
            blocking = not self._async
        elif not blocking and not self._async:
            self._logger.critical("Impossible to run a command both synchronous and non-blocking")
            raise RuntimeError("Impossible to run a command both synchronous and non-blocking")

        self.updateLastExecution()

        if self._async:
            commandThreadArgs = {
                "executionId": self._executionId,
                "previousExecution": self._lastExecution,
                "logPrefix": "[#{}] ".format(self._executionId)
            }

            commandThread = threading.Thread(target=self._run, kwargs=commandThreadArgs)
            commandThread.start()

            if blocking:
                commandThread.join()

            return None
        else:
            return self._run(self._executionId, self._lastExecution)

    def _run(self, executionId, previousExecution, logPrefix=""):
        self._logger.debug("%sAcquiring lock...", logPrefix)
        self._lock.acquire()

        overallStatus = self._STATUS_SUCCESS
        for command in self._commands:
            self._logger.info("%sExecuting `%s`...", logPrefix, " ".join(command))

            try:
                subprocess.check_call(command, **self._streams)
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
                    self._logger.critical(
                        "%sExecution of `%s` failed: %s: %s",
                        logPrefix,
                        " ".join(command),
                        type(error).__name__,
                        str(error)
                    )
                    raise
            except subprocess.CalledProcessError as error:
                status = self._STATUS_ERROR
                logLevel = logging.ERROR

                if error.returncode == 254:
                    status = self._STATUS_WARNING
                    logLevel = logging.WARNING
                elif error.returncode == 75:
                    status = self._STATUS_TRY_AGAIN
                    logLevel = logging.INFO

                if overallStatus < status:
                    overallStatus = status

                self._logger.log(
                    logLevel,
                    "%sExecution of `%s` finished with exit status %s",
                    logPrefix,
                    " ".join(command),
                    error.returncode
                )

        if overallStatus == self._STATUS_TRY_AGAIN:
            self._logger.info("%sCommand finished with a temporary error", logPrefix)

            if executionId == self._executionId:
                self._logger.info("Resetting cache...")
                self.updateLastExecution(previousExecution)

                if self._timeoutId is not None:
                    GObject.source_remove(self._timeoutId)

                    self._timeoutId = None
                    self._timeoutTime = None

                    self._timeout(0)
        else:
            if overallStatus == self._STATUS_SUCCESS:
                self._logger.info("%sCommand finished successfully", logPrefix)
            elif overallStatus == self._STATUS_WARNING:
                self._logger.warning("%sCommand finished with warnings", logPrefix)
            else:
                self._logger.error("%sCommand failed", logPrefix)

            self._showStatusNotification(overallStatus)

        self._lock.release()
        return overallStatus != self._STATUS_ERROR

    def getLastExecution(self):
        lastExecution = None
        try:
            with open(self._cacheFile, "rt") as cacheFile:
                lastExecutionTime = cacheFile.read(20)
                if lastExecutionTime:
                    lastExecution = datetime.datetime.fromtimestamp(int(lastExecutionTime))
        except IOError as error:
            if error.errno != errno.ENOENT:
                self._logger.critical(
                    "While reading the last execution time, a exception occurred: %s: %s",
                    type(error).__name__,
                    str(error)
                )
                raise

        return lastExecution

    def getNextExecution(self, lastExecution=None):
        if lastExecution is None:
            lastExecution = datetime.datetime.today()

        nextExecutionCroniter = croniter.croniter(self._cronExpression, lastExecution)
        return nextExecutionCroniter.get_next(datetime.datetime)

    def updateLastExecution(self, lastExecution=None):
        if lastExecution is None:
            lastExecution = datetime.datetime.today()

        with open(self._cacheFile, "wt") as cacheFile:
            timezoneOffset = datetime.datetime.utcnow() - datetime.datetime.today()
            timestamp = int((lastExecution + timezoneOffset - datetime.datetime(1970, 1, 1)).total_seconds())
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
        try:
            if self._waitUntilScheduled():
                if not self._mainPower or self._waitUntilMainPower():
                    self._initNotification()

                    self._notificationTimeout(self._sleepTime)

                    self._logger.info("Sending notification...")
                    if not self._showNotification(self._notification):
                        self._resetNotificationTimeout()
                        self._resetNotification()
                        self._timeout(0)
        except Exception as error:
            self.logger.critical("%s: %s", type(error).__name__, str(error), exc_info=True)
            raise

    def _waitUntilScheduled(self):
        self._lastExecution = self.getLastExecution()

        if self._lastExecution is None:
            self._logger.info("Command has never been executed")
            self._nextExecution = datetime.datetime.today()
            return True

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
            self._logger.critical("Failed to initialize notification service")
            raise RuntimeError("Failed to initialize notification service")

    def _initNotification(self):
        assert self._notification is None
        assert self._notificationAction is None

        self._logger.debug("Initializing notification...")

        name = self._nameTemplate[1].format(self._name) if self._name else self._nameTemplate[0]

        notificationData = self._notificationData.copy()
        notificationData["message"] = notificationData["message"].format(name)

        self._notification = pynotify.Notification(**notificationData)

        self._notification.set_urgency(pynotify.URGENCY_NORMAL)
        self._notification.set_timeout(pynotify.EXPIRES_NEVER)
        self._notification.set_category("presence")

        self._notification.add_action("start", "Start", self._notificationCallback)
        self._notification.add_action("skip", "Skip", self._notificationCallback)
        self._notification.add_action("later", "Later", self._notificationCallback)
        self._notification.add_action("default", "", self._notificationCallback)
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
        elif self._notificationAction == "later":
            self._logger.info("User requested to notify again later")

            self._resetNotification()

            self._timeout(self._sleepTime)
            return
        elif self._notificationAction != "ignore":
            self._logger.info("User requested to %s the command", self._notificationAction)

            if self._notificationAction == "start":
                self.run()
            else:
                self.updateLastExecution()

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
        except Exception as error:
            self.logger.critical("%s: %s", type(error).__name__, str(error), exc_info=True)
            raise

        return False

    def _showStatusNotification(self, status):
        assert status in ( self._STATUS_SUCCESS, self._STATUS_WARNING, self._STATUS_ERROR )

        if not pynotify.is_initted():
            self._initNotificationService()

        name = self._nameTemplate[1].format(self._name) if self._name else self._nameTemplate[0]

        notificationData = self._statusNotificationData[status].copy()
        notificationData["message"] = notificationData["message"].format(name)

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
            self._logger.critical(
                "While sending a notification, a exception occurred: %s: %s",
                type(error).__name__,
                str(error),
                exc_info=True
            )
            raise

        if not notificationShown:
            self._logger.error("Failed to send notification")
            return False

        return True
