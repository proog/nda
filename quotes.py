import sqlite3
import re
from datetime import datetime, timezone


class Quotes:
    db_name = 'quotes.db'
    imported_authors = {}
    ignore_nicks = ['nda_monitor7']
    nick_map = {
        'mashin': 'ashin',
        'udo': 'duo',
        'gc_iu': 'duo',
        'ui': 'duo',
        'chewey': 'krabboss',
        'chewey2': 'krabboss',
        'gravalanch': 'krabboss',
        'sole': 'solefolia',
        'sfl': 'solefolia',
        'lenneth': 'solefolia',
        'cassie': 'solefolia',
        'sole`': 'solefolia',
        'spookfolia': 'solefolia',
        'gara': 'garamond',
        'iworkatjunes': 'garamond',
        'junes': 'garamond',
        'junesphone': 'garamond',
        'proogphone': 'proog',
        'sprook': 'proog',
        'alfonso': 'proog',
        '|seth|': 'seth',
        'sethphone': 'seth',
        'sethp': 'seth',
        'lod': 'seth',
        'loddite': 'seth',
        'seths': 'seth',
        'sk4nker': 'skanker',
        'spookanker': 'skanker',
        'ebi': 'ebichu',
        'ivan_lap': 'ivan',
        'ivan_pc': 'ivan',
        'ivy': 'ivan',
        'alpoop': 'alpott'
    }

    def __init__(self, channel):
        self.db = sqlite3.connect(self.db_name)
        self.table_name = channel.replace('#', '').strip()
        cursor = self.db.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS %s (id INTEGER PRIMARY KEY AUTOINCREMENT, time INTEGER, author TEXT, message TEXT)' % self.table_name)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_author ON %s (author)' % self.table_name)
        self.db.commit()

    def add_quote(self, timestamp, author, message, commit=True):
        author = author.lower().strip('_ ')  # try to normalize nicks to lowercase versions and no alts
        message = message.rstrip()  # remove trailing whitespace from message

        if timestamp == 0 or len(author) == 0 or len(message) == 0 or author in self.ignore_nicks:
            return False

        if author in self.nick_map.keys():
            author = self.nick_map[author]
        else:
            if author not in self.imported_authors.keys():
                self.imported_authors[author] = 0
            self.imported_authors[author] += 1

        cursor = self.db.cursor()
        cursor.execute('INSERT INTO %s (time, author, message) VALUES (?, ?, ?)' % self.table_name, (timestamp, author, message))

        if commit:
            self.db.commit()

        return True  # return true if the quote was added

    def random_quote(self, author=None):
        cursor = self.db.cursor()

        if author is None:
            cursor.execute('SELECT time, author, message FROM %s ORDER BY RANDOM() LIMIT 1' % self.table_name)
        else:
            author = author.lower()
            cursor.execute('SELECT time, author, message FROM %s WHERE author=? ORDER BY RANDOM() LIMIT 1' % self.table_name, (author,))

        row = cursor.fetchone()

        if row is not None:
            date = datetime.utcfromtimestamp(row[0]).strftime('%b %d %Y')
            author = row[1]
            message = row[2]
            return '%s   -- %s, %s' % (message, author, date)

        return 'no quotes found :(' if author is None else 'no quotes found for %s :(' % author

    def import_log(self, filename, utc_offset=0):
        utc_offset_padded = ('+' if utc_offset >= 0 else '') + str(utc_offset).zfill(2 if utc_offset >= 0 else 3) + '00'
        lines = 0
        messages = 0
        imported = 0
        skipped = 0
        year = 1970

        with open(filename, 'r', encoding='utf-8') as log:
            for line in log:
                lines += 1

                if lines % 5000 == 0:
                    self.db.commit()  # commit every 5000 lines for performance
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

                if self.add_quote(timestamp, author, message, False):
                    imported += 1
                else:
                    skipped += 1

        self.db.commit()  # do a final commit if some insertions were left over
        print('Imported %i messages' % imported)
        print('Skipped %i messages' % skipped)
        print('%i messages total' % messages)
        print('%i lines total' % lines)

    def close(self):
        self.db.close()


if __name__ == '__main__':
    q = Quotes('#garachat')
    #q.add_quote(0, 'ashin', '( ͡° ͜ʖ ͡°)')
    q.import_log('SynIRC-#garachat.log', 1)
    for (nick, messages) in sorted(q.imported_authors.items(), key=lambda x: x[1], reverse=True):
        print('%s %i' % (nick, messages))
    #print(q.random_quote('duo'))
    q.close()
