import time
import json
import os.path
from datetime import datetime


class Greeting:
    def __init__(self, channel, dt, repeat, message, last_used):
        self.channel = channel
        self.repeat = repeat
        self.message = message
        self.last_used = last_used if last_used is not None else datetime(1970, 1, 1)
        self.greet_time = datetime(year=dt.year,
                                   month=dt.month,
                                   day=dt.day,
                                   hour=dt.hour,
                                   minute=dt.minute,
                                   second=dt.second)

    def matches(self, now):
        # make a copy of the timestamps with the variable/repeatable parts swapped out with the current time
        # last used time needs to be compared using the variable parts too
        # (otherwise any event from earlier in the year will trigger: a last_used 0001-01-01 00:00:00
        # < yearly 2016-01-01 (= not already used), but 2016-01-01 00:00:00 >= 2016-01-01 00:00:00 (= already used))
        time_cmp = self.greet_time
        used_cmp = self.last_used

        if self.repeat in ['yearly', 'monthly', 'daily', 'hourly', 'minutely']:
            time_cmp = time_cmp.replace(year=now.year)
            used_cmp = used_cmp.replace(year=now.year)
        if self.repeat in ['monthly', 'daily', 'hourly', 'minutely']:
            time_cmp = time_cmp.replace(month=now.month)
            used_cmp = used_cmp.replace(month=now.month)
        if self.repeat in ['daily', 'hourly', 'minutely']:
            time_cmp = time_cmp.replace(day=now.day)
            used_cmp = used_cmp.replace(day=now.day)
        if self.repeat in ['hourly', 'minutely']:
            time_cmp = time_cmp.replace(hour=now.hour)
            used_cmp = used_cmp.replace(hour=now.hour)
        if self.repeat in ['minutely']:
            time_cmp = time_cmp.replace(minute=now.minute)
            used_cmp = used_cmp.replace(minute=now.minute)

        passed = now >= time_cmp
        already_used = used_cmp >= time_cmp
        return passed and not already_used

    def as_json(self):
        return {
            'channel': self.channel,
            'date': self.greet_time.strftime(date_format),
            'repeat': self.repeat,
            'message': self.message,
            'last_used': self.last_used.strftime(date_format)
        }


conf_file = 'greetings.conf'
date_format = '%Y-%m-%d %H:%M:%S'


def greet():
    greetings = reload()
    now = datetime.utcnow()
    matched = []

    for greeting in greetings:
        if greeting.matches(now):
            greeting.last_used = now
            matched.append((greeting.channel, greeting.message))

    if len(matched) > 0:
        with open(conf_file, 'w') as f:
            json.dump([g.as_json() for g in greetings], f, indent=2, separators=(',', ': '), sort_keys=True)

    return matched


def reload():
    greetings = []
    if os.path.exists(conf_file):
        with open(conf_file) as f:
            for json_greeting in json.load(f):
                channel = json_greeting['channel']
                dt = datetime.strptime(json_greeting['date'], date_format)
                repeat = json_greeting['repeat'].lower()
                message = json_greeting['message']
                last_used = json_greeting.get('last_used', None)

                if last_used is not None:
                    last_used = datetime.strptime(last_used, date_format)

                greetings.append(Greeting(channel, dt, repeat, message, last_used))
    return greetings


if __name__ == '__main__':
    while True:
        print(datetime.utcnow(), greet())
        time.sleep(10)
