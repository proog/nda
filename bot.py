#!/usr/bin/env python3

import socket
import select
import time
import link_generator
import link_lookup
import unit_converter
from idle_talk import IdleTalk


class Bot:
    irc = None
    address = 'irc.synirc.net'
    port = 6667
    nick = 'nda_monitor7'
    user = 'nda_monitor7'
    real_name = 'NDA Monitor Pro 2015 - Keeping IT Confidential (tm)'
    channel = '#garachat'
    crlf = '\r\n'
    buffer_size = 1024
    receive_timeout = 10
    lines = []
    unfinished_line = ''
    logging = True
    idle_talk = None

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
        print(msg)

        if self.logging:
            with open('bot.log', 'a', encoding='utf-8') as f:
                f.write('%s\r\n' % msg)

    def _readline(self):
        if len(self.lines) > 0:
            return self.lines.pop(0)  # if any lines are already read, return them in sequence

        buffer = self.irc.recv(self.buffer_size)
        data = buffer.decode('utf-8')
        self.lines = data.split(self.crlf)
        self.lines[0] = self.unfinished_line + self.lines[0]  # prepend unfinished line to its continuation

        if data.endswith(self.crlf):
            self.unfinished_line = ''  # buffer ended on a newline, no remainder
        else:
            self.unfinished_line = self.lines.pop(-1)  # turn unfinished line into remainder for next readline call

        return self.lines.pop(0)  # return a line

    def _connect(self):
        self._log('Connecting to %s:%s' % (self.address, self.port))
        self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect((self.address, self.port))
        self._send('NICK %s' % self.nick)
        self._send('USER %s 8 * :%s' % (self.user, self.real_name))

        while True:
            line = self._readline()
            data = line.split()
            self._log(line)

            if 'PING' in data:
                self._pong(data[-1].lstrip(':'))
                break

        self._send('JOIN %s' % self.channel)

    def _disconnect(self):
        self._log('Disconnecting from %s:%s' % (self.address, self.port))
        self._send('JOIN 0')  # leave all channels
        self.irc.close()

    def _receive(self):
        ready, _, _ = select.select([self.irc], [], [], self.receive_timeout)

        if len(ready) == 0:  # if nothing to receive within timeout, check if it's time to talk
            if self.idle_talk.can_talk():
                self._send_message(self.channel, self.idle_talk.generate_message())
            return

        line = self._readline()
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

            if command == 'PRIVMSG':
                target = data[2]
                reply_target = target if target.startswith('#') else source_nick  # channel or direct message
                message = ' '.join(data[3:]).strip().lstrip(':')

                self._parse_message(message, reply_target, source_nick)

    def _parse_message(self, message, reply_target, source_nick):
        self.idle_talk.add_message(message)  # add other message to the idle talk log

        if message.lower() == '!hi':
            self._send_message(reply_target, 'hi %s' % source_nick)
        if message.lower() == '!imgur':
            self._send_message(reply_target, link_generator.imgur_link(100))
        if message.lower() == '!reddit':
            self._send_message(reply_target, link_generator.reddit_link(100))
        if unit_converter.contains_unit(message):
            converted = unit_converter.convert_unit(message)
            if converted is not None:
                self._send_message(reply_target, '^^ %.2f %s' % (converted[0], converted[1]))
        if link_lookup.contains_youtube(message):
            title = link_lookup.youtube_lookup(message)
            if title is not None:
                self._send_message(reply_target, '^^ \x02%s\x02' % title)  # 0x02 == control character for bold text

    def _main_loop(self):
        self.lines = []
        self.unfinished_line = ''
        self.idle_talk = IdleTalk()

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
            except OSError as os_error:
                self._log('An error occurred (%i): %s' % (os_error.errno, os_error.strerror))
                time.sleep(10)
            except KeyboardInterrupt:
                self._disconnect()
                break

if __name__ == '__main__':
    bot = Bot()
    bot.start()
