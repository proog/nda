import sqlite3
import re
import json
from datetime import datetime, timezone


class Quotes:
    db_name = 'quotes.db'

    def __init__(self, channel, conf_file='quotes.conf'):
        with open(conf_file, 'r', encoding='utf-8') as file:
            conf = json.load(file)
            self.ignore_nicks = conf['ignore']
            self.aliases = conf['aliases']

        self.db = sqlite3.connect(self.db_name)
        self.table_name = channel.replace('#', '').strip()
        cursor = self.db.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER, author TEXT, message TEXT, word_count INTEGER)' % self.table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_author ON %s (author)' % self.table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_word_count ON %s (word_count)' % self.table_name)
        self.db.commit()

    def normalize_nick(self, nick):
        nick = nick.lower().strip('_ ') # try to normalize nicks to lowercase versions and no alts

        for (master, aliases) in self.aliases.items():
            if nick == master or nick in aliases:
                return master

        return nick

    def add_quote(self, timestamp, author, message, commit=True):
        author = self.normalize_nick(author)
        message = message.rstrip()  # remove trailing whitespace from message
        word_count = len(message.split())

        if timestamp == 0 or len(author) == 0 or len(message) == 0 or author in self.ignore_nicks:
            return False

        cursor = self.db.cursor()
        cursor.execute('INSERT INTO %s (time, author, message, word_count) VALUES (?, ?, ?, ?)'
                       % self.table_name, (timestamp, author, message, word_count))

        if commit:
            self.db.commit()

        return True  # return true if the quote was added

    def random_quote(self, author=None):
        cursor = self.db.cursor()

        if author is None:
            cursor.execute('SELECT time, author, message FROM %s WHERE word_count > 2 ORDER BY RANDOM() LIMIT 1' % self.table_name)
        else:
            author = author.lower()
            cursor.execute('SELECT time, author, message FROM %s WHERE author=? AND word_count>? ORDER BY RANDOM() LIMIT 1' % self.table_name, (author, 2))

        row = cursor.fetchone()

        if row is not None:
            date = datetime.utcfromtimestamp(row[0]).strftime('%b %d %Y')
            author = row[1]
            message = row[2]
            return '%s -- %s, %s' % (message, author, date)

        return 'no quotes found :(' if author is None else 'no quotes found for %s :(' % author

    def import_irssi_log(self, filename, utc_offset=0):
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
                date_match = re.match(r'^--- Day changed .{3} (.+)$', line)
                date_match2 = re.match(r'^--- Log opened .{3} (\w{3}) (\d{2}) .{8} (\d{4})$', line)

                if date_match is not None:
                    date_str = '%s %s' % (date_match.group(1), utc_offset_padded)
                    log_date = datetime.strptime(date_str, '%b %d %Y %z')
                    continue
                elif date_match2 is not None:
                    date_str = '%s %s %s %s' % (date_match2.group(1), date_match2.group(2), date_match2.group(3), utc_offset_padded)
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

                if self.add_quote(timestamp, author, message, False):
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

                author = self.normalize_nick(match.group(3))

                if author not in authors.keys():
                    authors[author] = 0
                authors[author] += 1

        return authors

    def close(self):
        self.db.close()


if __name__ == '__main__':
    q = Quotes('#garachat')
    #for (nick, msg_count) in sorted(q.dump_irssi_log_authors('gclogs/#garachat-master.log').items(), key=lambda x: x[1], reverse=True):
    #    if nick not in q.aliases.keys():
    #        print('%s %i' % (nick, msg_count))
    #q.add_quote(0, 'ashin', '( ͡° ͜ʖ ͡°)')
    q.import_irssi_log('gclogs/#garachat-master.log', 0)
    #print(q.random_quote('duo'))
    q.close()
