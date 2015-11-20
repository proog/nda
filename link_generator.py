import urllib.request
import random
from urllib.error import *

lowercase_chars = 'abcdefghijklmnopqrstuvwxyz'
uppercase_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
numbers = '0123456789'
max_tries = 100


def generate_combination(chars, length):
    return ''.join([chars[random.randint(0, len(chars) - 1)] for i in range(length)])


def imgur_link():
    chars = lowercase_chars + uppercase_chars + numbers

    for attempt in range(0, max_tries):
        combination = generate_combination(chars, 5)
        url = 'http://i.imgur.com/%s.jpg' % combination
        request = urllib.request.Request(url, method='HEAD')

        try:
            response = urllib.request.urlopen(request)

            if response.status == 200:
                return url
        except (HTTPError, URLError):
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def reddit_link():
    chars = lowercase_chars + numbers

    for attempt in range(0, max_tries):
        combination = generate_combination(chars, 4)
        url = 'https://www.reddit.com/r/all/comments/3t%s' % combination
        request = urllib.request.Request(url, method='HEAD')

        try:
            response = urllib.request.urlopen(request)

            if response.status == 200:
                return url
        except (HTTPError, URLError):
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


if __name__ == '__main__':
    print('found: ' + reddit_link())
