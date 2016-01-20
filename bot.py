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
from idle_talk import IdleTalk
from quotes import SqliteQuotes
from maze import Maze
from rpg.main import RPG
from mail import Mail


class IRCError(Exception):
    pass


class Channel:
    def __init__(self, name):
        self.name = name
        self.idle_talk = IdleTalk()
        self.game = Maze()
        self.rpg = RPG(name)


class Bot:
    buffer_size = 4096
    receive_timeout = 0.5
    ping_timeout = 180
    passive_interval = 60  # how long between performing passive, input independent operations like mail
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
            self.trusted_nicks = conf.get('trusted_nicks', [])
            self.quit_message = conf.get('quit_message', '')
            self.logging = conf.get('logging', False)
            link_lookup.youtube_api_key = conf.get('youtube_api_key', None)
        self.irc = None
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.connect_time = None
        self.last_ping = None
        self.waiting_for_pong = False
        self.last_passive = None
        self.quotes = None
        self.mail = None

    def _send(self, msg):
        if not msg.endswith(self.crlf):
            msg += self.crlf
        self.irc.send(msg.encode('utf-8'))

    def _send_message(self, to, msg):
        if msg is None or len(msg) == 0:
            return

        msg = msg.strip(self.crlf)
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
        messages = self.mail.unread_messages(to)
        if len(messages) > 0:
            self._send_message(to, 'you have %i unread message(s)' % len(messages))
            self._send_messages(to, messages)

    def _log(self, msg):
        msg = '%s %s' % (datetime.datetime.utcnow(), msg)
        print(msg)

        if self.logging:
            with open('bot.log', 'a', encoding='utf-8') as f:
                f.write('%s%s' % (msg, self.crlf))

    def _readline(self):
        if len(self.lines) > 0:
            return self.lines.pop(0)  # if any lines are already read, return them in sequence

        ready, _, _ = select.select([self.irc], [], [], self.receive_timeout)

        if len(ready) == 0:  # if no lines and nothing received, return None
            return None

        buffer = self.irc.recv(self.buffer_size)
        data = self.unfinished_line + buffer.decode('utf-8')  # prepend unfinished line to its continuation
        lines = data.split(self.crlf)

        # if buffer ended on newline, the last element will be empty string
        # otherwise, the last element will be an unfinished line
        # if no newlines found in buffer, the entire buffer is an unfinished line (line longer than what recv returned)
        self.unfinished_line = lines.pop(-1)
        self.lines = lines

        return self._readline()  # recurse until a finished line is found or nothing is received within timeout

    def _connect(self):
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
        self.quotes.close()
        self.mail.close()

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

        # check if any nicks with unread messages have come online
        unread_receivers = self.mail.unread_receivers()
        if len(unread_receivers) > 0:
            self._ison(unread_receivers)

        # check if it's time to talk
        for channel in self.channels:
            if channel.idle_talk.can_talk() and False:
                self._send_message(channel.name, channel.idle_talk.generate_message())

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
                self.mail.update_last_seen(source_nick)

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
        tokens = message.split()
        _, _, raw_args = message.partition(' ')

        if len(tokens) == 0:
            return  # don't process empty or whitespace-only messages

        if message.startswith(' '):
            tokens[0] = ' ' + tokens[0]  # any initial space is removed by str.split(), so we put it back here

        # explicit commands
        handled = self._explicit_command(tokens[0], tokens[1:] if len(tokens) > 1 else [], reply_target, source_nick, raw_args)

        if not handled:
            # implicit commands
            self._implicit_command(message, reply_target, source_nick)

            for channel in self.channels:
                if reply_target == channel.name:
                    channel.idle_talk.add_message(message)  # add message to the idle talk log
                    timestamp = int(datetime.datetime.utcnow().timestamp())
                    self.quotes.add_quote(channel.name, timestamp, source_nick, message)  # add message to the quotes database

    def _explicit_command(self, command, args, reply_target, source_nick, raw_args):
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
            if reply_target not in [c.name for c in self.channels]:  # only allow quote requests in a channel
                self._send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            random_quote = self.quotes.random_quote(reply_target, author, year, word)
            self._send_message(reply_target, random_quote if random_quote is not None else 'no quotes found :(')

        def quote_count():
            if reply_target not in [c.name for c in self.channels]:
                self._send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            count = self.quotes.quote_count(reply_target, author, year, word)
            self._send_message(reply_target, '%i quotes' % count)

        def quote_top():
            if reply_target not in [c.name for c in self.channels]:
                self._send_message(reply_target, 'command only available in channel :(')
                return

            author, year, word = parse_quote_command()
            top = self.quotes.top(reply_target, 5, year, word)
            if len(top) > 0:
                self._send_messages(reply_target, top)
            else:
                self._send_message(reply_target, 'no quotes found :(')

        def update():
            if source_nick not in self.trusted_nicks:
                self._send_message(reply_target, 'how about no >:(')
                return

            if shell.git_pull():
                self._disconnect()
                time.sleep(5)  # give the server time to process disconnection to prevent nick collision
                shell.restart(__file__)
            else:
                self._send_message(reply_target, 'pull failed, manual update required :(')

        def shell_command():
            if source_nick in self.trusted_nicks:
                output = shell.run(' '.join(args))
                self._send_messages(reply_target, output)

        def rpg_action():
            for channel in self.channels:
                if reply_target == channel.name:  # only allow rpg play in channel
                    self._send_messages(reply_target, channel.rpg.action(' '.join(args)))

        def send_mail():
            if len(args) < 2:
                return
            self.mail.send(source_nick, args[0], ' '.join(args[1:]))
            self._send_message(source_nick, 'message sent to %s :)' % args[0])

        def unsend_mail():
            if len(args) < 1:
                return
            try:
                id = int(args[0])
                success = self.mail.unsend(source_nick, id)
                self._send_message(source_nick, 'message %i unsent :)' % id if success else 'message %i wasn\'t found :(')
            except ValueError:
                pass

        def outbox():
            messages = self.mail.outbox(source_nick)
            if len(messages) == 0:
                self._send_message(source_nick, 'no unsent messages')
            else:
                self._send_messages(source_nick, messages)

        def help():
            self._send_messages(source_nick, [
                '!help: this message',
                '!hi: say hi',
                '!imgur: random imgur link',
                '!reddit: random reddit link',
                '!porn: random porn link + longest comment',
                '!quote [NICK] [YEAR] [?SEARCH]: get a random quote and optionally filter by nick, year or search string. Search string can be enclosed in quotes (?"") to allow spaces',
                '!quotecount [NICK] [YEAR] [?SEARCH]: same as !quote, but get total number of matches instead',
                '!quotetop [YEAR] [?SEARCH]: get the top 5 nicks by number of quotes',
                '!seen NICK: when did the bot last see NICK?',
                '!send NICK MESSAGE: deliver MESSAGE to NICK once it\'s online',
                '!outbox: see your messages that haven\'t been delivered yet',
                '!unsend ID: cancel delivery of message with the specified id (listed by !outbox)',
                '!isitmovienight: is it movie night?',
                '!uptime: time since coming online',
                '!rpg [ACTION]: play the GOTY right here'
            ])

        command = command.lower()
        commands = {
            '!help': help,
            '!hi': lambda: self._send_message(reply_target, 'hi %s, jag heter %s, %s heter jag' % (source_nick, self.nicks[self.nick_index], self.nicks[self.nick_index])),
            '!imgur': lambda: self._send_message(reply_target, link_generator.imgur_link()),
            '!reddit': lambda: self._send_message(reply_target, link_generator.reddit_link()),
            '!uptime': uptime,
            '!porn': porn,
            '!quote': quote,
            '!quotecount': quote_count,
            '!quotetop': quote_top,
            '!update': update,
            '!isitmovienight': lambda: self._send_message(reply_target, 'maybe :)' if datetime.datetime.utcnow().weekday() in [4, 5] else 'no :('),
            '!rpg': rpg_action,
            '!send': send_mail,
            '!unsend': unsend_mail,
            '!outbox': outbox,
            '!seen': lambda: self._send_message(reply_target, self.mail.last_seen(args[0])) if len(args) > 0 else None,
            # '!shell': shell_command,
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
            title = link_lookup.youtube_lookup(message)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)  # 0x02 == control character for bold text

        def generic_lookup():
            title = link_lookup.generic_lookup(message)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)

        def convert_units():
            converted = unit_converter.convert_unit(message)
            if converted is not None:
                value, unit = converted
                self._send_message(reply_target, '^^ %.2f %s' % (value, unit))

        matched = False
        matchers = [
            ((lambda: link_lookup.contains_youtube(message)), youtube_lookup),
            ((lambda: link_lookup.contains_link(message) and not matched), generic_lookup),  # skip if youtube link already matched
            ((lambda: unit_converter.contains_unit(message) and False), convert_units)
        ]

        for matcher, func in matchers:
            if matcher():
                func()
                matched = True

        return matched

    def _main_loop(self):
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.quotes = SqliteQuotes()
        self.mail = Mail()

        self._connect()
        while True:
            self._receive()

    def start(self):
        while True:  # keep trying to run the main loop even after errors occur
            try:
                self._main_loop()
            except IRCError as irc_error:
                self._log('IRC error: %s' % irc_error.args)
                self._disconnect()
                time.sleep(5)
            except OSError as os_error:
                self._log('OS error (errno %i): %s' % (os_error.errno, os_error.strerror))
                time.sleep(5)
            except KeyboardInterrupt:
                self._disconnect()
                break
            except Exception as error:
                self._log('Unknown error (%s): %s' % (str(type(error)), error.args))
                self._log(traceback.format_exc())


if __name__ == '__main__':
    bot = Bot('bot.conf')
    bot.start()
