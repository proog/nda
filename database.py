import sqlite3
import re
import random
import json
from datetime import datetime, timezone, timedelta
from util import normalize_nick, year_to_timestamps, escape_sql_like, clamp


class Database:
    def __init__(self, db_name, aliases=None, ignore_nicks=None):
        self.aliases = aliases if aliases is not None else {}
        self.ignore_nicks = ignore_nicks if ignore_nicks is not None else []

        self.db = sqlite3.connect(db_name)
        self.db.execute('''CREATE TABLE IF NOT EXISTS channels (
            channel TEXT NOT NULL PRIMARY KEY,
            seq_id  INTEGER NOT NULL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS quotes_full (
            channel    TEXT NOT NULL,
            seq_id     INTEGER NOT NULL,
            time       INTEGER,
            author     TEXT,
            raw_author TEXT,
            message    TEXT,
            word_count INTEGER,
            PRIMARY KEY (channel, seq_id))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS quotes (
            channel TEXT NOT NULL,
            seq_id  INTEGER NOT NULL,
            time    INTEGER,
            author  TEXT,
            message TEXT,
            PRIMARY KEY (channel, seq_id))''')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_time    ON quotes (time)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_author  ON quotes (author)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_message ON quotes (message)')

        self.db.execute('''CREATE TABLE IF NOT EXISTS nicks (
            nick       TEXT NOT NULL PRIMARY KEY,
            last_seen  INTEGER,
            utc_offset INTEGER)''')

        self.db.execute('''CREATE TABLE IF NOT EXISTS mail (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_nick   TEXT,
            to_nick     TEXT,
            message     TEXT,
            received    INTEGER,
            sent_at     INTEGER,
            received_at INTEGER)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_to_nick  ON mail (to_nick)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_received ON mail (received)')
        self.db.commit()

    def _build_quote_where(self, channel, author=None, year=None, word=None):
        query = 'channel=?'
        params = (channel,)

        if year is not None:
            time_tuple = year_to_timestamps(year)
            if time_tuple is None:
                return None
            query += ' AND time BETWEEN ? AND ?'
            params += time_tuple

        if author is not None:
            author = normalize_nick(author, self.aliases)
            query += ' AND author=?'
            params += (author,)

        if word is not None:
            word = escape_sql_like(word.lower())
            query += ' AND message LIKE ? ESCAPE ?'
            params += ('%' + word + '%', '\\')

        # let's hide some stuff
        if channel == '#garachat':
            query += ' AND time NOT BETWEEN ? AND ?'
            params += (1407110400, 1410393599)  # 2014-08-04 - 2014-09-10

        return query, params

    def add_quote(self, channel, timestamp, author, message, commit=True):
        raw_author = author
        author = normalize_nick(author, self.aliases)
        message = message.rstrip()  # remove trailing whitespace from message
        word_count = len(message.split())

        if timestamp == 0 or len(author) == 0 or author in self.ignore_nicks:
            return False

        self.db.execute('INSERT OR IGNORE INTO channels (channel, seq_id) VALUES (?, ?)', (channel, 0))
        seq_id, = self.db.execute('SELECT seq_id FROM channels WHERE channel=?', (channel,)).fetchone()
        seq_id += 1  # increment by 1; the id stored in the sequence table will always be the last one used

        self.db.execute('UPDATE channels SET seq_id=? WHERE channel=?', (seq_id, channel))
        self.db.execute('INSERT INTO quotes_full (channel, seq_id, time, author, raw_author, message, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (channel, seq_id, timestamp, author, raw_author, message, word_count))

        if word_count >= 5:
            self.db.execute('INSERT INTO quotes (channel, seq_id, time, author, message) VALUES (?, ?, ?, ?, ?)',
                            (channel, seq_id, timestamp, author, message))

        if commit:
            self.db.commit()

        return True  # return true if the quote was added

    def quote_context(self, channel, seq_id, lines=20):
        rows = self.db.execute('SELECT time, raw_author, message FROM quotes_full WHERE channel=? AND seq_id BETWEEN ? AND ? ORDER BY seq_id ASC',
                               (channel, seq_id - lines, seq_id + lines)).fetchall()
        messages = []
        for row in rows:
            timestamp, author, message = row
            timestamp_formatted = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
            messages.append('%s <%s> %s' % (timestamp_formatted, author, message))
        return messages

    def random_quote(self, channel, author=None, year=None, word=None, add_author_info=True):
        num_rows = self.quote_count(channel, author, year, word)

        if num_rows == 0:
            return None

        random_skip = random.randint(0, num_rows - 1)
        where, params = self._build_quote_where(channel, author, year, word)
        query = 'SELECT seq_id, time, author, message FROM quotes WHERE %s LIMIT 1 OFFSET %i' % (where, random_skip)

        cursor = self.db.cursor()
        cursor.execute(query, params)

        (seq_id, timestamp, author, message) = cursor.fetchone()
        date = datetime.utcfromtimestamp(timestamp).strftime('%b %d %Y')

        return '%s -- %s, %s (%i)' % (message, author, date, seq_id) if add_author_info else message

    def quote_count(self, channel, author=None, year=None, word=None):
        where, params = self._build_quote_where(channel, author, year, word)
        query = 'SELECT COUNT(*) FROM quotes WHERE %s' % where

        cursor = self.db.cursor()
        cursor.execute(query, params)
        (count,) = cursor.fetchone()

        return int(count)

    def quote_top(self, channel, size=5, year=None, word=None):
        where, params = self._build_quote_where(channel, None, year, word)
        query = 'SELECT author, COUNT(*) AS c FROM quotes WHERE %s ' \
                'GROUP BY author HAVING c>0 ORDER BY c DESC LIMIT %i' % (where, size)

        cursor = self.db.cursor()
        cursor.execute(query, params)
        return ['%s: %i quotes' % (a, c) for a, c in cursor.fetchall()]

    def quote_top_percent(self, channel, size=5, year=None, word=None):
        where, params = self._build_quote_where(channel, None, year, word)
        where_total, params_total = self._build_quote_where(channel)
        query = 'SELECT author, matching, total, ' \
                'CAST(matching AS REAL) / total * 100 AS ratio ' \
                'FROM (' \
                '  SELECT author, ' \
                '  SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS matching, ' \
                '  SUM(CASE WHEN %s THEN 1 ELSE 0 END) AS total ' \
                '  FROM quotes GROUP BY author ' \
                '  HAVING matching>0 AND total>0 AND total>=500' \
                ') ' \
                'ORDER BY ratio DESC LIMIT %i' % (where, where_total, size)

        cursor = self.db.cursor()
        cursor.execute(query, params + params_total)
        return ['%s: %g%% (%i/%i)' % (a, r, c, t) for a, c, t, r in cursor.fetchall()]

    def set_current_time(self, nick, utc_offset):
        try:
            utc_offset = clamp(-12, int(utc_offset), 12)
        except:
            return 'wrong format :('

        nick = normalize_nick(nick, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('INSERT OR IGNORE INTO nicks (nick) VALUES (?)', (nick,))
        cursor.execute('UPDATE nicks SET utc_offset=? WHERE nick=?', (utc_offset, nick))
        self.db.commit()

        return 'ok :)'

    def current_time(self, nick):
        normalized_nick = normalize_nick(nick, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('SELECT utc_offset FROM nicks WHERE nick=?', (normalized_nick,))
        row = cursor.fetchone()

        if row is None or row[0] is None:
            return 'no timezone found for %s :(' % nick

        offset = row[0]
        utc_offset_str = '+%i' % offset if offset >= 0 else str(offset)
        tz = timezone(timedelta(hours=offset))

        return 'it\'s %s for %s (utc%s)' % (datetime.now(tz).strftime('%I:%M %p'), nick, utc_offset_str)

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

    def mail_send(self, from_, to, message):
        from_ = normalize_nick(from_, self.aliases)
        to = normalize_nick(to, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('INSERT INTO mail (from_nick, to_nick, message, received, sent_at, received_at) VALUES (?, ?, ?, ?, ?, ?)',
                       (from_, to, message, False, int(datetime.utcnow().timestamp()), None))
        self.db.commit()

    def mail_unsend(self, from_, id):
        cursor = self.db.cursor()
        cursor.execute('DELETE FROM mail WHERE from_nick=? AND id=?', (from_, id))
        self.db.commit()
        return cursor.rowcount > 0

    def mail_outbox(self, from_):
        from_ = normalize_nick(from_, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('SELECT id, to_nick, message FROM mail WHERE from_nick=? AND received=? ORDER BY id', (from_, False))
        return ['%i: (%s) %s' % (id, to, msg) for id, to, msg in cursor.fetchall()]

    def mail_unread_messages(self, to):
        to = normalize_nick(to, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('SELECT from_nick, message, sent_at FROM mail WHERE to_nick=? AND received=? ORDER BY sent_at ASC', (to, False))

        messages = ['%s -- %s, %s' % (msg, from_, datetime.utcfromtimestamp(sent).strftime('%Y-%m-%d %H:%M:%S'))
                    for from_, msg, sent in cursor.fetchall()]

        now = int(datetime.utcnow().timestamp())
        cursor.execute('UPDATE mail SET received=?, received_at=? WHERE to_nick=? AND received=?', (True, now, to, False))
        self.db.commit()

        return messages

    def mail_unread_receivers(self):
        cursor = self.db.cursor()
        cursor.execute('SELECT DISTINCT to_nick FROM mail WHERE received=?', (False,))
        return [nick for (nick,) in cursor.fetchall()]

    def import_irssi_log(self, filename, channel, utc_offset=0):
        utc_offset_padded = ('+' if utc_offset >= 0 else '') + str(utc_offset).zfill(2 if utc_offset >= 0 else 3) + '00'
        lines = 0
        messages = 0
        imported = 0
        skipped = 0
        log_date = datetime.utcfromtimestamp(0)

        with open(filename, 'r', encoding='utf-8') as log:
            for line in log:
                lines += 1

                if lines % 20000 == 0:
                    self.db.commit()  # commit every 20000 lines for performance
                    print('processing line %i' % lines)

                line = line.strip()
                date_match = re.match(r'^--- Day changed .{3} (\w{3}) (\d{2}) (\d{4})$', line)
                date_match2 = re.match(r'^--- Log opened .{3} (\w{3}) (\d{2}) .{8} (\d{4})$', line)
                date_match = date_match if date_match is not None else date_match2

                if date_match is not None:
                    date_str = '%s %s %s %s' % (date_match.group(1), date_match.group(2), date_match.group(3), utc_offset_padded)
                    log_date = datetime.strptime(date_str, '%b %d %Y %z')
                    continue

                match = re.match(r'^(\d\d):(\d\d)\s<.(.+?)>\s(.+)$', line)  # 12:34 <&author> message

                if match is None:
                    continue

                messages += 1
                log_time = log_date.replace(hour=int(match.group(1)), minute=int(match.group(2)))
                timestamp = int(log_time.astimezone(timezone.utc).timestamp())
                author = match.group(3)
                message = match.group(4)

                if self.add_quote(channel, timestamp, author, message, False):
                    imported += 1
                else:
                    skipped += 1

        self.db.commit()  # do a final commit if some insertions were left over
        print('Imported %i messages' % imported)
        print('Skipped %i messages' % skipped)
        print('%i messages total' % messages)
        print('%i lines total' % lines)

    def import_hexchat_log(self, filename, channel, utc_offset=0):
        utc_offset_padded = ('+' if utc_offset >= 0 else '') + str(utc_offset).zfill(2 if utc_offset >= 0 else 3) + '00'
        lines = 0
        messages = 0
        imported = 0
        skipped = 0
        year = 1970

        with open(filename, 'r', encoding='utf-8') as log:
            for line in log:
                lines += 1

                if lines % 20000 == 0:
                    self.db.commit()  # commit every 20000 lines for performance
                    print('processing line %i' % lines)

                line = line.strip()
                year_match = re.match(r'^\*\*\*\* BEGIN LOGGING AT .* (\d{4})$', line)

                if year_match is not None:
                    year = int(year_match.group(1))
                    continue

                match = re.match(r'^(.{15})\s<(.+?)>\s(.+)$', line)  # jan 01 12:34:56 <author> message

                if match is None:
                    continue

                messages += 1
                log_time_tz = '%s %i %s' % (match.group(1), year, utc_offset_padded)
                log_time = datetime.strptime(log_time_tz, '%b %d %X %Y %z')
                timestamp = int(log_time.astimezone(timezone.utc).timestamp())
                author = match.group(2)
                message = match.group(3)

                if self.add_quote(channel, timestamp, author, message, False):
                    imported += 1
                else:
                    skipped += 1

        self.db.commit()  # do a final commit if some insertions were left over
        print('Imported %i messages' % imported)
        print('Skipped %i messages' % skipped)
        print('%i messages total' % messages)
        print('%i lines total' % lines)

    def dump_irssi_log_authors(self, filename):
        authors = {}

        with open(filename, 'r', encoding='utf-8') as log:
            for line in log:
                match = re.match(r'^(\d\d):(\d\d)\s<.(.+?)>\s(.+)$', line)

                if match is None:
                    continue

                author = normalize_nick(match.group(3), self.aliases)

                if author not in authors.keys():
                    authors[author] = 0
                authors[author] += 1

        return authors

    def close(self):
        self.db.close()


if __name__ == '__main__':
    with open('nda.conf', 'r') as f:
        conf = json.load(f)
        q = Database('nda.db', conf.get('aliases', {}), conf.get('ignore_nicks', []))
        # for (nick, msg_count) in sorted(q.dump_irssi_log_authors('gclogs/#garachat-master.log').items(), key=lambda x: x[1], reverse=True):
        #     if nick not in q.aliases.keys():
        #         print('%s %i' % (nick, msg_count))
        # q.add_quote('#garachat', 0, 'ashin', '( ͡° ͜ʖ ͡°)')
        # q.import_irssi_log('gclogs/#garachat-master.log', '#garachat', 0)
        print(q.quote_top(channel='#garachat', size=5))
        print(q.random_quote(channel='#garachat', author='ashin', year=2010))
        print(q.quote_count(channel='#garachat', author='sarah'))
        print(q.random_quote(channel='#garachat', author='duo', word='fuck you guys'))
        print(q.quote_top_percent(channel='#garachat', year=None, word='cup'))
        print(q.quote_context(channel='#garachat', seq_id=183047))

        q.close()
