import http
import http.client
import random


lowercase_chars = 'abcdefghijklmnopqrstuvwxyz'
uppercase_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
numbers = '0123456789'


def generate_combination(chars, length):
    return ''.join([chars[random.randint(0, len(chars) - 1)] for i in range(length)])


def imgur_link(max_tries):
    chars = lowercase_chars + uppercase_chars + numbers
    tries = 0

    while tries < max_tries:
        combination = generate_combination(chars, 5)

        connection = http.client.HTTPConnection('i.imgur.com')
        connection.request('HEAD', '/%ss.jpg' % combination)
        response = connection.getresponse()

        if response.status == 200:
            return 'http://i.imgur.com/%ss.jpg' % combination

        tries += 1

    return 'couldn\'t find a valid link in %i tries :(' % max_tries


def youtube_link(max_tries):
    chars = lowercase_chars + uppercase_chars + numbers
    tries = 0

    while tries < max_tries:
        combination = generate_combination(chars, 11)

        connection = http.client.HTTPConnection('youtube.com')
        connection.request('HEAD', '/watch?v=%s' % combination)
        response = connection.getresponse()

        if response.status == 200:
            return 'http://youtube.com/watch?v=%s' % combination

        tries += 1

    return 'couldn\'t find a valid link in %i tries :(' % max_tries

if __name__ == '__main__':
    print('found: ' + imgur_link(100))
