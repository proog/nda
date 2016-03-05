import sys
from datetime import datetime


def normalize_nick(nick, aliases_map):
    nick = nick.lower().strip('_ ')  # try to normalize nicks to lowercase versions and no alts

    for (master, aliases) in aliases_map.items():
        if nick == master or nick in aliases:
            return master

    return nick


def year_to_timestamps(year):
    if year is None:
        return 0, sys.maxsize
    elif year not in range(1970, datetime.utcnow().year + 1):
        return None

    time_min = int(datetime(year, 1, 1, 0, 0, 0).timestamp())
    time_max = int(datetime(year, 12, 31, 23, 59, 59).timestamp())
    return time_min, time_max


def escape_sql_like(word):
    for char in ['\\', '%', '_']:
        word = word.replace(char, '\\' + char)
    return word


def clamp(minimum, i, maximum):
    return max(minimum, min(i, maximum))
