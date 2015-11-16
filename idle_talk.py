import random
import time
import os.path


class IdleTalk:
    log = []
    last_message = time.time()
    last_generated_message = 0

    min_log_length = 30
    max_log_length = 200
    log_file = 'idle_talk.log'

    min_idle_delay = 1800  # 30 mins
    max_idle_delay = 7200  # 2 hours
    min_message_interval = 15
    max_message_interval = 1800

    def __trim_log(self):
        while len(self.log) > self.max_log_length:
            i = random.randint(0, len(self.log) - 1)
            del self.log[i]  # remove random message from log

    def add_message(self, msg):
        self.log.append(msg)
        self.last_message = time.time()

        with open(self.log_file, 'a') as file:
            file.write('%s\r\n' % msg)

        self.__trim_log()

    def can_talk(self):
        t = time.time()
        random_delay = random.randint(self.min_idle_delay, self.max_idle_delay)
        random_interval = random.randint(self.min_message_interval, self.max_message_interval)

        return len(self.log) >= self.min_log_length \
            and self.last_message + random_delay < t \
            and self.last_generated_message + random_interval < t

    def generate_message(self):
        self.last_generated_message = time.time()
        return self.log[random.randint(0, len(self.log))]

    def __init__(self):
        if os.path.isfile(self.log_file):
            with open(self.log_file) as file:
                self.log = file.readlines()

        self.__trim_log()
