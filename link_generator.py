import http
import http.client
import random


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
            connection = http.client.HTTPConnection('i.imgur.com')
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
            connection = http.client.HTTPSConnection('www.reddit.com')
            connection.request('HEAD', '/r/all/comments/3t%s' % combination)
            response = connection.getresponse()

            if response.status == 200:
                return 'https://www.reddit.com/r/all/comments/3t%s' % combination
        except http.client.HTTPException:
            return 'connection failed, please try again later :('

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


if __name__ == '__main__':
    print('found: ' + reddit_link())
