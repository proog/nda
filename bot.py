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
from idle_talk import IdleTalk
from quotes import Quotes
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
    receive_timeout = 5
    message_timeout = 180
    passive_interval = 30  # how long between performing passive, input independent operations like mail
    crlf = '\r\n'

    def __init__(self, conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            conf = json.load(f)
            self.address = conf['address']
            self.port = conf['port'] if 'port' in conf.keys() else 6667
            self.user = conf['user']
            self.nicks = conf['nicks']
            self.real_name = conf['real_name']
            self.channels = [Channel(c) for c in conf['channels']]
            self.nickserv_password = conf['nickserv_password'] if 'nickserv_password' in conf.keys() else None
            self.trusted_nicks = conf['trusted_nicks'] if 'trusted_nicks' in conf.keys() else []
            self.quit_message = conf['quit_message'] if 'quit_message' in conf.keys() else ''
            self.logging = conf['logging'] if 'logging' in conf.keys() else False
        self.irc = None
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.connect_time = None
        self.last_message = None
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
            for message in messages:
                self._send_message(to, message)

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
        self.last_message = datetime.datetime.utcnow()
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

    def _receive(self):
        line = self._readline()  # a line or None if nothing received

        # if we don't receive any messages or pings for a while, something strange happened (like a netsplit)
        if (datetime.datetime.utcnow() - self.last_message).total_seconds() > self.message_timeout:
            raise IRCError('No message received from the server in %i seconds' % self.message_timeout)

        # perform passive operations if the interval is up
        if (datetime.datetime.utcnow() - self.last_passive).total_seconds() > self.passive_interval:
            # check if any nicks with unread messages have come online
            unread_receivers = self.mail.unread_receivers()
            if len(unread_receivers) > 0:
                self._ison(unread_receivers)

            # check if it's time to talk
            for channel in self.channels:
                if channel.idle_talk.can_talk() and False:
                    self._send_message(channel.name, channel.idle_talk.generate_message())

            self.last_passive = datetime.datetime.utcnow()

        if line is None:
            return

        data = line.split()
        self._log(line)
        self.last_message = datetime.datetime.utcnow()

        if len(data) > 1:
            command = data[0]

            if command == 'PING':
                self._pong(' '.join(data[1:]).lstrip(':'))
            elif command == 'ERROR':
                raise IRCError(line)
        if len(data) > 3:
            source = data[0].lstrip(':')
            source_nick = source.split('!')[0]
            command = data[1]

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

        if len(tokens) == 0:
            return  # don't process empty or whitespace-only messages

        if message.startswith(' '):
            tokens[0] = ' ' + tokens[0]  # any initial space is removed by str.split(), so we put it back here

        # explicit commands
        handled = self._explicit_command(tokens[0], tokens[1:] if len(tokens) > 1 else [], reply_target, source_nick)

        if not handled:
            # implicit commands
            self._implicit_command(message, reply_target, source_nick)

            for channel in self.channels:
                if reply_target == channel.name:
                    channel.idle_talk.add_message(message)  # add message to the idle talk log
                    timestamp = int(datetime.datetime.utcnow().timestamp())
                    self.quotes.add_quote(channel.name, timestamp, source_nick, message)  # add message to the quotes database

    def _explicit_command(self, command, args, reply_target, source_nick):
        def parse_quote_command():
            author = None
            year = None

            if len(args) > 0:
                arg = args[0]
                if re.match(r'^\d{4}$', arg) is not None:
                    year = int(arg)
                else:
                    author = arg
            if len(args) > 1 and author is not None and year is None:
                arg = args[1]
                if re.match(r'^\d{4}$', arg) is not None:
                    year = int(arg)

            return author, year

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
                return

            author, year = parse_quote_command()
            random_quote = self.quotes.random_quote(reply_target, author, year)
            self._send_message(reply_target, random_quote if random_quote is not None else 'no quotes found :(')

        def quote_count():
            if reply_target not in [c.name for c in self.channels]:
                return

            author, year = parse_quote_command()
            count = self.quotes.quote_count(reply_target, author, year)
            self._send_message(reply_target, '%i quotes' % count)

        def update():
            if source_nick in self.trusted_nicks:
                if shell.git_pull():
                    self._disconnect()
                    time.sleep(5)  # give the server time to process disconnection to prevent nick collision
                    shell.restart(__file__)
                else:
                    self._send_message(reply_target, 'pull failed, manual update required :(')

        def shell_command():
            if source_nick in self.trusted_nicks:
                for line in shell.run(' '.join(args)):
                    self._send_message(reply_target, line)

        def multiline(lines):
            for line in lines:
                self._send_message(reply_target, line)

        def rpg_action():
            for channel in self.channels:
                if reply_target == channel.name:  # only allow rpg play in channel
                    multiline(channel.rpg.action(' '.join(args)))

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
                multiline(messages)

        command = command.lower()
        commands = {
            '!help': lambda: self._send_message(reply_target, 'https://github.com/proog/nda#commands'),
            '!hi': lambda: self._send_message(reply_target, 'hi %s' % source_nick),
            '!imgur': lambda: self._send_message(reply_target, link_generator.imgur_link()),
            '!reddit': lambda: self._send_message(reply_target, link_generator.reddit_link()),
            '!uptime': uptime,
            '!porn': porn,
            '!quote': quote,
            '!quotecount': quote_count,
            '!update': update,
            '!isitmovienight': lambda: self._send_message(reply_target, 'maybe :)' if datetime.datetime.utcnow().weekday() in [4, 5] else 'no :('),
            '!rpg': rpg_action,
            '!send': send_mail,
            '!unsend': unsend_mail,
            '!outbox': outbox,
            # '!shell': shell_command,
            # '!up': lambda: multiline(self.game.up()),
            # '!down': lambda: multiline(self.game.down()),
            # '!left': lambda: multiline(self.game.left()),
            # '!right': lambda: multiline(self.game.right()),
            # '!look': lambda: multiline(self.game.look()),
            # '!restart': lambda: multiline(self.game.restart())
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
        self.quotes = Quotes([c.name for c in self.channels])
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
