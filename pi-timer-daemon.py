#!/usr/bin/python

import datetime
import httplib
import json
import signal
import sys
import time
import traceback

import db
import secrets

# Set a flag if a graceful exit is requested
kill_signal = False
def sigterm_handler(_signo, _stack_frame):
    global kill_signal
    kill_signal = True

signal.signal(signal.SIGTERM, sigterm_handler)


enable_rpio = True

class Logger(object):
    def __init__(self):
        self.f = open('/var/log/pi-timer.log', 'a')
        self.write_log("Logging started.")

    def write_log(self, msg):
        self.f.write("%s: %s\n" % (datetime.datetime.now(), msg))
        self.f.flush()

    def close(self):
        self.write_log("Logging ended.")
        self.f.close()


if enable_rpio:
    import RPi.GPIO as GPIO
    class DeviceIO(object):
        """IO controller for Raspberry Pi."""
        def __init__(self):
            logger.write_log("Initializing GPIO.")
            GPIO.setmode(GPIO.BCM)

        def init_output(self, pin):
            GPIO.setup(pin, GPIO.OUT)

        def set_output(self, pin, output):
            logger.write_log("Setting pin %d to %d" % (pin, output))
            GPIO.output(pin, output)

        def close(self):
            logger.write_log("Cleaning up GPIO.")
            GPIO.cleanup()

    import watchdogdev
    watchdog = watchdogdev.watchdog("/dev/watchdog")
    def keep_alive():
        watchdog.keep_alive()
else:
    class DeviceIO(object):
        """Dummy IO controller."""
        def __init__(self):
            pass

        def init_output(self, pin):
            pass

        def set_output(self, pin, output):
            pass

        def close(self):
            pass

    def keep_alive():
        pass


class Device(object):
    """A device that can be controlled by the GPIO pins on the Pi."""
    # Only one device per group can be on at a time
    group_locks = {}

    def __init__(self, io, identifier, group, display_name, pin, scheduler):
        self.io = io
        self.identifier = identifier
        self.group = group
        self.display_name = display_name
        self.pin = pin
        self.scheduler = scheduler

        io.init_output(self.pin)

        self.on = None
        self.turn_off()

        # TODO: Configure IO

    def turn_off(self):
        if self.on == False:
            return

        self.io.set_output(self.pin, 1)
        self.on = False
        logger.write_log("Turned OFF device %s (%d)" % (
            self.display_name, self.identifier))
        db.log_device_enabled(self.identifier, False)

        if (self.group in Device.group_locks and
                Device.group_locks[self.group] == self.identifier):
            del Device.group_locks[self.group]

    def turn_on(self):
        if self.on == True:
            return

        if (self.group in Device.group_locks and
                Device.group_locks[self.group] != self.identifier):
            # Some other device has the lock; defer
            logger.write_log("Device %s (%d) waiting on %d for lock." % (
                self.display_name, self.identifier, Device.group_locks[self.group]))
            return

        Device.group_locks[self.group] = self.identifier

        self.io.set_output(self.pin, 0)
        self.on = True
        logger.write_log("Turned ON device %s (%d)" % (
            self.display_name, self.identifier))
        db.log_device_enabled(self.identifier, True)

    def update(self):
        (enable, poll_time) = self.scheduler.should_enable(self)
        if enable:
            self.turn_on()
        else:
            self.turn_off()
        return poll_time

    def get_last_seconds(self, seconds):
        last_day = int(time.time()) - seconds
        return db.get_device_history(self.identifier, last_day)


class Scheduler(object):
    """An object that determines when a device is enabled or disabled."""
    def should_enable(self, device):
        """Override this function in subclasses to do interesting things."""
        return (False, 10000)


class FixedScheduler(Scheduler):
    """Turn on at a certain hour/minute each day for given duration (sec).
    
    This scheduler will enable the device anytime after hour/minute until the
    given total duration (in seconds) has been met for the day.
    
    The device will not be turned on for less than min_duration seconds at a
    time.
    """
    def __init__(self, hour, minute, duration, min_duration):
        self.hour = hour
        self.minute = minute
        self.duration = duration
        self.min_duration = min_duration

    def should_enable(self, device):
        # Only look back 12 hours so we don't count yesterday's run
        history = device.get_last_seconds(60*60*12)
        start_time = None
        total_seconds = 0
        for row in history:
            if row[1] == 1:
                start_time = row[0]
            elif row[1] == 0:
                if start_time:
                    total_seconds += row[0] - start_time
                start_time = None
        if start_time:
            total_seconds += int(time.time()) - start_time

        now = datetime.datetime.now()
        if (now.hour > self.hour or (
            now.hour == self.hour and now.minute >= self.minute)):
            if total_seconds < self.duration and (
                device.on or (self.duration - total_seconds) > self.min_duration):
                if not device.on:
                    logger.write_log("Device %d has been on %d sec. in last 24 hours." % (device.identifier, total_seconds))
                    logger.write_log("Turning device on for %d sec." % (self.duration - total_seconds))
                return (True, self.duration - total_seconds)

        return (False, 10000)


class DBScheduler(FixedScheduler):
    """Works like FixedScheduler, except the schedule is stored in the DB."""
    def __init__(self):
        self.hour = 0
        self.minute = 0
        self.duration = 0
        self.min_duration = 0

    def should_enable(self, device):
        (_, self.hour, self.minute, self.duration, self.min_duration) = (
            db.get_device_schedule(device.identifier))
        return super(DBScheduler, self).should_enable(device)


class GoogleCalendarScheduler(FixedScheduler):
    """Like FixedScheduler, but the schedule is stored in Google Calendar."""
    def __init__(self, min_duration, max_duration):
        self.hour = 0
        self.minute = 0
        self.duration = 0
        self.min_duration = min_duration
        self.max_duration = max_duration

    last_update = 0
    error_count = 0
    schedules = {}

    @staticmethod
    def update_from_gc():
        # Update from GC once an hour
        if int(time.time()) - GoogleCalendarScheduler.last_update < 60*60:
            return

        logger.write_log("Syncing Google calendar")

        (access_token, refresh_token) = db.get_tokens()

        min_time = datetime.datetime.now() - datetime.timedelta(1)
        max_time = datetime.datetime.now() + datetime.timedelta(1)
        today = datetime.datetime.now()

        conn = httplib.HTTPSConnection("www.googleapis.com")
        conn.request("GET", "/calendar/v3/calendars/%s/events?access_token=%s" % (
            secrets.CALENDAR_ID, access_token))
        res = json.loads(conn.getresponse().read())
        if "error" in res:
            GoogleCalendarScheduler.error_count += 1
            if GoogleCalendarScheduler.error_count > 3:
                logger.write_log("### Too many errors in a row. Giving up.")
                return

            logger.write_log("### Error getting calendar, attempting to refresh token:\n%s" % res["error"]["message"])
            conn = httplib.HTTPSConnection("accounts.google.com")
            conn.request("POST", "/o/oauth2/token", "client_id=%s&client_secret=%s&refresh_token=%s&grant_type=refresh_token" % (
                secrets.OAUTH_CLIENT_ID, secrets.OAUTH_SECRET, refresh_token),
                {"Content-Type": "application/x-www-form-urlencoded"})
            res = json.loads(conn.getresponse().read())
            db.set_tokens(res["access_token"], refresh_token)
            return

        GoogleCalendarScheduler.error_count = 0

        for event in res["items"]:
            if event["summary"].split(":")[0] == "device":
                event_id = event["id"]
                device_id = int(event["summary"].split(":")[1])
                logger.write_log("Syncing device %d" % device_id)
                conn.request("GET", "/calendar/v3/calendars/%s/events/%s/instances?timeMin=%s-07:00&timeMax=%s-07:00&access_token=%s" % (
                    secrets.CALENDAR_ID, event_id, min_time.isoformat('T'), max_time.isoformat('T'), access_token))
                res = json.loads(conn.getresponse().read())

                if device_id in GoogleCalendarScheduler.schedules:
                    del GoogleCalendarScheduler.schedules[device_id]

                for instance in res["items"]:
                    start_time = datetime.datetime.strptime(instance["start"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S")
                    end_time = datetime.datetime.strptime(instance["end"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S")
                    if start_time.year == today.year and start_time.month == today.month and start_time.day == today.day:
                        schedule = {
                            "hour": start_time.hour,
                            "minute": start_time.minute,
                            "duration": (end_time-start_time).total_seconds()
                        }
                        logger.write_log("Device %d runs at %d:%02d for up to %d seconds" % (device_id, schedule["hour"], schedule["minute"], schedule["duration"]))
                        GoogleCalendarScheduler.schedules[device_id] = schedule

        GoogleCalendarScheduler.last_update = int(time.time())

    def should_enable(self, device):
        self.update_from_gc()
        
        if device.identifier in GoogleCalendarScheduler.schedules:
            schedule = GoogleCalendarScheduler.schedules[device.identifier]
            self.hour = schedule["hour"]
            self.minute = schedule["minute"]
            self.duration = schedule["duration"]
            if self.duration > self.max_duration:
                logger.write_log("ERROR! Duration of %d seconds exceeded maximum of %d! Clamping." % (self.duration, self.max_duration))
                self.duration = self.max_duration

        return super(GoogleCalendarScheduler, self).should_enable(device)


# Main entry point
logger = Logger()
devices = None
try:
    db = db.DB('/var/lib/pi-timer/db.sqlite', logger)
except:
    logger.write_log("### Caught exception:\n%s" % traceback.format_exc())
    logger.close()
    sys.exit(0)
    
try:
    io = DeviceIO()

    devices = [
        Device(io, 101, 1000, "Front sprinklers", 18, GoogleCalendarScheduler(60, 1200)),
        Device(io, 201, 1000, "Back sprinklers bank A", 23, GoogleCalendarScheduler(60, 1200)),
        Device(io, 202, 1000, "Back sprinklers bank B", 24, GoogleCalendarScheduler(60, 1200))]

    while True:
        next_poll = 60
        # Update each device's schedule once per minute unless a device needs
        # a shorter update
        for device in devices:
            next_poll = min(next_poll, device.update())

        for i in xrange(0, next_poll*12):
            # Sleep for 5 seconds at a time, up until it's time to poll again
            time.sleep(1.0/12)
            keep_alive()
            if kill_signal:
                break

        if kill_signal:
            logger.write_log("### Caught TERM signal. Exiting.")
            break

except:
    logger.write_log("### Caught exception:\n%s" % traceback.format_exc())
finally:
    if devices:
        for device in devices:
            device.turn_off()
    io.close()
    db.close()
    logger.close()
