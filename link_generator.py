import http
import http.client
import random


timeout = 5
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

        try:
            connection = http.client.HTTPConnection('i.imgur.com', timeout=timeout)
            connection.request('HEAD', '/%s.jpg' % combination)
            response = connection.getresponse()

            if response.status == 200:
                return 'http://i.imgur.com/%s.jpg' % combination
        except http.client.HTTPException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def reddit_link():
    chars = lowercase_chars + numbers

    for attempt in range(0, max_tries):
        combination = generate_combination(chars, 4)

        try:
            connection = http.client.HTTPSConnection('www.reddit.com', timeout=timeout)
            connection.request('HEAD', '/r/all/comments/3t%s' % combination)
            response = connection.getresponse()

            if response.status == 200:
                return 'https://www.reddit.com/r/all/comments/3t%s' % combination
        except http.client.HTTPException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def xhamster_link():
    gay = random.randint(0, 1) == 1
    headers = {
        'Cookie': 'x_content_preference_index=s%3A3%3A%22gay%22%3B' if gay else ''
    }

    for attempt in range(0, max_tries):
        try:
            connection = http.client.HTTPConnection('xhamster.com', timeout=timeout)
            connection.request('HEAD', '/random.php', headers=headers)
            response = connection.getresponse()
            location = response.getheader('Location', None)

            # sometimes their randomizer fails and redirects to the front page, try again if that happens
            if response.status == 302 and location is not None and location != 'http://xhamster.com':
                return location
        except http.client.HTTPException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def wikihow_link():
    for attempt in range(0, max_tries):
        try:
            connection = http.client.HTTPConnection('www.wikihow.com', timeout=timeout)
            connection.request('HEAD', '/Special:Randomizer')
            response = connection.getresponse()
            location = response.getheader('Location', None)

            if response.status == 302 and location is not None:
                return location
        except http.client.HTTPException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


if __name__ == '__main__':
    print('found: ' + xhamster_link())
    print('found: ' + wikihow_link())
