import random
import time
import os.path


class IdleTalk:
    min_log_length = 30
    max_log_length = 200
    log_file = 'idle_talk.log'

    min_idle_delay = 1800  # 30 mins
    max_idle_delay = 7200  # 2 hours
    min_message_interval = 5
    max_message_interval = 1800

    def _random_delay(self):
        return random.randint(self.min_idle_delay, self.max_idle_delay)

    def _random_interval(self):
        return random.randint(self.min_message_interval, self.max_message_interval)

    def _trim_log(self):
        while len(self.log) > self.max_log_length:
            i = random.randint(0, len(self.log) - 1)
            del self.log[i]  # remove random message from log

    def add_message(self, msg):
        self.log.append(msg)
        self.last_message = time.time()
        self.delay = self._random_delay()  # set a random delay for each "quiet period"

        with open(self.log_file, 'a', encoding='utf-8') as file:
            file.write('%s\r\n' % msg)

        self._trim_log()

    def can_talk(self):
        t = time.time()

        return len(self.log) >= self.min_log_length \
            and self.last_message + self.delay < t \
            and self.last_generated_message + self.interval < t

    def generate_message(self):
        self.last_generated_message = time.time()
        self.interval = self._random_interval()  # set a random interval after each generated message

        return self.log[random.randint(0, len(self.log) - 1)]

    def __init__(self):
        self.log = []
        self.last_message = time.time()
        self.last_generated_message = 0
        self.delay = self._random_delay()
        self.interval = self._random_interval()

        if os.path.isfile(self.log_file):
            with open(self.log_file, 'r', encoding='utf-8') as file:
                self.log = file.readlines()

        self._trim_log()


class IdleTimer:
    min_idle_delay = 1800  # 30 mins
    max_idle_delay = 7200  # 2 hours
    min_message_interval = 5
    max_message_interval = 1800  # 30 mins

    def _random_delay(self):
        return random.randint(self.min_idle_delay, self.max_idle_delay)

    def _random_interval(self):
        return random.randint(self.min_message_interval, self.max_message_interval)

    def message_received(self):
        self.last_receive = time.time()
        self.delay = self._random_delay()  # set a random delay for each "quiet period"

    def message_sent(self):
        self.last_send = time.time()
        self.interval = self._random_interval()  # set a random interval after each generated message

    def can_talk(self):
        t = time.time()
        return self.last_receive + self.delay < t and self.last_send + self.interval < t

    def __init__(self):
        self.last_receive = 0
        self.last_send = 0
        self.delay = 0
        self.interval = 0
        self.message_received()
