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

try:
    import RPi.GPIO as GPIO
    enable_rpio = True
except ImportError:
    enable_rpio = False

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

    def __init__(self, io, identifier, group, type, display_name, pin, scheduler):
        self.io = io
        self.identifier = identifier
        self.group = group
        self.type = type
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
    def __init__(self, schedule):
        self.schedule = schedule

    def should_enable(self, device):
        for item in self.schedule:
            start_time = item["start_time"]
            duration = item["duration"]
            min_duration = item["min_duration"]
            window = duration + 60*60
            delta = (datetime.datetime.now() - start_time).total_seconds()
            if delta < 0 or delta > window:
                continue

            if duration < min_duration:
                continue

            history = device.get_last_seconds(window)
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

            if total_seconds < duration and (
                device.on or (duration - total_seconds) > min_duration):
                if not device.on:
                    logger.write_log("Device %d has been on %d sec. in last %d seconds." % (device.identifier, total_seconds, window))
                    logger.write_log("Turning device on for %d sec." % (duration - total_seconds))
                return (True, int(duration - total_seconds))

        return (False, 10000)


class DBScheduler(FixedScheduler):
    """Works like FixedScheduler, except the schedule is stored in the DB."""
    def __init__(self):
        self.schedule = []

    def should_enable(self, device):
        schedule = (
            db.get_device_schedule(device.identifier))
        self.schedule = [
            {
                "start_time": datetime.datetime.fromtimestamp(item[0]),
                "duration": item[2],
                "min_duration": item[3]
            }
            for item in schedule]
        return super(DBScheduler, self).should_enable(device)


class GoogleCalendarScheduler(FixedScheduler):
    """Like FixedScheduler, but the schedule is stored in Google Calendar."""
    def __init__(self, min_duration, max_duration):
        self.schedule = []
        self.min_duration = min_duration
        self.max_duration = max_duration

    error_count = 0
    schedules = {}

    @staticmethod
    def update_from_gc():
        # Update from GC once an hour
        last_update = int(db.get_global("gcupdatetime"))
        if int(time.time()) - last_update < 60*60:
            return

        logger.write_log("Syncing Google calendar")

        (access_token, refresh_token) = db.get_tokens()

        min_time = datetime.datetime.now() - datetime.timedelta(1)
        max_time = datetime.datetime.now() + datetime.timedelta(1)

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

        # Clear all schedules
        for device_id in GoogleCalendarScheduler.schedules.keys():
            db.clear_device_schedule(device_id)

        GoogleCalendarScheduler.schedules = {}

        for event in res["items"]:
            if event["summary"].split(":")[0] == "device":
                event_id = event["id"]
                device_id = int(event["summary"].split(":")[1])
                logger.write_log("Syncing device %d" % device_id)
                conn.request("GET", "/calendar/v3/calendars/%s/events/%s/instances?timeMin=%s-07:00&timeMax=%s-07:00&access_token=%s" % (
                    secrets.CALENDAR_ID, event_id, min_time.isoformat('T'), max_time.isoformat('T'), access_token))
                res = json.loads(conn.getresponse().read())


                for instance in res["items"]:
                    start_time = datetime.datetime.strptime(instance["start"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S")
                    end_time = datetime.datetime.strptime(instance["end"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S")
                    schedule = {
                        "start_time": start_time,
                        "duration": (end_time-start_time).total_seconds()
                    }
                    logger.write_log("Device %d runs at %s for up to %d seconds" % (device_id, schedule["start_time"], schedule["duration"]))
                    GoogleCalendarScheduler.schedules[device_id].append(schedule)
                    db.set_device_schedule(device_id, schedule["start_time"], schedule["duration"], 0)

        db.set_global("gcupdatetime", str(int(time.time())))

    def should_enable(self, device):
        self.update_from_gc()
        
        if device.identifier in GoogleCalendarScheduler.schedules:
            self.schedule = []
            for item in GoogleCalendarScheduler.schedules[device.identifier]:
                schedule_item = {
                    "start_time": item["start_time"],
                    "duration": item["duration"],
                    "min_duration": self.min_duration
                }
                if schedule_item["duration"] > self.max_duration:
                    logger.write_log("ERROR! Duration of %d seconds exceeded maximum of %d! Clamping." % (schedule_item["duration"], self.max_duration))
                    schedule_item["duration"] = self.max_duration
                self.schedule.append(schedule_item)

        return super(GoogleCalendarScheduler, self).should_enable(device)


# Main entry point
logger = Logger()
devices = {}
try:
    db = db.DB('/var/lib/pi-timer/db.sqlite', logger)
except:
    logger.write_log("### Caught exception:\n%s" % traceback.format_exc())
    logger.close()
    sys.exit(0)
    
try:
    db.set_global("gcupdatetime", "0")

    io = DeviceIO()

    while True:
        # Fetch devices
        for device in db.list_devices():
            if device[0] not in devices:
                devices[device[0]] = (
                    Device(io, device[0], device[1], device[2], device[3], device[4],
                        GoogleCalendarScheduler(60, 1200)))

        next_poll = 60
        # Update each device's schedule once per minute unless a device needs
        # a shorter update
        for device in devices.itervalues():
            next_poll = min(next_poll, device.update())

        for i in xrange(0, next_poll):
            # Sleep for 1 second at a time, up until it's time to poll again
            time.sleep(1)
            keep_alive()
            if kill_signal:
                break

        if kill_signal:
            logger.write_log("### Caught TERM signal. Exiting.")
            break

except:
    logger.write_log("### Caught exception:\n%s" % traceback.format_exc())
finally:
    for device in devices.itervalues():
        device.turn_off()
    io.close()
    db.close()
    logger.close()
