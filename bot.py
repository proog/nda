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
from idle_talk import IdleTalk
from quotes import Quotes


class Bot:
    irc = None
    buffer_size = 1024
    receive_timeout = 10
    crlf = '\r\n'
    lines = []
    unfinished_line = ''
    idle_talk = None
    quotes = None

    def __init__(self, conf_file):
        with open(conf_file, 'r', encoding='utf-8') as f:
            conf = json.load(f)
            self.address = conf['address']
            self.port = conf['port'] if 'port' in conf.keys() else 6667
            self.user = conf['user']
            self.nick = conf['nick']
            self.real_name = conf['real_name']
            self.channel = conf['channel']
            self.nickserv_password = conf['nickserv_password'] if 'nickserv_password' in conf.keys() else None
            self.trusted_nicks = conf['trusted_nicks'] if 'trusted_nicks' in conf.keys() else []
            self.quit_message = conf['quit_message'] if 'quit_message' in conf.keys() else ''
            self.logging = conf['logging'] if 'logging' in conf.keys() else False

    def _send(self, msg):
        if not msg.endswith(self.crlf):
            msg += self.crlf
        self.irc.send(msg.encode('utf-8'))

    def _send_message(self, to, msg):
        self._log('Sending %s to %s' % (msg.strip(self.crlf), to))
        self._send('PRIVMSG %s :%s' % (to, msg))

    def _pong(self, msg):
        self._send('PONG :%s' % msg)

    def _log(self, msg):
        msg = '%s %s' % (datetime.datetime.utcnow(), msg)

        if self.logging:
            print(msg)
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
        # if no newlines found in buffer, the entire buffer is an unfinished line (line longer than buffer_size)
        self.unfinished_line = lines.pop(-1)
        self.lines = lines

        return self._readline()  # recurse until a finished line is found or nothing is received within timeout

    def _connect(self):
        self._log('Connecting to %s:%s' % (self.address, self.port))
        self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect((self.address, self.port))
        self._send('NICK %s' % self.nick)
        self._send('USER %s 8 * :%s' % (self.user, self.real_name))

    def _disconnect(self):
        self._log('Disconnecting from %s:%s' % (self.address, self.port))
        self.quotes.close()

        try:
            self._send('QUIT :%s' % self.quit_message)
            self.irc.close()
        except OSError as os_error:
            self._log('An error occurred while disconnecting (%i): %s' % (os_error.errno, os_error.strerror))

    def _receive(self):
        line = self._readline()  # a line or None if nothing received

        if line is None:  # if no more lines and none received within timeout, check if it's time to talk
            if self.idle_talk.can_talk() and False:
                self._send_message(self.channel, self.idle_talk.generate_message())
            return

        data = line.split()
        self._log(line)

        if len(data) > 1:
            command = data[0]

            if command == 'PING':
                self._pong(' '.join(data[1:]).lstrip(':'))
            elif command == 'ERROR':
                raise ValueError('Received ERROR from server (%s)' % line)
        if len(data) > 3:
            source = data[0].lstrip(':')
            source_nick = source.split('!')[0]
            command = data[1]

            if command == '001':  # RPL_WELCOME: successful client registration
                if self.nickserv_password is not None:
                    self._send_message('NickServ', 'IDENTIFY %s' % self.nickserv_password)
                self._send('JOIN %s' % self.channel)
            elif command == 'PRIVMSG':
                target = data[2]
                reply_target = target if target.startswith('#') else source_nick  # channel or direct message
                message = ' '.join(data[3:]).strip().lstrip(':')
                self._parse_message(message, reply_target, source_nick)

    def _parse_message(self, message, reply_target, source_nick):
        tokens = message.split()

        # explicit commands
        if message.lower() == '!hi':
            self._send_message(reply_target, 'hi %s' % source_nick)
            return
        elif message.lower() == '!imgur':
            self._send_message(reply_target, link_generator.imgur_link())
            return
        elif message.lower() == '!reddit':
            self._send_message(reply_target, link_generator.reddit_link())
            return
        elif message.lower() == '!porn':
            self._send_message(reply_target, link_generator.xhamster_link())
            return
        elif tokens[0] == '!quote' and False:
            self._send_message(reply_target, self.quotes.random_quote(tokens[1] if len(tokens) > 1 else None))
            return
        elif message.lower() == '!update' and source_nick in self.trusted_nicks:
            if shell.git_pull():
                self._send_message(reply_target, 'pull succeeded, restarting')
                self._disconnect()
                time.sleep(5)  # give the server time to process disconnection to prevent nick collision
                shell.restart(__file__)
            else:
                self._send_message(reply_target, 'pull failed wih non-zero return code :(')
            return
        elif message.startswith('!shell ') and source_nick in self.trusted_nicks and False:
            shell_command = ''.join(message.split('!shell ')[1:])
            output = shell.run(shell_command)
            for line in output:
                self._send_message(reply_target, line)
            return

        # link and unit lookups
        if link_lookup.contains_youtube(message):
            title = link_lookup.youtube_lookup(message)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)  # 0x02 == control character for bold text
        elif link_lookup.contains_link(message) and False:
            title = link_lookup.generic_lookup(message)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)
        elif unit_converter.contains_unit(message) and False:
            converted = unit_converter.convert_unit(message)
            if converted is not None:
                self._send_message(reply_target, '^^ %.2f %s' % (converted[0], converted[1]))

        self.idle_talk.add_message(message)  # add message to the idle talk log
        self.quotes.add_quote(int(time.time()), source_nick, message)  # add message to the quotes database

    def _main_loop(self):
        self.lines = []
        self.unfinished_line = ''
        self.idle_talk = IdleTalk()
        self.quotes = Quotes(self.channel)

        self._connect()
        while True:
            self._receive()

    def start(self):
        while True:  # keep trying to run the main loop even after errors occur
            try:
                self._main_loop()
            except ValueError as irc_error:
                self._log('Error received from the server: %s' % irc_error.args)
                self._disconnect()
                time.sleep(5)
            except OSError as os_error:
                self._log('An error occurred (%i): %s' % (os_error.errno, os_error.strerror))
                time.sleep(5)
            except KeyboardInterrupt:
                self._disconnect()
                break


if __name__ == '__main__':
    bot = Bot('bot.conf')
    bot.start()
