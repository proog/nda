import sqlite3
from datetime import datetime
from util import normalize_nick


class Mail:
    db_name = 'mail.db'

    def __init__(self, aliases=None):
        self.aliases = aliases if aliases is not None else {}
        self.db = sqlite3.connect(self.db_name)
        self.db.execute('CREATE TABLE IF NOT EXISTS nicks (id INTEGER PRIMARY KEY AUTOINCREMENT, nick TEXT UNIQUE, last_seen INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, from_nick TEXT, to_nick TEXT, message TEXT, received INTEGER, sent_at INTEGER, received_at INTEGER)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_to_nick ON messages (to_nick)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_received ON messages (received)')
        self.db.commit()

    def update_last_seen(self, nick, timestamp=None):
        nick = normalize_nick(nick, self.aliases)
        timestamp = timestamp if timestamp is not None else int(datetime.utcnow().timestamp())
        cursor = self.db.cursor()
        cursor.execute('INSERT OR IGNORE INTO nicks (nick) VALUES (?)', (nick,))
        cursor.execute('UPDATE nicks SET last_seen=? WHERE nick=?', (timestamp, nick))
        self.db.commit()

    def last_seen(self, nick):
        alias = normalize_nick(nick, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('SELECT last_seen FROM nicks WHERE nick=?', (alias,))
        row = cursor.fetchone()

        if row is None or row[0] is None:
            return '%s has never been seen :(' % nick

        return '%s was last seen on %s :)' % (nick, datetime.utcfromtimestamp(row[0]).strftime('%Y-%m-%d %H:%M:%S'))

    def send(self, from_, to, message):
        cursor = self.db.cursor()
        cursor.execute('INSERT INTO messages (from_nick, to_nick, message, received, sent_at, received_at) VALUES (?, ?, ?, ?, ?, ?)',
                       (from_, to, message, False, int(datetime.utcnow().timestamp()), None))
        self.db.commit()

    def unsend(self, from_, id):
        cursor = self.db.cursor()
        cursor.execute('DELETE FROM messages WHERE from_nick=? AND id=?', (from_, id))
        self.db.commit()
        return cursor.rowcount > 0

    def outbox(self, from_):
        cursor = self.db.cursor()
        cursor.execute('SELECT id, to_nick, message FROM messages WHERE from_nick=? AND received=? ORDER BY id', (from_, False))
        return ['%i: (%s) %s' % (id, to, msg) for id, to, msg in cursor.fetchall()]

    def unread_messages(self, to):
        cursor = self.db.cursor()
        cursor.execute('SELECT from_nick, message, sent_at FROM messages WHERE to_nick=? AND received=? ORDER BY sent_at ASC', (to, False))

        messages = ['%s -- %s, %s' % (msg, from_, datetime.utcfromtimestamp(sent).strftime('%Y-%m-%d %H:%M:%S'))
                    for from_, msg, sent in cursor.fetchall()]

        now = int(datetime.utcnow().timestamp())
        cursor.execute('UPDATE messages SET received=?, received_at=? WHERE to_nick=? AND received=?', (True, now, to, False))
        self.db.commit()

        return messages

    def unread_receivers(self):
        cursor = self.db.cursor()
        cursor.execute('SELECT DISTINCT to_nick FROM messages WHERE received=?', (False,))
        return [nick for (nick,) in cursor.fetchall()]

    def close(self):
        self.db.close()
