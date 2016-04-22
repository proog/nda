#!/usr/bin/env python3

import socket
import select
import time
import traceback
from datetime import datetime
from util import is_channel


class IRCError(Exception):
    pass


class IRC:
    buffer_size = 4096     # buffer size for each socket read
    receive_timeout = 0.5  # how long to wait for socket data in each main loop iteration
    ping_wait = 200        # how long to wait before pinging the server
    ping_timeout = 10      # and how long to wait for a pong when pinging
    ping_text = 'nda'      # text to send with pings
    crlf = '\r\n'          # irc message delimiter

    def __init__(self, address, port, user, real_name, nicks, nickserv_password, logging):
        self.address = address
        self.port = port
        self.user = user
        self.real_name = real_name
        self.nicks = nicks
        self.nickserv_password = nickserv_password
        self.logging = logging

        self.socket = None
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.connect_time = datetime.min
        self.last_ping = datetime.min
        self.waiting_for_pong = False

    def current_nick(self):
        return self.nicks[self.nick_index]

    def log(self, msg):
        msg = '%s %s' % (datetime.utcnow(), msg)
        print(msg)

        if self.logging:
            with open('nda.log', 'a', encoding='utf-8') as f:
                f.write('%s%s' % (msg, self.crlf))

    def send_message(self, to, msg):
        if msg is None or len(msg) == 0:
            return

        msg = msg.replace(self.crlf, '\n').replace('\n', ' ').strip()
        self.log('Sending %s to %s' % (msg, to))
        command = 'PRIVMSG %s :' % to

        # irc max line length is 512, but server -> other clients will tack on a :source, so let's be conservative
        chunk_size = 512 - len(command + self.crlf) - 100
        chunks = [msg[i:i + chunk_size] for i in range(0, len(msg), chunk_size)]

        for chunk in chunks:
            self._send(command + chunk + self.crlf)

        self.message_sent(to, msg)

    def send_messages(self, to, msgs):
        for msg in msgs:
            self.send_message(to, msg)

    def _send(self, msg):
        if not msg.endswith(self.crlf):
            msg += self.crlf
        self.socket.send(msg.encode('utf-8'))

    def _ping(self, msg):
        self.log('Sending PING :%s' % msg)
        self._send('PING :%s' % msg)
        self.waiting_for_pong = True
        self.last_ping = datetime.utcnow()

    def _pong(self, msg):
        self.log('Sending PONG :%s' % msg)
        self._send('PONG :%s' % msg)

    def _change_nick(self, nick):
        self.log('Sending NICK %s' % nick)
        self._send('NICK %s' % nick)

    def _join(self, channel):
        self.log('Sending JOIN %s' % channel)
        self._send('JOIN %s' % channel)

    def _ison(self, nicks):
        nicks_str = ' '.join(nicks)
        self.log('Sending ISON %s' % nicks_str)
        self._send('ISON %s' % nicks_str)

    def _quit(self, quit_message):
        self.log('Sending QUIT :%s' % quit_message)
        self._send('QUIT :%s' % quit_message)

    def _readline(self):
        if len(self.lines) > 0:
            return self.lines.pop(0)  # if any lines are already read, return them in sequence

        ready, _, _ = select.select([self.socket], [], [], self.receive_timeout)

        if len(ready) == 0:  # if no lines and nothing received, return None
            return None

        buffer = self.socket.recv(self.buffer_size)
        data = self.unfinished_line + buffer.decode('utf-8', errors='ignore')  # prepend unfinished line to its continuation
        lines = data.split(self.crlf)

        # if buffer ended on newline, the last element will be empty string
        # otherwise, the last element will be an unfinished line
        # if no newlines found in buffer, the entire buffer is an unfinished line (line longer than what recv returned)
        self.unfinished_line = lines.pop(-1)
        self.lines = lines

        return self._readline()  # recurse until a finished line is found or nothing is received within timeout

    def _connect(self):
        now = datetime.utcnow()
        self.lines = []
        self.unfinished_line = ''
        self.nick_index = 0
        self.connect_time = now
        self.waiting_for_pong = False
        self.last_ping = now

        self.log('Connecting to %s:%s' % (self.address, self.port))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((self.address, self.port))

        self._send('USER %s 8 * :%s' % (self.user, self.real_name))
        self._change_nick(self.current_nick())

    def _disconnect(self, quit_message='quit'):
        self.log('Disconnecting from %s:%s' % (self.address, self.port))

        try:
            self._quit(quit_message)
            self.socket.close()
        except OSError as os_error:
            self.log('An error occurred while disconnecting (%i): %s' % (os_error.errno, os_error.strerror))

    def _receive(self):
        now = datetime.utcnow()
        line = self._readline()  # a line or None if nothing received

        # if the last ping (server or client) happened over ping_wait seconds ago, let's follow up on that
        # if we did not already send a ping, the server hasn't pinged us in a while, so ping it once
        # if that ping doesn't trigger a pong within ping_timeout, the server is in limbo and we want to reconnect
        if not self.waiting_for_pong and (now - self.last_ping).total_seconds() > self.ping_wait:
            self.log('No PING received from the server in %i seconds' % self.ping_wait)
            self._ping(self.ping_text)
        elif self.waiting_for_pong and (now - self.last_ping).total_seconds() > self.ping_timeout:
            raise IRCError('No PONG received from the server in %i seconds' % self.ping_timeout)

        if line is None:
            return

        data = line.split()
        self.log(line)

        if len(data) < 2:  # smallest message we want is PING :msg
            return

        if not data[0].startswith(':'):  # distinguish between message formats
            command = data[0]

            if command == 'PING':
                self._pong(' '.join(data[1:]).lstrip(':'))
                self.last_ping = datetime.utcnow()
            elif command == 'ERROR':
                raise IRCError(line)
        else:
            source = data[0].lstrip(':')
            source_nick = source.split('!')[0]
            command = data[1]

            if '!' in source and source_nick not in self.nicks:  # update last seen whenever anything happens from some nick
                self.nick_seen(source_nick)

            if command == '001':  # RPL_WELCOME: successful client registration
                if self.nickserv_password is not None and len(self.nickserv_password) > 0:
                    self.send_message('NickServ', 'IDENTIFY %s' % self.nickserv_password)

                self.connected()
            elif command == '303':  # RPL_ISON: list of online nicks, process mail here
                self.ison_result(' '.join(data[3:]).lstrip(':').split())
            elif command == '433':  # ERR_NICKNAMEINUSE: nick already taken
                self.nick_index += 1
                if self.nick_index >= len(self.nicks):
                    self.log('Error: all nicks already in use')
                    raise KeyboardInterrupt
                self._change_nick(self.current_nick())
            elif command == 'PONG':
                self.waiting_for_pong = False
            elif command == 'KICK':
                time.sleep(2)
                self._join(data[2])
            elif command == 'JOIN':  # process mail as soon as the user joins instead of after passive_interval seconds
                if source_nick != self.current_nick():  # disregard own joins
                    self.nick_joined(source_nick)
            elif command == 'PRIVMSG':
                target = data[2]
                reply_target = target if is_channel(target) else source_nick  # channel or direct message
                message = ' '.join(data[3:]).lstrip(':')
                self.message_received(message, reply_target, source_nick)

    def _main_loop(self):
        disconnect = False
        connect = True

        while True:
            try:
                if disconnect:
                    self._disconnect('an error occurred, reconnecting')
                    disconnect = False
                    time.sleep(5)

                if connect:
                    self._connect()
                    connect = False

                self._receive()
                self.main_loop_iteration()
            except IRCError as irc_error:
                self.log('IRC error: %s' % irc_error.args)
                disconnect = True
                connect = True
            except OSError as os_error:
                self.log('OS error (errno %s): %s' % (str(os_error.errno), os_error.strerror))
                disconnect = True
                connect = True
            except KeyboardInterrupt:
                self._disconnect('nda loves you :)')
                break
            except Exception as error:
                self.log('Unknown error (%s): %s' % (str(type(error)), error.args))
                self.log(traceback.format_exc())
                self.unknown_error_occurred(error)
                time.sleep(10)

    def start(self):
        self.started()
        self._main_loop()
        self.stopped()

    # abstract methods for subclasses:

    def connected(self): pass

    def ison_result(self, nicks): pass

    def main_loop_iteration(self): pass

    def message_received(self, message, reply_target, source_nick): pass

    def message_sent(self, to, message): pass

    def nick_joined(self, nick): pass

    def nick_seen(self, nick): pass

    def started(self): pass

    def stopped(self): pass

    def unknown_error_occurred(self, error): pass
