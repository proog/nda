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

    def __random_delay(self):
        return random.randint(self.min_idle_delay, self.max_idle_delay)

    def __random_interval(self):
        return random.randint(self.min_message_interval, self.max_message_interval)

    def __trim_log(self):
        while len(self.log) > self.max_log_length:
            i = random.randint(0, len(self.log) - 1)
            del self.log[i]  # remove random message from log

    def add_message(self, msg):
        self.log.append(msg)
        self.last_message = time.time()
        self.delay = self.__random_delay()  # set a random delay for each "quiet period"

        with open(self.log_file, 'a') as file:
            file.write('%s\r\n' % msg)

        self.__trim_log()

    def can_talk(self):
        t = time.time()

        return len(self.log) >= self.min_log_length \
            and self.last_message + self.delay < t \
            and self.last_generated_message + self.interval < t

    def generate_message(self):
        self.last_generated_message = time.time()
        self.interval = self.__random_interval()  # set a random interval after each generated message

        return self.log[random.randint(0, len(self.log))]

    def __init__(self):
        self.log = []
        self.last_message = time.time()
        self.last_generated_message = 0
        self.delay = self.__random_delay()
        self.interval = self.__random_interval()

        if os.path.isfile(self.log_file):
            with open(self.log_file) as file:
                self.log = file.readlines()

        self.__trim_log()
