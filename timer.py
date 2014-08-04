#!/usr/bin/python

import argparse
import datetime
import httplib
import json
import time

import db
import secrets

db = db.DB('/var/lib/pi-timer/db.sqlite', None)

parser = argparse.ArgumentParser(description='Query pi-timer database')
parser.add_argument('action', choices=['history', 'clearhistory', 'schedule', 'clearschedule', 'authenticate', 'refreshgc'])
parser.add_argument('device', type=int)
parser.add_argument('--setschedule', nargs=4)

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

if args.action == "clearhistory":
    db.clear_device_history(args.device)
    print "Cleared history."

if args.action == "schedule":
    if args.setschedule:
        start_time = datetime.datetime.strptime(
            "%s %s" % (args.setschedule[0], args.setschedule[1]),
            "%Y-%m-%d %H:%M")
        duration = int(args.setschedule[2])
        min_duration = int(args.setschedule[3])
        db.set_device_schedule(args.device, start_time, duration, min_duration)
    schedule = db.get_device_schedule(args.device)
    if schedule:
        print "Device schedule:"
        for row in schedule:
            print "Run at %s for up to %d seconds (min %d seconds)" % (
                    datetime.datetime.fromtimestamp(row[1]), row[2], row[3])
            print "Set on %s" % datetime.datetime.fromtimestamp(row[0])
    else:
        print "No schedule set for %d" % args.device

if args.action == "clearschedule":
    db.clear_device_schedule(args.device)
    print "Cleared schedule."

if args.action == "authenticate":
    print "Visit this URL to get a token:"
    print "https://accounts.google.com/o/oauth2/auth?scope=https://www.googleapis.com/auth/calendar&redirect_uri=urn:ietf:wg:oauth:2.0:oob&response_type=code&client_id=%s" % secrets.OAUTH_CLIENT_ID
    code = raw_input("Enter code: ")

    conn = httplib.HTTPSConnection("accounts.google.com")
    conn.request("POST", "/o/oauth2/token", "code=%s&client_id=%s&client_secret=%s&redirect_uri=urn:ietf:wg:oauth:2.0:oob&grant_type=authorization_code" % (
        code, secrets.OAUTH_CLIENT_ID, secrets.OAUTH_SECRET),
        {"Content-Type": "application/x-www-form-urlencoded"})
    res = json.loads(conn.getresponse().read())
    print "Token: %s" % res["access_token"]
    print "Refresh: %s" % res["refresh_token"]
    db.set_tokens(res["access_token"], res["refresh_token"])

if args.action == "refreshgc":
    db.set_global("gcupdatetime", "0")
    print "gcupdatetime global reset."

