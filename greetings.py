import random
import json
import os.path
from datetime import datetime


class Greeting:
    def __init__(self, channel, dt, message):
        self.greet_time = datetime.min
        self.last_used = datetime.min
        self.channel = channel
        self.message = message
        self.regenerate(dt)

    def regenerate(self, dt):
        h = random.randint(0, 23)
        m = random.randint(0, 59)
        s = random.randint(0, 59)
        self.greet_time = datetime(year=dt.year,
                                   month=dt.month,
                                   day=dt.day,
                                   hour=h,
                                   minute=m,
                                   second=s)

    def matches(self, now):
        same_date = self._matches_date(now)
        dt_passed = now >= self.greet_time.replace(year=now.year)
        already_used = self._used_today(now)
        return same_date and dt_passed and not already_used

    def _matches_date(self, now):
        return now.month == self.greet_time.month and now.day == self.greet_time.day

    def _used_today(self, now):
        return self.last_used.date() == self.greet_time.replace(year=now.year).date()


def greet():
    now = datetime.utcnow()
    ret = []

    for greeting in greetings:
        if greeting.matches(now):
            greeting.last_used = now
            greeting.regenerate(greeting.greet_time)
            ret.append((greeting.channel, greeting.message))

    return ret


greetings = []

if os.path.exists('greetings.conf'):
    with open('greetings.conf') as f:
        for json_greeting in json.load(f)['greetings']:
            channel = json_greeting['channel']
            dt = datetime.strptime(json_greeting['date'], '%Y-%m-%d')
            message = json_greeting['message']
            greetings.append(Greeting(channel, dt, message))
