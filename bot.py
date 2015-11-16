#!/usr/bin/env python3

import socket
import select
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
    idle_talk = None

    def __send(self, msg):
        if not msg.endswith(self.crlf):
            msg += self.crlf
        self.irc.send(msg.encode('utf-8'))

    def __send_message(self, to, msg):
        self.__log('Sending %s to %s' % (msg, to))
        self.__send('PRIVMSG %s :%s' % (to, msg))

    def __pong(self, msg):
        self.__send('PONG :%s' % msg)

    def __log(self, msg):
        print(msg)
        with open('bot.log', 'a') as f:
            f.write('%s\r\n' % msg)

    def __connect(self):
        self.__log('Connecting to %s:%s' % (self.address, self.port))
        self.irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.irc.connect((self.address, self.port))
        self.__send('NICK %s' % self.nick)
        self.__send('USER %s 8 * :%s' % (self.user, self.real_name))

        while True:
            buffer = self.irc.recv(self.buffer_size)
            data = buffer.decode('utf-8').split()
            self.__log(' '.join(data))

            if 'PING' in data:
                self.__pong(data[-1].lstrip(':'))
                break

        self.__send('JOIN %s' % self.channel)

    def __disconnect(self):
        self.__log('Disconnecting from %s:%s' % (self.address, self.port))
        self.__send('JOIN 0')  # leave all channels
        self.irc.close()

    def __receive(self):
        ready, _, _ = select.select([self.irc], [], [], self.receive_timeout)

        if len(ready) == 0:  # if nothing to receive within timeout, check if it's time to talk
            if self.idle_talk.can_talk():
                self.__send_message(self.channel, self.idle_talk.generate_message())
            return

        buffer = self.irc.recv(self.buffer_size)
        data = buffer.decode('utf-8').strip().split(' ')
        self.__log(' '.join(data))

        if len(data) > 1:
            command = data[0]

            if command == 'PING':
                self.__pong(' '.join(data[1:]).lstrip(':'))

        if len(data) > 3:
            source = data[0].lstrip(':')
            source_nick = source.split('!')[0]
            command = data[1]

            if command == 'PRIVMSG':
                target = data[2]
                reply_target = target if target.startswith('#') else source_nick  # channel or direct message
                message = ' '.join(data[3:]).strip().lstrip(':')

                self.__parse_message(message, reply_target, source_nick)

    def __parse_message(self, message, reply_target, source_nick):
        self.idle_talk.add_message(message)  # add other message to the idle talk log

        if message.lower() == '!hi':
            self.__send_message(reply_target, 'hi %s' % source_nick)
        if message.lower() == '!imgur':
            self.__send_message(reply_target, 'ok brb')
            self.__send_message(reply_target, link_generator.imgur_link(100))
        if message.lower() == '!youtube':
            self.__send_message(reply_target, 'ok brb')
            self.__send_message(reply_target, link_generator.youtube_link(100))
        if unit_converter.contains_unit(message):
            converted = unit_converter.convert_unit(message)
            if converted is not None:
                self.__send_message(reply_target, '^^ %.2f %s' % (converted[0], converted[1]))
        if link_lookup.contains_youtube(message):
            title = link_lookup.youtube_lookup(message)
            if title is not None:
                self.__send_message(reply_target, '^^ %s' % title)

    def start(self):
        self.__connect()
        self.idle_talk = IdleTalk()

        while True:
            self.__receive()

    def stop(self):
        self.__disconnect()

if __name__ == '__main__':
    bot = Bot()
    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()
