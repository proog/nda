import requests
import requests.auth
import random
import json
from requests.exceptions import *
from datetime import datetime, timedelta


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
reddit_access_token = None
reddit_access_token_expiry = None


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


def get_reddit_access_token(consumer_key, consumer_secret, user_agent):
    global reddit_access_token, reddit_access_token_expiry

    if consumer_key is None or consumer_secret is None:
        return None

    # the request itself may take time so we refresh the token 10 seconds earlier than needed
    if reddit_access_token is None or datetime.utcnow() >= reddit_access_token_expiry - timedelta(seconds=10):
        auth = requests.auth.HTTPBasicAuth(consumer_key, consumer_secret)

        try:
            response = requests.post('https://www.reddit.com/api/v1/access_token', auth=auth, data={
                'grant_type': 'client_credentials',
                'username': consumer_key,
                'password': consumer_secret
            }, headers={
                'User-Agent': user_agent
            })

            response_json = response.json()
            reddit_access_token = response_json.get('access_token', None)
            reddit_access_token_expiry = datetime.utcnow() + timedelta(seconds=response_json.get('expires_in', 0))
        except:
            return None

    return reddit_access_token


def penis_link(consumer_key, consumer_secret):
    user_agent = 'nda_reddit:v0.1'
    subreddit = random.choice(['massivecock', 'penis', 'softies', 'autofellatio', 'tinydick', 'selfservice', 'guysgonewild', 'totallystraight'])
    listing = random.choice(['new', 'hot', 'controversial'])
    api_url = 'https://oauth.reddit.com/r/%s/%s?limit=20&raw_json=1' % (subreddit, listing)
    access_token = get_reddit_access_token(consumer_key, consumer_secret, user_agent)

    if access_token is None:
        return None

    try:
        response = requests.get(api_url, headers={
            'Authorization': 'bearer %s' % access_token,
            'User-Agent': user_agent
        })
        posts = response.json().get('data', {}).get('children', [])

        if len(posts) == 0:
            return None

        post = random.choice(posts)['data']
        url = post['url']
        title = post['title']
    except:
        return None

    return '%s -- %s' % (url, title)


def make_pastebin(text, pastebin_api_key):
    url = 'http://pastebin.com/api/api_post.php'
    data = {
        'api_dev_key': pastebin_api_key,
        'api_option': 'paste',
        'api_paste_code': text
    }

    try:
        response = requests.post(url, data)
        return response.text if response.text.startswith('http://') else None
    except:
        return None


if __name__ == '__main__':
    print('found: ' + imgur_link())
    print('found: ' + reddit_link())
    print('found: ' + xhamster_link())
    print('found: ' + wikihow_link())

    with open('nda.conf', 'r') as f:
        conf = json.load(f)
        consumer_key = conf.get('reddit_consumer_key', None)
        consumer_secret = conf.get('reddit_consumer_secret', None)
        print(penis_link(consumer_key, consumer_secret))
        print(penis_link(consumer_key, consumer_secret))
        print(make_pastebin('nda says hi :)', conf.get('pastebin_api_key', None)))
