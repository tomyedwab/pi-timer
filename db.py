import sqlite3
import time


class DB(object):
    def __init__(self, filename, logger):
        self.conn = sqlite3.connect(filename)
        self.logger = logger
        
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS device_history 
                     (timestamp integer, device integer, enabled integer)''')
        c.execute('''CREATE TABLE IF NOT EXISTS device_schedule
                     (timestamp integer, device integer, hour integer,
                      minute integer, duration integer, min_duration integer)''')
        c.execute('''CREATE TABLE IF NOT EXISTS access_tokens
                     (access_token string, refresh_token string)''')
        self.conn.commit()

        if self.logger:
            self.logger.write_log("Opened Sqlite database.")

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
               WHERE device = ? AND timestamp > ?
               ORDER BY timestamp''',
            (device, from_timestamp))
        return list(rows)

    def get_device_schedule(self, device):
        c = self.conn.cursor()
        c.execute(
            '''SELECT timestamp, hour, minute, duration, min_duration FROM device_schedule
               WHERE device = ?
               ORDER BY timestamp DESC''',
            (device,))
        return c.fetchone()

    def set_device_schedule(self, device, hour, minute, duration, min_duration):
        c = self.conn.cursor()
        c.execute(
            '''INSERT INTO device_schedule VALUES (?, ?, ?, ?, ?, ?)''',
            (int(time.time()), device, hour, minute, duration, min_duration))
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

    def close(self):
        self.conn.close()
        if self.logger:
            self.logger.write_log("Closed Sqlite database.")

