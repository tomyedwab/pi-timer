#!/usr/bin/python

import argparse
import datetime
import time

import db

db = db.DB('/var/lib/pi-timer/db.sqlite', None)

parser = argparse.ArgumentParser(description='Query pi-timer database')
parser.add_argument('action', choices=['history', 'schedule'])
parser.add_argument('device', type=int)
parser.add_argument('--setschedule', nargs=4, type=int)

args = parser.parse_args()

if args.action == "history":
    history = db.get_device_history(args.device, int(time.time()) - (24*60*60))
    last_on_time = None
    for row in history:
        date_str = datetime.datetime.fromtimestamp(row[0])
        if row[1] == 1:
            print "%s: Device turned ON" % date_str
            last_on_time = row[0]
        elif row[1] == 0 and last_on_time:
            print "%s: Device turned OFF (%d seconds)" % (date_str, row[0] - last_on_time)
            last_on_time = None

if args.action == "schedule":
    if args.setschedule:
        db.set_device_schedule(args.device, *args.setschedule)
    print args.setschedule
    schedule = db.get_device_schedule(args.device)
    if schedule:
        print "Device schedule:"
        print "Run at %d:%02d every day for up to %d seconds (min %d seconds)" % (
                schedule[1], schedule[2], schedule[3], schedule[4])
        print "Set on %s" % datetime.datetime.fromtimestamp(schedule[0])
    else:
        print "No schedule set for %d" % args.device
