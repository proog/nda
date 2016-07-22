#!/usr/bin/env python3

import time
import json
import link_generator
import link_lookup
import unit_converter
import shell
import re
import greetings
import sqlite3
import random
import redis
from datetime import datetime
from irc import IRC
from idle_talk import IdleTimer
from database import Database
from maze import Maze
from rpg.main import RPG
from twitter import Twitter
from util import clamp, is_channel


class Channel:
    history_max_len = 50

    def __init__(self, name):
        self.name = name
        self.idle_timer = IdleTimer()
        self.game = Maze()
        self.rpg = RPG(name)
        self.history = []

    def add_history(self, description, detail):
        self.history.append((description, detail))

        if len(self.history) > self.history_max_len:
            self.history = self.history[-self.history_max_len:]

    def get_history(self, last=1):
        return self.history[-last:]


class NDA(IRC):
    passive_interval = 60  # how long between performing passive, input independent operations like mail
    admin_duration = 30    # how long an admin session is active after authenticating with !su
    redis_in_prefix = 'ndain:'
    redis_out_prefix = 'ndaout:'

    def __init__(self, conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            conf = json.load(f)
        address = conf['address']
        port = conf.get('port', 6667)
        user = conf['user']
        real_name = conf['real_name']
        nicks = conf['nicks']
        ns_password = conf.get('nickserv_password', None)
        logging = conf.get('logging', False)
        super().__init__(address, port, user, real_name, nicks, ns_password, logging)

        self.channels = [Channel(c) for c in conf['channels']]
        self.admin_password = conf.get('admin_password', '')
        self.idle_talk = conf.get('idle_talk', False)
        self.auto_tweet_regex = conf.get('auto_tweet_regex', None)
        self.youtube_api_key = conf.get('youtube_api_key', None)
        self.pastebin_api_key = conf.get('pastebin_api_key', None)
        self.reddit_consumer_key = conf.get('reddit_consumer_key', None)
        self.reddit_consumer_secret = conf.get('reddit_consumer_secret', None)
        self.admin_sessions = {}
        self.last_passive = datetime.min

        aliases = conf.get('aliases', {})
        ignore_nicks = conf.get('ignore_nicks', [])
        self.database = Database('nda.db', aliases, ignore_nicks)

        tw_consumer_key = conf.get('twitter_consumer_key', None)
        tw_consumer_secret = conf.get('twitter_consumer_secret', None)
        tw_access_token = conf.get('twitter_access_token', None)
        tw_access_secret = conf.get('twitter_access_token_secret', None)
        self.twitter = Twitter(tw_consumer_key, tw_consumer_secret, tw_access_token, tw_access_secret)

        use_redis = conf.get('use_redis', False)
        self.redis, self.redis_sub = None, None

        if use_redis:
            try:
                self.redis = redis.StrictRedis()
                self.redis_sub = self.redis.pubsub(ignore_subscribe_messages=True)
                self.redis_sub.psubscribe('%s*' % self.redis_in_prefix)
            except:
                self.log('Couldn\'t connect to redis, disabling redis support')
                self.redis, self.redis_sub = None, None

    def unknown_error_occurred(self, error):
        for channel in self.channels:
            self.send_message(channel.name, 'tell proog that a %s occurred :\'(' % str(type(error)))

    def stopped(self):
        self.database.close()
        if self.redis_sub is not None:
            self.redis_sub.close()

    def connected(self):
        self.admin_sessions = {}
        self.last_passive = datetime.utcnow()

        for channel in self.channels:
            self._join(channel.name)

    def message_sent(self, to, message):
        # redis logging
        if self.redis is not None:
            self.redis.publish('%s%s' % (self.redis_out_prefix, to), message)

        # add own message to the quotes database
        if self.get_channel(to) is not None:
            timestamp = int(datetime.utcnow().timestamp())
            self.database.add_quote(to, timestamp, self.current_nick(), message, full_only=True)

    def main_loop_iteration(self):
        # check for external input
        self.redis_input()

        # perform various passive operations if the interval is up
        if (datetime.utcnow() - self.last_passive).total_seconds() < self.passive_interval:
            return

        # check if any nicks with unread messages have come online (disabled for now)
        # unread_receivers = self.database.mail_unread_receivers()
        # if len(unread_receivers) > 0:
        #     self._ison(unread_receivers)

        # check if it's time to talk
        if self.idle_talk:
            for channel in self.channels:
                if channel.idle_timer.can_talk():
                    seq_id = 0
                    quote = self.database.random_quote(channel=channel.name, stringify=False)
                    if quote is not None:
                        message, author, date, seq_id = quote
                        self.send_message(channel.name, message)
                    channel.add_history('idle talk', 'seq_id=%i, i=%i, d=%i'
                                        % (seq_id, channel.idle_timer.interval, channel.idle_timer.delay))
                    channel.idle_timer.message_sent()  # notify idle timer that we sent something, even with no quote

        # check if it's time for a festive greeting
        for channel_name, greeting in greetings.greet():
            channel = self.get_channel(channel_name)
            if channel is not None:
                self.send_message(channel_name, greeting)
                channel.add_history('greeting', greeting)

        self.last_passive = datetime.utcnow()

    def nick_seen(self, nick):
        self.database.update_last_seen(nick)

    def ison_result(self, nicks):
        for nick in nicks:
            self.process_mail(nick)

    def nick_joined(self, nick):
        self.process_mail(nick)

    def message_received(self, message, reply_target, source_nick):
        channel = self.get_channel(reply_target)
        tokens = message.split()
        _, _, raw_args = message.partition(' ')

        # redis logging
        if self.redis is not None:
            self.redis.publish('%s%s' % (self.redis_out_prefix, reply_target), message)

        if len(tokens) == 0:
            return  # don't process empty or whitespace-only messages

        if message.startswith(' '):
            tokens[0] = ' ' + tokens[0]  # any initial space is removed by str.split(), so we put it back here

        # explicit commands
        command = tokens[0]
        args = tokens[1:] if len(tokens) > 1 else []
        handled = self.explicit_command(command, args, reply_target, source_nick, raw_args)

        if channel is not None:
            channel.idle_timer.message_received()  # notify idle timer that someone talked
            timestamp = int(datetime.utcnow().timestamp())
            self.database.add_quote(channel.name, timestamp, source_nick, message, full_only=handled)  # add message to the quotes database

        # implicit commands
        if not handled:
            self.implicit_command(message, reply_target, source_nick)

    def explicit_command(self, command, args, reply_target, source_nick, raw_args):
        channel = self.get_channel(reply_target)

        def parse_quote_command():
            author = None
            year = None
            search = ''
            raw_args_nosearch = raw_args

            multiword_match = re.search(r'\?"(.*)"', raw_args)
            singleword_match = re.search(r'\?([^\s]+)', raw_args)

            if multiword_match is not None:
                search = multiword_match.group(1)
                raw_args_nosearch = raw_args.replace('?"' + search + '"', '')
            elif singleword_match is not None:
                search = singleword_match.group(1)
                raw_args_nosearch = raw_args.replace('?' + search, '')

            for arg in raw_args_nosearch.split():
                if re.match(r'^\d{4}$', arg) is not None:
                    year = int(arg)
                else:
                    author = arg

            return author, year, search if len(search) > 0 else None

        def admin(func):
            if self.is_admin(source_nick):
                func()
            else:
                self.send_message(reply_target, 'how about no >:(')

        def uptime():
            connect_time = self.connect_time.strftime('%Y-%m-%d %H:%M:%S')
            uptime_str = str(datetime.utcnow() - self.connect_time)
            self.send_message(reply_target, 'connected on %s, %s ago' % (connect_time, uptime_str))

        def porn():
            link = link_generator.xhamster_link()
            self.send_message(reply_target, link)
            if link.startswith('http://'):
                comment = link_lookup.xhamster_comment(link)
                self.send_message(reply_target, comment)

        def quote():
            if channel is None:  # only allow quote requests in a channel
                self.send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            random_quote = self.database.random_quote(reply_target, author, year, word)
            self.send_message(reply_target, random_quote if random_quote is not None else 'no quotes found :(')
            channel.add_history('quote', 'a=%s, y=%s, w=%s' % (author, year, word))

        def quote_id():
            if channel is None:  # only allow quote requests in a channel
                self.send_message(reply_target, 'command only available in channel :(')
                return
            if len(args) < 1:
                self.send_message(reply_target, 'missing sequence id :(')
                return

            try:
                seq_id = int(args[0])
            except ValueError:
                self.send_message(reply_target, 'bad sequence id :(')
                return

            quote = self.database.quote_by_seq_id(reply_target, seq_id)
            self.send_message(reply_target, quote if quote is not None else 'quote not found :(')

        def quote_count():
            if channel is None:
                self.send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            count = self.database.quote_count(reply_target, author, year, word)
            self.send_message(reply_target, '%i quotes' % count)
            channel.add_history('quote count', 'a=%s, y=%s, w=%s' % (author, year, word))

        def quote_top(percent=False):
            if channel is None:
                self.send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            func = self.database.quote_top_percent if percent else self.database.quote_top
            top = func(reply_target, 5, year, word)
            channel.add_history('quote top', 'y=%s, w=%s, pct=%s' % (year, word, percent))
            if len(top) > 0:
                self.send_messages(reply_target, top)
            else:
                self.send_message(reply_target, 'no quotes found :(')

        def quote_context():
            if channel is None:
                self.send_message(reply_target, 'command only available in channel :(')
                return

            if len(args) < 1:
                self.send_message(reply_target, 'missing sequence id :(')
                return

            try:
                seq_id = int(args[0])
            except ValueError:
                self.send_message(reply_target, 'bad sequence id :(')
                return

            lines = 20
            if len(args) > 1:
                try:
                    lines = clamp(0, int(args[1]), 100)
                except ValueError:
                    pass

            context = self.database.quote_context(reply_target, seq_id, lines)

            if len(context) == 0:
                self.send_message(reply_target, 'no context found :(')
                return

            link = link_generator.make_pastebin('\r\n'.join(context), self.pastebin_api_key)
            self.send_message(reply_target, link if link is not None else 'couldn\'t upload to pastebin :(')

        def update():
            if shell.git_pull():
                self._disconnect('if i\'m not back in a few seconds, something is wrong')
                time.sleep(2)  # give the server time to process disconnection to prevent nick collision
                shell.restart(__file__)
            else:
                self.send_message(reply_target, 'pull failed, manual update required :(')

        def shell_command():
            output = shell.run(' '.join(args))
            self.send_messages(reply_target, output)

        def rpg_action():
            if channel is None:  # only allow rpg play in channel
                self.send_message(reply_target, 'command only available in channel :(')
                return
            self.send_messages(reply_target, channel.rpg.action(' '.join(args)))

        def send_mail():
            if len(args) < 2:
                return
            to = args[0]
            msg = ' '.join(args[1:])
            self.database.mail_send(source_nick, to, msg)
            self.send_message(source_nick, 'message sent to %s :)' % to)

        def unsend_mail():
            if len(args) < 1:
                return
            try:
                id = int(args[0])
                success = self.database.mail_unsend(source_nick, id)
                self.send_message(source_nick, 'message %i unsent :)' % id if success else 'message %i wasn\'t found :(')
            except ValueError:
                pass

        def outbox():
            messages = self.database.mail_outbox(source_nick)
            if len(messages) == 0:
                self.send_message(source_nick, 'no unsent messages')
            else:
                self.send_messages(source_nick, messages)

        def tweet():
            if len(raw_args) > 140:
                self.send_message(reply_target, 'tweet too long (%i characters) :(' % len(raw_args))
                return

            if self.twitter.tweet(raw_args):
                self.send_message(reply_target, 'sent :)')
            else:
                delay = self.twitter.next_tweet_delay()
                reason = 'in %i seconds' % delay if delay > 0 else 'now, but something went wrong'
                self.send_message(reply_target, 'not sent (next tweet available %s) :(' % reason)

        def su():
            if raw_args == self.admin_password:
                self.admin_sessions[source_nick] = datetime.utcnow()
                self.send_message(source_nick, 'you are now authenticated for %i seconds' % self.admin_duration)
            else:
                self.send_message(source_nick, 'how about no >:(')

        def die():
            raise KeyboardInterrupt

        def penis():
            link = link_generator.penis_link(self.reddit_consumer_key, self.reddit_consumer_secret)
            self.send_message(reply_target, link if link is not None else 'couldn\'t grab a dick for you, sorry :(')

        def set_time():
            if len(args) > 0:
                self.send_message(reply_target, self.database.set_current_time(source_nick, args[0]))
            else:
                self.send_message(reply_target, 'missing utc offset :(')

        def get_time():
            if len(args) > 0:
                self.send_message(reply_target, self.database.current_time(args[0]))
            else:
                self.send_message(reply_target, 'missing nick :(')

        def history():
            history_channel = self.get_channel(args[0]) if len(args) > 0 else channel

            if history_channel is None:
                self.send_message(reply_target, 'channel not found, please specify #channel :(')
                return

            recent = history_channel.get_history(3)
            if len(recent) == 0:
                self.send_message(reply_target, 'No history yet :(')
                return
            self.send_messages(reply_target, ['%s: %s' % entry for entry in recent])

        def help():
            self.send_messages(source_nick, [
                '!context ID [NUM_LINES]: pastebin context for a quote, optionally with number of lines (default is 20)',
                '!imgur: random imgur link',
                '!isitmovienight: is it movie night?',
                '!penis: random penis',
                '!porn: random porn link + longest comment',
                '!quote [NICK] [YEAR] [?SEARCH]: get a random quote and optionally filter by nick, year or search string. Search string can be enclosed in quotes (?"") to allow spaces',
                '!quotecount [NICK] [YEAR] [?SEARCH]: same as !quote, but get total number of matches instead',
                '!quotetop [YEAR] [?SEARCH]: get the top 5 nicks by number of quotes',
                '!quotetopp [YEAR] [?SEARCH]: same as !quotetop, but use matching:total ratio instead of number of quotes',
                '!reddit: random reddit link',
                '!rpg [ACTION]: play the GOTY right here',
                '!seen NICK: when did the bot last see NICK?',
                '!settime UTC_OFFSET: set your timezone',
                '!time NICK: get current time and timezone for NICK',
                '!tweet MESSAGE: send MESSAGE as tweet',
                '!wikihow: random wikihow article',
                # '!send NICK MESSAGE: deliver MESSAGE to NICK once it\'s online',
                # '!outbox: see your messages that haven\'t been delivered yet',
                # '!unsend ID: cancel delivery of message with the specified id (listed by !outbox)',
            ])

        command = command.lower()
        commands = {
            '!context': quote_context,
            '!die': lambda: admin(die),
            '!help': help,
            '!hi': lambda: self.send_message(reply_target, 'hi %s, jag heter %s, %s heter jag' % (source_nick, self.current_nick(), self.current_nick())),
            '!history': history,
            '!imgur': lambda: self.send_message(reply_target, link_generator.imgur_link()),
            '!isitmovienight': lambda: self.send_message(reply_target, 'maybe :)' if datetime.utcnow().weekday() in [4, 5] else 'no :('),
            '!penis': penis,
            '!porn': porn,
            '!quote': quote,
            '!quotecount': quote_count,
            '!quoteid': quote_id,
            '!quotetop': quote_top,
            '!quotetopp': lambda: quote_top(True),
            '!reddit': lambda: self.send_message(reply_target, link_generator.reddit_link()),
            '!rpg': rpg_action,
            '!seen': lambda: self.send_message(reply_target, self.database.last_seen(args[0])) if len(args) > 0 else None,
            '!settime': set_time,
            '!su': su,
            '!time': get_time,
            '!tweet': tweet,
            '!update': lambda: admin(update),
            '!uptime': uptime,
            '!wikihow': lambda: self.send_message(reply_target, link_generator.wikihow_link()),
            # '!send': send_mail,
            # '!unsend': unsend_mail,
            # '!outbox': outbox,
            # '!shell': lambda: admin(shell_command),
            # '!up': lambda: self._send_multiline_message(reply_target, self.game.up()),
            # '!down': lambda: self._send_multiline_message(reply_target, self.game.down()),
            # '!left': lambda: self._send_multiline_message(reply_target, self.game.left()),
            # '!right': lambda: self._send_multiline_message(reply_target, self.game.right()),
            # '!look': lambda: self._send_multiline_message(reply_target, self.game.look()),
            # '!restart': lambda: self._send_multiline_message(reply_target, self.game.restart())
        }

        if command in commands:
            commands[command]()
            return True

        return False

    def implicit_command(self, message, reply_target, source_nick):
        def youtube_lookup():
            title = link_lookup.youtube_lookup(message, self.youtube_api_key)
            if title is not None:
                self.send_message(reply_target, '^^ \x02%s\x02' % title)  # 0x02 == control character for bold text

        def twitter_lookup():
            title = link_lookup.twitter_lookup(message, self.twitter)
            if title is not None:
                self.send_message(reply_target, '^^ \x02%s\x02' % title)

        def generic_lookup():
            title = link_lookup.generic_lookup(message)
            if title is not None:
                self.send_message(reply_target, '^^ \x02%s\x02' % title)

        def convert_units():
            converted = unit_converter.convert_unit(message)
            if converted is not None:
                value, unit = converted
                self.send_message(reply_target, '^^ %.2f %s' % (value, unit))

        def tweet_trigger():
            m = message.lower()
            return self.auto_tweet_regex is not None \
                and len(m) in range(40, 141) \
                and re.search(self.auto_tweet_regex, m) is not None

        def undertale():
            db = sqlite3.connect('ndrtl.db')
            count, = db.execute('SELECT COUNT(*) FROM undertale').fetchone()
            if count > 0:
                msg, = db.execute('SELECT message FROM undertale WHERE id=?', (random.randint(1, count),)).fetchone()
                self.send_message(reply_target, msg)
            db.close()

        matched = False
        matchers = [
            ((lambda: link_lookup.contains_youtube(message)), youtube_lookup),
            ((lambda: link_lookup.contains_twitter(message)), twitter_lookup),
            ((lambda: link_lookup.contains_link(message) and not matched), generic_lookup),  # skip if specific link already matched
            ((lambda: 'undertale' in message.lower()), undertale),
            (tweet_trigger, lambda: self.twitter.tweet(message)),
            # ((lambda: unit_converter.contains_unit(message)), convert_units)
        ]

        for matcher, func in matchers:
            if matcher():
                func()
                matched = True

        return matched

    def get_channel(self, name):
        for channel in self.channels:
            if name == channel.name:
                return channel
        return None

    def is_admin(self, nick):
        return nick in self.admin_sessions and \
               (datetime.utcnow() - self.admin_sessions[nick]).total_seconds() < self.admin_duration

    def process_mail(self, to):
        messages = self.database.mail_unread_messages(to)
        if len(messages) > 0:
            self.send_message(to, 'you have %i unread message(s)' % len(messages))
            self.send_messages(to, messages)

    def redis_input(self):
        while self.redis_sub is not None:
            try:
                d = self.redis_sub.get_message()
            except:
                self.log('Error getting message from redis, disabling redis support')
                self.redis, self.redis_sub = None, None
                return

            if d is None:
                break
            if d['type'] != 'pmessage':
                continue

            to = d['channel'].decode().split(self.redis_in_prefix, 1)[1]
            msg = d['data'].decode()
            valid_target = self.get_channel(to) is not None if is_channel(to) else len(to) > 0

            if valid_target and len(msg) > 0:
                self.log('redis message: %s to %s' % (msg, to))
                self.send_message(to, msg)


if __name__ == '__main__':
    nda = NDA('nda.conf')
    nda.start()
