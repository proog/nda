import sqlite3
import re
import json
import random
import sys
from datetime import datetime, timezone, timedelta


def normalize_nick(nick, aliases_map):
    nick = nick.lower().strip('_ ')  # try to normalize nicks to lowercase versions and no alts

    for (master, aliases) in aliases_map.items():
        if nick == master or nick in aliases:
            return master

    return nick


def year_to_timestamps(year):
    if year is None:
        return 0, sys.maxsize
    elif year not in range(1970, datetime.utcnow().year + 1):
        return None

    time_min = int(datetime(year, 1, 1, 0, 0, 0).timestamp())
    time_max = int(datetime(year, 12, 31, 23, 59, 59).timestamp())
    return time_min, time_max


class SqliteQuotes:
    def __init__(self, aliases=None, conf_file='quotes.conf'):
        self.db_name = 'quotes.db'
        self.eager_word_count = True
        self.aliases = aliases if aliases is not None else {}

        with open(conf_file, 'r', encoding='utf-8') as file:
            conf = json.load(file)
            self.ignore_nicks = conf.get('ignore', [])

        self.db = sqlite3.connect(self.db_name)
        self.db.execute('CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, time INTEGER, author TEXT, message TEXT, word_count INTEGER)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_channel ON quotes (channel)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_time ON quotes (time)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_author ON quotes (author)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_message ON quotes (message)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_word_count ON quotes (word_count)')
        self.db.execute('CREATE TABLE IF NOT EXISTS timezones (id INTEGER PRIMARY KEY AUTOINCREMENT, author TEXT, utc_offset INTEGER)')
        self.db.execute('CREATE INDEX IF NOT EXISTS idx_author ON timezones (author)')
        self.db.commit()

    def _escape_like(self, word):
        for char in ['\\', '%', '_']:
            word = word.replace(char, '\\' + char)
        return word

    def _build_where(self, channel, author=None, year=None, word=None):
        query = 'channel=?'
        params = (channel,)

        if not self.eager_word_count:
            query += ' AND word_count>=?'
            params += (5,)

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
            word = self._escape_like(word.lower())
            query += ' AND message LIKE ? ESCAPE ?'
            params += ('%' + word + '%', '\\')

        # let's hide some stuff
        if channel == '#garachat':
            query += ' AND time NOT BETWEEN ? AND ?'
            params += (1407110400, 1410393599)  # 2014-08-04 - 2014-09-10

        return query, params

    def add_quote(self, channel, timestamp, author, message, commit=True):
        author = normalize_nick(author, self.aliases)
        message = message.rstrip()  # remove trailing whitespace from message
        word_count = len(message.split())

        if timestamp == 0 or len(author) == 0 or (self.eager_word_count and word_count < 5) or author in self.ignore_nicks:
            return False

        cursor = self.db.cursor()
        cursor.execute('INSERT INTO quotes (channel, time, author, message, word_count) VALUES (?, ?, ?, ?, ?)',
                       (channel, timestamp, author, message, word_count))

        if commit:
            self.db.commit()

        return True  # return true if the quote was added

    def random_quote(self, channel, author=None, year=None, word=None, add_author_info=True):
        num_rows = self.quote_count(channel, author, year, word)

        if num_rows == 0:
            return None

        random_skip = random.randint(0, num_rows - 1)
        where, params = self._build_where(channel, author, year, word)
        query = 'SELECT time, author, message FROM quotes WHERE %s LIMIT 1 OFFSET %i' % (where, random_skip)

        cursor = self.db.cursor()
        cursor.execute(query, params)

        (timestamp, author, message) = cursor.fetchone()
        date = datetime.utcfromtimestamp(timestamp).strftime('%b %d %Y')

        return '%s -- %s, %s' % (message, author, date) if add_author_info else message

    def quote_count(self, channel, author=None, year=None, word=None):
        where, params = self._build_where(channel, author, year, word)
        query = 'SELECT COUNT(*) FROM quotes WHERE %s' % where

        cursor = self.db.cursor()
        cursor.execute(query, params)
        (count,) = cursor.fetchone()

        return int(count)

    def top(self, channel, size=5, year=None, word=None):
        where, params = self._build_where(channel, None, year, word)
        query = 'SELECT author, COUNT(*) AS c FROM quotes WHERE %s ' \
                'GROUP BY author HAVING c>0 ORDER BY c DESC LIMIT %i' % (where, size)

        cursor = self.db.cursor()
        cursor.execute(query, params)
        return ['%s: %i quotes' % (a, c) for a, c in cursor.fetchall()]

    def top_percent(self, channel, size=5, year=None, word=None):
        where, params = self._build_where(channel, None, year, word)
        where_total, params_total = self._build_where(channel)
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

    def set_time(self, author, utc_offset):
        try:
            utc_offset = min(max(int(utc_offset), -12), 12)
        except:
            return 'wrong format :('

        author = normalize_nick(author, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('DELETE FROM timezones WHERE author=?', (author,))
        cursor.execute('INSERT INTO timezones (author, utc_offset) VALUES (?, ?)', (author, utc_offset))
        self.db.commit()

        return 'ok :)'

    def get_time(self, author):
        normalized_author = normalize_nick(author, self.aliases)
        cursor = self.db.cursor()
        cursor.execute('SELECT utc_offset FROM timezones WHERE author=?', (normalized_author,))
        row = cursor.fetchone()

        if row is None:
            return 'no timezone found for %s :(' % author

        offset, = row
        utc_offset_str = '+%i' % offset if offset >= 0 else str(offset)
        tz = timezone(timedelta(hours=offset))

        return 'it\'s %s for %s (utc%s)' % (datetime.now(tz).strftime('%I:%M %p'), author, utc_offset_str)

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
    q = SqliteQuotes()
    #for (nick, msg_count) in sorted(q.dump_irssi_log_authors('gclogs/#garachat-master.log').items(), key=lambda x: x[1], reverse=True):
    #    if nick not in q.aliases.keys():
    #        print('%s %i' % (nick, msg_count))
    #q.add_quote('#garachat', 0, 'ashin', '( ͡° ͜ʖ ͡°)')
    #q.import_irssi_log('gclogs/#garachat-master.log', '#garachat', 0)
    print(q.top(channel='#garachat', size=5))
    print(q.random_quote(channel='#garachat', author='ashin', year=2010))
    print(q.quote_count(channel='#garachat', author='sarah'))
    print(q.random_quote(channel='#garachat', author='duo', word='fuck you guys'))
    print(q.top_percent(channel='#garachat', year=None, word='cup'))
    q.close()
