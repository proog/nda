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
from datetime import datetime
from irc import IRC
from idle_talk import IdleTimer
from database import Database
from maze import Maze
from rpg.main import RPG
from twitter import Twitter
from util import clamp


class Channel:
    def __init__(self, name):
        self.name = name
        self.idle_timer = IdleTimer()
        self.game = Maze()
        self.rpg = RPG(name)


class NDA(IRC):
    passive_interval = 60  # how long between performing passive, input independent operations like mail
    admin_duration = 30    # how long an admin session is active after authenticating with !su

    def __init__(self, conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            conf = json.load(f)
            address = conf['address']
            port = conf.get('port', 6667)
            user = conf['user']
            nicks = conf['nicks']
            real_name = conf['real_name']
            nickserv_password = conf.get('nickserv_password', None)
            logging = conf.get('logging', False)
            self.channels = [Channel(c) for c in conf['channels']]
            self.admin_password = conf.get('admin_password', '')
            self.idle_talk = conf.get('idle_talk', False)
            self.auto_tweet_regex = conf.get('auto_tweet_regex', None)
            self.youtube_api_key = conf.get('youtube_api_key', None)
            self.pastebin_api_key = conf.get('pastebin_api_key', None)
            self.twitter_consumer_key = conf.get('twitter_consumer_key', None)
            self.twitter_consumer_secret = conf.get('twitter_consumer_secret', None)
            self.twitter_access_token = conf.get('twitter_access_token', None)
            self.twitter_access_token_secret = conf.get('twitter_access_token_secret', None)
            self.reddit_consumer_key = conf.get('reddit_consumer_key', None)
            self.reddit_consumer_secret = conf.get('reddit_consumer_secret', None)
            self.aliases = conf.get('aliases', {})
            self.ignore_nicks = conf.get('ignore_nicks', [])
        self.admin_sessions = {}
        self.last_passive = datetime.min
        self.database = None
        self.twitter = None

        super().__init__(address, port, user, real_name, nicks, nickserv_password, logging)

    def unknown_error_occurred(self, error):
        for channel in self.channels:
            self.send_message(channel.name, 'tell proog that a %s occurred :\'(' % str(type(error)))

    def started(self):
        self.database = Database('nda.db', self.aliases, self.ignore_nicks)
        self.twitter = Twitter(self.twitter_consumer_key, self.twitter_consumer_secret, self.twitter_access_token, self.twitter_access_token_secret)

    def stopped(self):
        self.database.close()

    def connected(self):
        self.admin_sessions = {}
        self.last_passive = datetime.utcnow()

        for channel in self.channels:
            self._join(channel.name)

    def message_sent(self, to, message):
        # add own message to the quotes database
        if self.get_channel(to) is not None:
            timestamp = int(datetime.utcnow().timestamp())
            self.database.add_quote(to, timestamp, self.current_nick(), message, full_only=True)

    def main_loop_iteration(self):
        now = datetime.utcnow()

        # perform various passive operations if the interval is up
        if (now - self.last_passive).total_seconds() < self.passive_interval:
            return

        # check if any nicks with unread messages have come online (disabled for now)
        # unread_receivers = self.database.mail_unread_receivers()
        # if len(unread_receivers) > 0:
        #     self._ison(unread_receivers)

        # check if it's time to talk
        if self.idle_talk:
            for channel in self.channels:
                if channel.idle_timer.can_talk():
                    channel.idle_timer.message_sent()  # notify idle timer that we sent something, even with no quote
                    quote = self.database.random_quote(channel=channel.name, add_author_info=False)
                    if quote is not None:
                        self.send_message(channel.name, quote)

        # check if it's time for a festive greeting
        for channel_name, greeting in greetings.greet():
            if channel_name in [c.name for c in self.channels]:
                self.send_message(channel_name, greeting)

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

        def quote_top(percent=False):
            if channel is None:
                self.send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            func = self.database.quote_top_percent if percent else self.database.quote_top
            top = func(reply_target, 5, year, word)
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
                time.sleep(5)  # give the server time to process disconnection to prevent nick collision
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
            self.database.mail_send(source_nick, args[0], ' '.join(args[1:]))
            self.send_message(source_nick, 'message sent to %s :)' % args[0])

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


if __name__ == '__main__':
    nda = NDA('nda.conf')
    nda.start()
