#!/usr/bin/python

import datetime
import sqlite3
import sys
import time
import traceback

class Logger(object):
    def __init__(self):
        self.f = open('/var/log/pi-timer.log', 'a')
        self.write_log("Logging started.")

    def write_log(self, msg):
        self.f.write("%s: %s\n" % (datetime.datetime.now(), msg))

    def close(self):
        self.write_log("Logging ended.")
        self.f.close()


class DB(object):
    def __init__(self, filename):
        self.conn = sqlite3.connect(filename)
        
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS device_history 
                     (timestamp integer, device integer, enabled integer)''')
        self.conn.commit()

        logger.write_log("Opened Sqlite database.")

    def log_device_enabled(self, device, enabled):
        timestamp = int(time.time())
        c = self.conn.cursor()
        c.execute("INSERT INTO device_history VALUES (%d, %d, %d)" % (
            timestamp, device, 1 if enabled else 0))
        self.conn.commit()

    def get_device_history(self, device, from_timestamp):
        c = self.conn.cursor()
        rows = c.execute(
            '''SELECT timestamp, enabled FROM device_history
               WHERE device = ? AND timestamp > ?''',
            (device, from_timestamp))
        return list(rows)

    def close(self):
        self.conn.close()
        logger.write_log("Closed Sqlite database.")


class Device(object):
    """A device that can be controlled by the GPIO pins on the Pi."""
    def __init__(self, identifier, display_name, pin, scheduler):
        self.identifier = identifier
        self.display_name = display_name
        self.pin = pin
        self.scheduler = scheduler

        self.on = None
        self.turn_off()

        # TODO: Configure IO

    def turn_off(self):
        if self.on == False:
            return

        # TODO: Set pin HIGH
        self.on = False
        logger.write_log("Turning OFF device %s (%d)" % (
            self.display_name, self.identifier))
        db.log_device_enabled(self.identifier, False)

    def turn_on(self):
        if self.on == True:
            return

        # TODO: Set pin LOW
        self.on = True
        logger.write_log("Turning ON device %s (%d)" % (
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
        # Only look back 23 hours so we don't count yesterday's run
        history = device.get_last_seconds(60*60*23)
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


# Main entry point
logger = Logger()
try:
    db = DB('/var/lib/pi-timer/db.sqlite')
except:
    logger.write_log("### Caught exception:\n%s" % traceback.format_exc())
    logger.close()
    sys.exit(0)
    
try:
    devices = [
        Device(101, "Front sprinklers", 0, FixedScheduler(14, 32, 211, 60)),
        Device(201, "Back sprinklers bank A", 0, Scheduler()),
        Device(202, "Back sprinklers bank B", 0, Scheduler())]

    while True:
        next_poll = 60
        # Update each device's schedule once per minute unless a device needs
        # a shorter update
        for device in devices:
            next_poll = min(next_poll, device.update())

        time.sleep(next_poll)

except:
    logger.write_log("### Caught exception:\n%s" % traceback.format_exc())
finally:
    for device in devices:
        device.turn_off()
    db.close()
    logger.close()
