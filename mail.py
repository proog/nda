import sqlite3
from datetime import datetime


class Mail:
    db_name = 'mail.db'
    table_name = 'messages'

    def __init__(self):
        self.db = sqlite3.connect(self.db_name)

        cursor = self.db.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY AUTOINCREMENT, from_nick TEXT, to_nick TEXT, message TEXT, received INTEGER, sent_at INTEGER, received_at INTEGER)' % self.table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_to_nick ON %s (to_nick)' % self.table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_received ON %s (received)' % self.table_name)
        self.db.commit()

    def send(self, from_, to, message):
        cursor = self.db.cursor()
        cursor.execute('INSERT INTO %s (from_nick, to_nick, message, received, sent_at, received_at) VALUES (?, ?, ?, ?, ?, ?)'
                       % self.table_name, (from_, to, message, False, int(datetime.utcnow().timestamp()), None))
        self.db.commit()

    def unread(self, to):
        cursor = self.db.cursor()
        cursor.execute('SELECT from_nick, message, sent_at FROM %s WHERE to_nick == ? AND received == ? ORDER BY sent_at ASC' % self.table_name, (to, False))

        messages = ['%s -- %s, %s' % (msg, from_, datetime.utcfromtimestamp(sent).strftime('%Y-%m-%d %H:%M:%S'))
                    for from_, msg, sent in cursor.fetchall()]

        now = int(datetime.utcnow().timestamp())
        cursor.execute('UPDATE %s SET received = ?, received_at = ? WHERE to_nick == ? AND received == ?' % self.table_name, (True, now, to, False))
        self.db.commit()

        return messages

    def unread_receivers(self):
        cursor = self.db.cursor()
        cursor.execute('SELECT DISTINCT to_nick FROM %s WHERE received == ?' % self.table_name, (False,))
        return [nick for (nick,) in cursor.fetchall()]

    def close(self):
        self.db.close()
