import re
import json
import random
import sys
from pymongo import MongoClient, TEXT
from datetime import datetime, timezone


class Quotes:
    db_name = 'nda'
    collection_name = 'quotes'
    eager_word_count = False

    def __init__(self, conf_file='quotes.conf'):
        with open(conf_file, 'r', encoding='utf-8') as file:
            conf = json.load(file)
            self.ignore_nicks = conf['ignore']
            self.aliases = conf['aliases']

        self.mongo = MongoClient()
        collection = self.mongo[self.db_name][self.collection_name]
        collection.create_index('channel')
        collection.create_index('time')
        collection.create_index('author')
        collection.create_index([('message', TEXT)])
        collection.create_index('word_count')

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

    def _document(self, channel, timestamp, author, message):
        author = self._normalize_nick(author)
        message = message.rstrip()  # remove trailing whitespace from message
        word_count = len(message.split())

        if timestamp == 0 or len(author) == 0 or (self.eager_word_count and word_count < 5) or author in self.ignore_nicks:
            return None

        return {
            'channel': channel,
            'time': timestamp,
            'author': author,
            'message': message,
            'word_count': word_count
        }

    def _query(self, channel, author=None, year=None, word=None):
        query = {
            'channel': channel
        }

        if not self.eager_word_count:
            query['word_count'] = {
                '$gte': 5
            }

        if year is not None:
            time_tuple = self._year_to_timestamps(year)

            if time_tuple is None:
                return 0

            query['time'] = {
                '$gte': time_tuple[0],
                '$lte': time_tuple[1]
            }

        if author is not None:
            author = self._normalize_nick(author)
            query['author'] = author

        if word is not None:
            word = word.lower()
            query['$text'] = {
                '$search': '\"%s\"' % word
            }

        # let's hide some stuff
        if channel == '#garachat':
            query['$or'] = [{
                'time': {'$lt': 1407110400}  # 2014-08-04
            }, {
                'time': {'$gt': 1410393599}  # 2014-09-10
            }]

        return query

    def add_quote(self, channel, timestamp, author, message):
        document = self._document(channel, timestamp, author, message)

        if document is None:
            return False

        self.mongo[self.db_name][self.collection_name].insert_one(document)
        return True  # return true if the quote was added

    def random_quote(self, channel, author=None, year=None, word=None):
        num_rows = self.quote_count(channel, author, year, word)

        if num_rows == 0:
            return None

        random_skip = random.randint(0, num_rows - 1)
        query = self._query(channel, author, year, word)

        for document in self.mongo[self.db_name][self.collection_name].find(query).limit(-1).skip(random_skip):
            date = datetime.utcfromtimestamp(document['time']).strftime('%b %d %Y')
            return '%s -- %s, %s' % (document['message'], document['author'], date)

    def quote_count(self, channel, author=None, year=None, word=None):
        query = self._query(channel, author, year, word)
        return self.mongo[self.db_name][self.collection_name].find(query).count()

    def top(self, channel, size=5, year=None, word=None):
        query = self._query(channel, None, year, word)

        aggregate = self.mongo[self.db_name][self.collection_name].aggregate([{
            '$match': query
        }, {
            '$group': {
                '_id': '$author',
                'count': {'$sum': 1}
            }
        }, {
            '$sort': {'count': -1}
        }, {
            '$limit': size
        }])

        return ['%s: %i quotes' % (doc['_id'], doc['count']) for doc in aggregate if doc['count'] > 0]

    def import_irssi_log(self, filename, channel, utc_offset=0):
        utc_offset_padded = ('+' if utc_offset >= 0 else '') + str(utc_offset).zfill(2 if utc_offset >= 0 else 3) + '00'
        lines = 0
        messages = 0
        imported = 0
        skipped = 0
        log_date = datetime.utcfromtimestamp(0)
        documents = []

        def insert():
            self.mongo[self.db_name][self.collection_name].insert_many(documents)
            documents.clear()

        with open(filename, 'r', encoding='utf-8') as log:
            for line in log:
                lines += 1

                if lines % 20000 == 0:
                    insert()
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

                document = self._document(channel, timestamp, author, message)
                if document is not None:
                    imported += 1
                    documents.append(document)
                else:
                    skipped += 1

        # final insert if some were left over
        insert()

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
        documents = []

        def insert():
            self.mongo[self.db_name][self.collection_name].insert_many(documents)
            documents.clear()

        with open(filename, 'r', encoding='utf-8') as log:
            for line in log:
                lines += 1

                if lines % 20000 == 0:
                    insert()
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

                document = self._document(channel, timestamp, author, message)
                if document is not None:
                    imported += 1
                    documents.append(document)
                else:
                    skipped += 1

        # final insert if some were left over
        insert()

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
        self.mongo.close()


if __name__ == '__main__':
    q = Quotes()
    #for (nick, msg_count) in sorted(q.dump_irssi_log_authors('gclogs/#garachat-master.log').items(), key=lambda x: x[1], reverse=True):
    #    if nick not in q.aliases.keys():
    #        print('%s %i' % (nick, msg_count))
    #q.add_quote('#garachat', 0, 'ashin', '( ͡° ͜ʖ ͡°)')
    #q.import_irssi_log('gclogs/#garachat-master.log', '#garachat', 0)
    print(q.top(channel='#garachat', size=5))
    print(q.random_quote(channel='#garachat', author='ashin', year=2010))
    print(q.quote_count(channel='#garachat', author='sarah'))
    print(q.random_quote(channel='#garachat', author='duo', word='fuck you guys'))
    q.close()
