import requests
import random
from requests.exceptions import *


timeout = 5
lowercase_chars = 'abcdefghijklmnopqrstuvwxyz'
uppercase_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
numbers = '0123456789'
max_tries = 100
user_agents = [
    'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 Safari/601.3.9',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36'
]


def generate_combination(chars, length):
    return ''.join([chars[random.randint(0, len(chars) - 1)] for i in range(length)])


def imgur_link():
    chars = lowercase_chars + uppercase_chars + numbers

    for attempt in range(0, max_tries):
        combination = generate_combination(chars, 5)
        url = 'http://i.imgur.com/%s.jpg' % combination

        try:
            response = requests.head(url, timeout=timeout, headers={
                'User-Agent': random.choice(user_agents)
            })

            if response.status_code == 200:
                return url
        except RequestException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def reddit_link():
    chars = lowercase_chars + numbers

    for attempt in range(0, max_tries):
        combination = generate_combination(chars, 4)
        url = 'https://www.reddit.com/r/all/comments/3t%s' % combination

        try:
            response = requests.head(url, timeout=timeout, headers={
                'User-Agent': random.choice(user_agents)
            })

            if response.status_code == 200:
                return url
        except RequestException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def xhamster_link():
    gay = random.randint(0, 1) == 1

    for attempt in range(0, max_tries):
        try:
            response = requests.head('http://xhamster.com/random.php', timeout=timeout, headers={
                'User-Agent': random.choice(user_agents),
                'Cookie': 'x_content_preference_index=s%3A3%3A%22gay%22%3B' if gay else ''
            })
            location = response.headers.get('Location', None)

            # sometimes their randomizer fails and redirects to the front page, try again if that happens
            if response.status_code == 302 and location is not None and location != 'http://xhamster.com':
                return location
        except RequestException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def wikihow_link():
    for attempt in range(0, max_tries):
        try:
            response = requests.head('http://www.wikihow.com/Special:Randomizer', timeout=timeout, headers={
                'User-Agent': random.choice(user_agents)
            })
            location = response.headers.get('Location', None)

            if response.status_code == 302 and location is not None:
                return location
        except RequestException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


if __name__ == '__main__':
    print('found: ' + imgur_link())
    print('found: ' + reddit_link())
    print('found: ' + xhamster_link())
    print('found: ' + wikihow_link())
