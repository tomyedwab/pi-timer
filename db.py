import datetime
import sqlite3
import time


class DB(object):
    def __init__(self, filename, logger):
        self.conn = sqlite3.connect(filename)
        self.logger = logger
        
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS devices 
                     (device_id integer, group_id integer, type string, display_name string, pin integer)''')
        c.execute('''CREATE TABLE IF NOT EXISTS device_history 
                     (timestamp integer, device integer, enabled integer)''')
        c.execute('''CREATE TABLE IF NOT EXISTS device_schedule
                     (timestamp integer, device integer, start_time integer,
                      duration integer, min_duration integer)''')
        c.execute('''CREATE TABLE IF NOT EXISTS access_tokens
                     (access_token string, refresh_token string)''')
        c.execute('''CREATE TABLE IF NOT EXISTS globals
                     (name string, value string)''')
        self.conn.commit()

        if self.logger:
            self.logger.write_log("Opened Sqlite database.")

    def log_device_enabled(self, device, enabled):
        timestamp = int(time.time())
        c = self.conn.cursor()
        c.execute("INSERT INTO device_history VALUES (?, ?, ?)", (
            timestamp, device, 1 if enabled else 0))
        self.conn.commit()

    def list_devices(self):
        c = self.conn.cursor()
        rows = c.execute(
            '''SELECT device_id, group_id, type, display_name, pin FROM devices''')
        return list(rows)

    def add_device(self, device_id, group, type, display_name, pin):
        c = self.conn.cursor()
        c.execute("INSERT INTO devices VALUES (?, ?, ?, ?, ?)", (
            device_id, group, type, display_name, pin))
        self.conn.commit()

    def get_device_history(self, device, from_timestamp):
        c = self.conn.cursor()
        rows = c.execute(
            '''SELECT timestamp, enabled FROM device_history
               WHERE device = ? AND timestamp > ?
               ORDER BY timestamp''',
            (device, from_timestamp))
        return list(rows)

    def clear_device_history(self, device):
        c = self.conn.cursor()
        c.execute(
            '''DELETE FROM device_history WHERE device = ?''',
            (device,))
        self.conn.commit()

    def get_device_schedule(self, device):
        c = self.conn.cursor()
        return [row for row in c.execute(
            '''SELECT timestamp, start_time, duration, min_duration FROM device_schedule
               WHERE device = ?
               ORDER BY timestamp DESC''',
            (device,))]

    def set_device_schedule(self, device, start_time, duration, min_duration):
        timestamp = (start_time - datetime.datetime(1970, 1, 1)).total_seconds() + (7*60*60)
        c = self.conn.cursor()
        c.execute(
            '''INSERT INTO device_schedule VALUES (?, ?, ?, ?, ?)''',
            (int(time.time()), device, timestamp, duration, min_duration))
        self.conn.commit()

    def clear_device_schedule(self, device):
        c = self.conn.cursor()
        c.execute(
            '''DELETE FROM device_schedule WHERE device = ?''',
            (device,))
        self.conn.commit()

    def set_tokens(self, access_token, refresh_token):
        c = self.conn.cursor()
        c.execute("DELETE FROM access_tokens")
        c.execute("INSERT INTO access_tokens VALUES (?, ?)",
                (access_token, refresh_token))
        self.conn.commit()

    def get_tokens(self):
        c = self.conn.cursor()
        c.execute(
            '''SELECT access_token, refresh_token FROM access_tokens''')
        return c.fetchone()

    def get_global(self, name):
        c = self.conn.cursor()
        c.execute(
            '''SELECT value FROM globals WHERE name = ?''',
            (name,))
        return c.fetchone()[0]

    def set_global(self, name, value):
        c = self.conn.cursor()
        c.execute(
            '''DELETE FROM globals WHERE name = ?''',
            (name,))
        c.execute(
            '''INSERT INTO globals VALUES (?, ?)''',
            (name,value))
        self.conn.commit()

    def close(self):
        self.conn.close()
        if self.logger:
            self.logger.write_log("Closed Sqlite database.")

