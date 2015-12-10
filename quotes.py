import sqlite3
import re
import json
import random
import sys
from datetime import datetime, timezone


class Quotes:
    db_name = 'quotes.db'

    def __init__(self, channels, conf_file='quotes.conf'):
        with open(conf_file, 'r', encoding='utf-8') as file:
            conf = json.load(file)
            self.ignore_nicks = conf['ignore']
            self.aliases = conf['aliases']

        self.db = sqlite3.connect(self.db_name)

        for channel in channels:
            self._create_table(channel)

    def _table_name(self, channel):
        return channel.replace('#', '', 1).strip()

    def _create_table(self, channel):
        table_name = self._table_name(channel)
        cursor = self.db.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER, author TEXT, message TEXT, word_count INTEGER)' % table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON %s (time)' % table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_author ON %s (author)' % table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_word_count ON %s (word_count)' % table_name)
        self.db.commit()

    def _normalize_nick(self, nick):
        nick = nick.lower().strip('_ ') # try to normalize nicks to lowercase versions and no alts

        for (master, aliases) in self.aliases.items():
            if nick == master or nick in aliases:
                return master

        return nick

    def _year_to_timestamps(self, year):
        if year is None:
            return 0, sys.maxsize
        elif year not in range(1970, datetime.utcnow().year + 1):
            return None

        time_min = int(datetime(year, 1, 1, 0, 0, 0).timestamp())
        time_max = int(datetime(year, 12, 31, 23, 59, 59).timestamp())
        return time_min, time_max

    def add_quote(self, channel, timestamp, author, message, commit=True):
        author = self._normalize_nick(author)
        message = message.rstrip()  # remove trailing whitespace from message
        word_count = len(message.split())

        if timestamp == 0 or len(author) == 0 or len(message) == 0 or author in self.ignore_nicks or word_count < 5:
            return False

        cursor = self.db.cursor()
        cursor.execute('INSERT INTO %s (time, author, message, word_count) VALUES (?, ?, ?, ?)'
                       % self._table_name(channel), (timestamp, author, message, word_count))

        if commit:
            self.db.commit()

        return True  # return true if the quote was added

    def random_quote(self, channel, author=None, year=None):
        time_tuple = self._year_to_timestamps(year)
        num_rows = self.quote_count(channel, author, year)

        if time_tuple is None or num_rows == 0:
            return None

        random_skip = random.randint(0, num_rows - 1)
        params = time_tuple
        query = 'SELECT time, author, message FROM %s WHERE time>=? AND time<=?' % self._table_name(channel)

        if author is not None:
            author = self._normalize_nick(author)
            query += ' AND author=?'
            params += (author,)

        query += ' LIMIT 1 OFFSET %i' % random_skip

        cursor = self.db.cursor()
        cursor.execute(query, params)

        (timestamp, author, message) = cursor.fetchone()
        date = datetime.utcfromtimestamp(timestamp).strftime('%b %d %Y')

        return '%s -- %s, %s' % (message, author, date)

    def quote_count(self, channel, author=None, year=None):
        time_tuple = self._year_to_timestamps(year)

        if time_tuple is None:
            return 0

        query = 'SELECT COUNT(*) FROM %s WHERE time>=? AND time<=?' % self._table_name(channel)
        params = time_tuple

        if author is not None:
            author = self._normalize_nick(author)
            query += ' AND author=?'
            params += (author,)

        cursor = self.db.cursor()
        cursor.execute(query, params)
        (count,) = cursor.fetchone()

        return int(count)

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

                if lines % 5000 == 0:
                    self.db.commit()  # commit every 5000 lines for performance
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
                    print('Skipped message: <%s> %s' % (author, message))
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

                author = self._normalize_nick(match.group(3))

                if author not in authors.keys():
                    authors[author] = 0
                authors[author] += 1

        return authors

    def close(self):
        self.db.close()


if __name__ == '__main__':
    q = Quotes(['#garachat'])
    #for (nick, msg_count) in sorted(q.dump_irssi_log_authors('gclogs/#garachat-master.log').items(), key=lambda x: x[1], reverse=True):
    #    if nick not in q.aliases.keys():
    #        print('%s %i' % (nick, msg_count))
    #q.add_quote('#garachat', 0, 'ashin', '( ͡° ͜ʖ ͡°)')
    #q.import_irssi_log('gclogs/#garachat-master.log', '#garachat', 0)
    print(q.random_quote(channel='#garachat', author='ashin', year=2010))
    print(q.quote_count(channel='#garachat', author='sarah'))
    q.close()
