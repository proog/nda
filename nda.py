#!/usr/bin/env python3

import socket
import select
import time
import datetime
import json
import link_generator
import link_lookup
import unit_converter
import shell
import re
import traceback
import greetings
import sqlite3
import random
from idle_talk import IdleTimer
from database import Database
from maze import Maze
from rpg.main import RPG
from twitter import Twitter
from util import clamp


class IRCError(Exception):
    pass


class Channel:
    def __init__(self, name):
        self.name = name
        self.idle_timer = IdleTimer()
        self.game = Maze()
        self.rpg = RPG(name)


class NDA:
    buffer_size = 4096
    receive_timeout = 0.5
    ping_timeout = 180
    passive_interval = 60  # how long between performing passive, input independent operations like mail
    admin_duration = 30
    crlf = '\r\n'

    def __init__(self, conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            conf = json.load(f)
            self.address = conf['address']
            self.port = conf.get('port', 6667)
            self.user = conf['user']
            self.nicks = conf['nicks']
            self.real_name = conf['real_name']
            self.channels = [Channel(c) for c in conf['channels']]
            self.nickserv_password = conf.get('nickserv_password', None)
            self.admin_password = conf.get('admin_password', '')
            self.quit_message = conf.get('quit_message', '')
            self.logging = conf.get('logging', False)
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
        self.irc = None
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.admin_sessions = {}
        self.connect_time = None
        self.last_ping = None
        self.waiting_for_pong = False
        self.last_passive = None
        self.database = None
        self.twitter = None

    def _get_channel(self, name):
        for channel in self.channels:
            if name == channel.name:
                return channel
        return None

    def _is_admin(self, nick):
        return nick in self.admin_sessions and \
               (datetime.datetime.utcnow() - self.admin_sessions[nick]).total_seconds() < self.admin_duration

    def _send(self, msg):
        if not msg.endswith(self.crlf):
            msg += self.crlf
        self.irc.send(msg.encode('utf-8'))

    def _send_message(self, to, msg):
        if msg is None or len(msg) == 0:
            return

        msg = msg.replace(self.crlf, '\n').replace('\n', ' ').strip()
        self._log('Sending %s to %s' % (msg, to))
        command = 'PRIVMSG %s :' % to

        # irc max line length is 512, but server -> other clients will tack on a :source, so let's be conservative
        chunk_size = 512 - len(command + self.crlf) - 100
        chunks = [msg[i:i + chunk_size] for i in range(0, len(msg), chunk_size)]

        for chunk in chunks:
            self._send(command + chunk + self.crlf)

    def _send_messages(self, to, msgs):
        for msg in msgs:
            self._send_message(to, msg)

    def _ping(self, msg):
        self._log('Sending PING :%s' % msg)
        self._send('PING :%s' % msg)

    def _pong(self, msg):
        self._log('Sending PONG :%s' % msg)
        self._send('PONG :%s' % msg)

    def _change_nick(self, nick):
        self._log('Sending NICK %s' % nick)
        self._send('NICK %s' % nick)

    def _join(self, channel):
        self._log('Sending JOIN %s' % channel)
        self._send('JOIN %s' % channel)

    def _ison(self, nicks):
        nicks_str = ' '.join(nicks)
        self._log('Sending ISON %s' % nicks_str)
        self._send('ISON %s' % nicks_str)

    def _process_mail(self, to):
        messages = self.database.mail_unread_messages(to)
        if len(messages) > 0:
            self._send_message(to, 'you have %i unread message(s)' % len(messages))
            self._send_messages(to, messages)

    def _log(self, msg):
        msg = '%s %s' % (datetime.datetime.utcnow(), msg)
        print(msg)

        if self.logging:
            with open('nda.log', 'a', encoding='utf-8') as f:
                f.write('%s%s' % (msg, self.crlf))

    def _readline(self):
        if len(self.lines) > 0:
            return self.lines.pop(0)  # if any lines are already read, return them in sequence

        ready, _, _ = select.select([self.irc], [], [], self.receive_timeout)

        if len(ready) == 0:  # if no lines and nothing received, return None
            return None

        buffer = self.irc.recv(self.buffer_size)
        data = self.unfinished_line + buffer.decode('utf-8', errors='ignore')  # prepend unfinished line to its continuation
        lines = data.split(self.crlf)

        # if buffer ended on newline, the last element will be empty string
        # otherwise, the last element will be an unfinished line
        # if no newlines found in buffer, the entire buffer is an unfinished line (line longer than what recv returned)
        self.unfinished_line = lines.pop(-1)
        self.lines = lines

        return self._readline()  # recurse until a finished line is found or nothing is received within timeout

    def _connect(self):
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.admin_sessions = {}

        self._log('Connecting to %s:%s' % (self.address, self.port))
        self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect((self.address, self.port))
        self.connect_time = datetime.datetime.utcnow()
        self.waiting_for_pong = False
        self.last_ping = datetime.datetime.utcnow()
        self.last_passive = datetime.datetime.utcnow()
        self._send('USER %s 8 * :%s' % (self.user, self.real_name))
        self._change_nick(self.nicks[self.nick_index])

    def _disconnect(self):
        self._log('Disconnecting from %s:%s' % (self.address, self.port))
        self.database.close()

        try:
            self._send('QUIT :%s' % self.quit_message)
            self.irc.close()
        except OSError as os_error:
            self._log('An error occurred while disconnecting (%i): %s' % (os_error.errno, os_error.strerror))

    def _execute_passive(self):
        now = datetime.datetime.utcnow()

        # if we don't receive a pong within the timeout, something strange happened and we want to reconnect
        if self.waiting_for_pong and (now - self.last_ping).total_seconds() > self.ping_timeout:
            raise IRCError('No PONG received from the server in %i seconds' % self.ping_timeout)

        # perform various passive operations if the interval is up
        if (now - self.last_passive).total_seconds() < self.passive_interval:
            return

        # ping the server
        if not self.waiting_for_pong:
            self._ping('nda')
            self.waiting_for_pong = True
            self.last_ping = datetime.datetime.utcnow()

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
                        self._send_message(channel.name, quote)

        # check if it's time for a festive greeting
        for channel_name, greeting in greetings.greet():
            if channel_name in [c.name for c in self.channels]:
                self._send_message(channel_name, greeting)

        self.last_passive = datetime.datetime.utcnow()

    def _receive(self):
        line = self._readline()  # a line or None if nothing received
        self._execute_passive()  # execute passive operations independent of input

        if line is None:
            return

        data = line.split()
        self._log(line)

        if len(data) < 2:  # smallest message we want is PING :msg
            return

        if not data[0].startswith(':'):  # distinguish between message formats
            command = data[0]

            if command == 'PING':
                self._pong(' '.join(data[1:]).lstrip(':'))
            elif command == 'ERROR':
                raise IRCError(line)
        else:
            source = data[0].lstrip(':')
            source_nick = source.split('!')[0]
            command = data[1]

            if '!' in source and source_nick not in self.nicks:  # update last seen whenever anything happens from some nick
                self.database.update_last_seen(source_nick)

            if command == '001':  # RPL_WELCOME: successful client registration
                if self.nickserv_password is not None and len(self.nickserv_password) > 0:
                    self._send_message('NickServ', 'IDENTIFY %s' % self.nickserv_password)

                for channel in self.channels:
                    self._join(channel.name)
            elif command == '303':  # RPL_ISON: list of online nicks, process mail here
                for nick in ' '.join(data[3:]).lstrip(':').split():
                    self._process_mail(nick)
            elif command == '433':  # ERR_NICKNAMEINUSE: nick already taken
                self.nick_index += 1
                if self.nick_index >= len(self.nicks):
                    self._log('Error: all nicks already in use')
                    raise KeyboardInterrupt
                self._change_nick(self.nicks[self.nick_index])
            elif command == 'PONG':
                self.waiting_for_pong = False
            elif command == 'KICK':
                time.sleep(2)
                self._join(data[2])
            elif command == 'JOIN':  # process mail as soon as the user joins instead of after passive_interval seconds
                if source_nick not in self.nicks:  # disregard own joins
                    self._process_mail(source_nick)
            elif command == 'PRIVMSG':
                target = data[2]
                reply_target = target if target in [c.name for c in self.channels] else source_nick  # channel or direct message
                message = ' '.join(data[3:]).lstrip(':')
                self._parse_message(message, reply_target, source_nick)

    def _parse_message(self, message, reply_target, source_nick):
        channel = self._get_channel(reply_target)
        tokens = message.split()
        _, _, raw_args = message.partition(' ')

        if len(tokens) == 0:
            return  # don't process empty or whitespace-only messages

        if message.startswith(' '):
            tokens[0] = ' ' + tokens[0]  # any initial space is removed by str.split(), so we put it back here

        # explicit commands
        command = tokens[0]
        args = tokens[1:] if len(tokens) > 1 else []
        handled = self._explicit_command(command, args, reply_target, source_nick, raw_args)

        if channel is not None:
            channel.idle_timer.message_received()  # notify idle timer that someone talked

        if not handled:
            # implicit commands
            self._implicit_command(message, reply_target, source_nick)

            if channel is not None:
                timestamp = int(datetime.datetime.utcnow().timestamp())
                self.database.add_quote(channel.name, timestamp, source_nick, message)  # add message to the quotes database

    def _explicit_command(self, command, args, reply_target, source_nick, raw_args):
        channel = self._get_channel(reply_target)

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
            if self._is_admin(source_nick):
                func()
            else:
                self._send_message(reply_target, 'how about no >:(')

        def uptime():
            connect_time = self.connect_time.strftime('%Y-%m-%d %H:%M:%S')
            uptime_str = str(datetime.datetime.utcnow() - self.connect_time)
            self._send_message(reply_target, 'connected on %s, %s ago' % (connect_time, uptime_str))

        def porn():
            link = link_generator.xhamster_link()
            self._send_message(reply_target, link)
            if link.startswith('http://'):
                comment = link_lookup.xhamster_comment(link)
                self._send_message(reply_target, comment)

        def quote():
            if channel is None:  # only allow quote requests in a channel
                self._send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            random_quote = self.database.random_quote(reply_target, author, year, word)
            self._send_message(reply_target, random_quote if random_quote is not None else 'no quotes found :(')

        def quote_count():
            if channel is None:
                self._send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            count = self.database.quote_count(reply_target, author, year, word)
            self._send_message(reply_target, '%i quotes' % count)

        def quote_top(percent=False):
            if channel is None:
                self._send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            func = self.database.quote_top_percent if percent else self.database.quote_top
            top = func(reply_target, 5, year, word)
            if len(top) > 0:
                self._send_messages(reply_target, top)
            else:
                self._send_message(reply_target, 'no quotes found :(')

        def quote_context():
            if channel is None:
                self._send_message(reply_target, 'command only available in channel :(')
                return

            if len(args) < 1:
                self._send_message(reply_target, 'missing sequence id :(')
                return

            try:
                seq_id = int(args[0])
            except ValueError:
                self._send_message(reply_target, 'bad sequence id :(')
                return

            lines = 20
            if len(args) > 1:
                try:
                    lines = clamp(0, int(args[1]), 100)
                except ValueError:
                    pass

            context = self.database.quote_context(reply_target, seq_id, lines)

            if len(context) == 0:
                self._send_message(reply_target, 'no context found :(')
                return

            link = link_generator.make_pastebin('\r\n'.join(context), self.pastebin_api_key)
            self._send_message(reply_target, link if link is not None else 'couldn\'t upload to pastebin :(')

        def update():
            if shell.git_pull():
                self._disconnect()
                time.sleep(5)  # give the server time to process disconnection to prevent nick collision
                shell.restart(__file__)
            else:
                self._send_message(reply_target, 'pull failed, manual update required :(')

        def shell_command():
            output = shell.run(' '.join(args))
            self._send_messages(reply_target, output)

        def rpg_action():
            if channel is None:  # only allow rpg play in channel
                self._send_message(reply_target, 'command only available in channel :(')
                return
            self._send_messages(reply_target, channel.rpg.action(' '.join(args)))

        def send_mail():
            if len(args) < 2:
                return
            self.database.mail_send(source_nick, args[0], ' '.join(args[1:]))
            self._send_message(source_nick, 'message sent to %s :)' % args[0])

        def unsend_mail():
            if len(args) < 1:
                return
            try:
                id = int(args[0])
                success = self.database.mail_unsend(source_nick, id)
                self._send_message(source_nick, 'message %i unsent :)' % id if success else 'message %i wasn\'t found :(')
            except ValueError:
                pass

        def outbox():
            messages = self.database.mail_outbox(source_nick)
            if len(messages) == 0:
                self._send_message(source_nick, 'no unsent messages')
            else:
                self._send_messages(source_nick, messages)

        def tweet():
            if len(raw_args) > 140:
                self._send_message(reply_target, 'tweet too long (%i characters) :(' % len(raw_args))
                return

            if self.twitter.tweet(raw_args):
                self._send_message(reply_target, 'sent :)')
            else:
                delay = self.twitter.next_tweet_delay()
                reason = 'in %i seconds' % delay if delay > 0 else 'now, but something went wrong'
                self._send_message(reply_target, 'not sent (next tweet available %s) :(' % reason)

        def su():
            if raw_args == self.admin_password:
                self.admin_sessions[source_nick] = datetime.datetime.utcnow()
                self._send_message(source_nick, 'you are now authenticated for %i seconds' % self.admin_duration)
            else:
                self._send_message(source_nick, 'how about no >:(')

        def die():
            raise KeyboardInterrupt

        def penis():
            link = link_generator.penis_link(self.reddit_consumer_key, self.reddit_consumer_secret)
            self._send_message(reply_target, link if link is not None else 'couldn\'t grab a dick for you, sorry :(')

        def set_time():
            if len(args) > 0:
                self._send_message(reply_target, self.database.set_current_time(source_nick, args[0]))
            else:
                self._send_message(reply_target, 'missing utc offset :(')

        def get_time():
            if len(args) > 0:
                self._send_message(reply_target, self.database.current_time(args[0]))
            else:
                self._send_message(reply_target, 'missing nick :(')

        def help():
            self._send_messages(source_nick, [
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
            '!hi': lambda: self._send_message(reply_target, 'hi %s, jag heter %s, %s heter jag' % (source_nick, self.nicks[self.nick_index], self.nicks[self.nick_index])),
            '!imgur': lambda: self._send_message(reply_target, link_generator.imgur_link()),
            '!isitmovienight': lambda: self._send_message(reply_target, 'maybe :)' if datetime.datetime.utcnow().weekday() in [4, 5] else 'no :('),
            '!penis': penis,
            '!porn': porn,
            '!quote': quote,
            '!quotecount': quote_count,
            '!quotetop': quote_top,
            '!quotetopp': lambda: quote_top(True),
            '!reddit': lambda: self._send_message(reply_target, link_generator.reddit_link()),
            '!rpg': rpg_action,
            '!seen': lambda: self._send_message(reply_target, self.database.last_seen(args[0])) if len(args) > 0 else None,
            '!settime': set_time,
            '!su': su,
            '!time': get_time,
            '!tweet': tweet,
            '!update': lambda: admin(update),
            '!uptime': uptime,
            '!wikihow': lambda: self._send_message(reply_target, link_generator.wikihow_link()),
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

    def _implicit_command(self, message, reply_target, source_nick):
        def youtube_lookup():
            title = link_lookup.youtube_lookup(message, self.youtube_api_key)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)  # 0x02 == control character for bold text

        def twitter_lookup():
            title = link_lookup.twitter_lookup(message, self.twitter)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)

        def generic_lookup():
            title = link_lookup.generic_lookup(message)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)

        def convert_units():
            converted = unit_converter.convert_unit(message)
            if converted is not None:
                value, unit = converted
                self._send_message(reply_target, '^^ %.2f %s' % (value, unit))

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
                self._send_message(reply_target, msg)
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

    def _main_loop(self):
        while True:
            try:
                self._receive()
            except IRCError as irc_error:
                self._log('IRC error: %s' % irc_error.args)
                self._disconnect()
                time.sleep(5)
                self._connect()
            except OSError as os_error:
                self._log('OS error (errno %i): %s' % (os_error.errno, os_error.strerror))
                self._disconnect()
                time.sleep(5)
                self._connect()
            except KeyboardInterrupt:
                self._disconnect()
                break
            except Exception as error:
                self._log('Unknown error (%s): %s' % (str(type(error)), error.args))
                self._log(traceback.format_exc())
                for channel in self.channels:
                    self._send_message(channel.name, 'tell proog that a %s occurred :\'(' % str(type(error)))

    def start(self):
        self.database = Database('nda.db', self.aliases, self.ignore_nicks)
        self.twitter = Twitter(self.twitter_consumer_key, self.twitter_consumer_secret, self.twitter_access_token, self.twitter_access_token_secret)

        self._connect()
        self._main_loop()


if __name__ == '__main__':
    nda = NDA('nda.conf')
    nda.start()
