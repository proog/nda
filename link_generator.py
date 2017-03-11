import random
import json
import re
from datetime import datetime, timedelta
import requests
import requests.auth
from requests.exceptions import RequestException


class LinkGenerator:
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

    def __init__(self, reddit_key=None, reddit_secret=None, pastebin_api_key=None):
        self.reddit_key = reddit_key
        self.reddit_secret = reddit_secret
        self.pastebin_api_key = pastebin_api_key
        self.reddit_access_token = None
        self.reddit_access_token_expiry = datetime.utcnow()

    def imgur(self):
        chars = self.lowercase_chars + self.uppercase_chars + self.numbers

        for _ in range(0, self.max_tries):
            combination = self._generate_combination(chars, 5)
            url = 'http://i.imgur.com/%s.jpg' % combination

            try:
                response = requests.head(url, timeout=self.timeout, headers={
                    'User-Agent': random.choice(self.user_agents)
                })

                if response.status_code == 200:
                    return url
            except RequestException:
                return 'connection failed, please try again later :('

        return 'couldn\'t find a valid link in %i tries :(' % self.max_tries

    def reddit(self):
        chars = self.lowercase_chars + self.numbers

        for _ in range(0, self.max_tries):
            combination = self._generate_combination(chars, 4)
            url = 'https://www.reddit.com/r/all/comments/3t%s' % combination

            try:
                response = requests.head(url, timeout=self.timeout, headers={
                    'User-Agent': random.choice(self.user_agents)
                })

                if response.status_code == 200:
                    return url
            except RequestException:
                return 'connection failed, please try again later :('

        return 'couldn\'t find a valid link in %i tries :(' % self.max_tries

    def xhamster(self):
        gay = random.randint(0, 1) == 1
        # sometimes their randomizer fails and redirects to the front page
        front_redirect = re.compile(r'^http(s)?://(www\.)?xhamster\.com(/)?$')
        # sometimes it redirects to https
        https_redirect = re.compile(r'^https://(www\.)?xhamster\.com/random\.php$')

        def request(https=False):
            protocol = 'https' if https else 'http'
            response = requests.head(
                protocol + '://xhamster.com/random.php',
                timeout=self.timeout,
                headers={
                    'User-Agent': random.choice(self.user_agents),
                    'Cookie': 'x_content_preference_index=s%3A3%3A%22gay%22%3B' if gay else ''
                }
            )
            location = response.headers.get('Location', '')

            if response.status_code in [301, 302]:
                if https_redirect.match(location) and not https:
                    return request(True)
                if not front_redirect.match(location):
                    return location
            return None

        for _ in range(0, self.max_tries):
            try:
                url = request()
                if url is not None:
                    return url
            except RequestException:
                return 'connection failed, please try again later :('

        return 'couldn\'t find a valid link in %i tries :(' % self.max_tries

    def wikihow(self):
        for _ in range(0, self.max_tries):
            try:
                response = requests.head(
                    'http://www.wikihow.com/Special:Randomizer',
                    timeout=self.timeout,
                    headers={
                        'User-Agent': random.choice(self.user_agents)
                    }
                )
                location = response.headers.get('Location', None)

                if response.status_code == 302 and location is not None:
                    return location
            except RequestException:
                return 'connection failed, please try again later :('

        return 'couldn\'t find a valid link in %i tries :(' % self.max_tries

    def penis(self):
        user_agent = 'nda_reddit:v0.1'
        subreddit = random.choice(['massivecock', 'penis', 'softies', 'autofellatio', 'tinydick', 'selfservice', 'guysgonewild', 'totallystraight', 'ratemycock'])
        listing = random.choice(['new', 'hot', 'controversial'])
        api_url = 'https://oauth.reddit.com/r/%s/%s?limit=20&raw_json=1' % (subreddit, listing)
        access_token = self._get_reddit_access_token(user_agent)

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

    def make_pastebin(self, text):
        if self.pastebin_api_key is None:
            return None

        url = 'http://pastebin.com/api/api_post.php'
        data = {
            'api_dev_key': self.pastebin_api_key,
            'api_option': 'paste',
            'api_paste_code': text
        }

        try:
            response = requests.post(url, data)
            return response.text if response.text.startswith('http://') else None
        except:
            return None

    def _generate_combination(self, chars, length):
        return ''.join([chars[random.randint(0, len(chars) - 1)] for i in range(length)])

    def _get_reddit_access_token(self, user_agent):
        if self.reddit_key is None or self.reddit_secret is None:
            return None

        # the request itself may take time so we refresh the token 10 seconds earlier than needed
        expiry = self.reddit_access_token_expiry - timedelta(seconds=10)

        if self.reddit_access_token is None or datetime.utcnow() >= expiry:
            auth = requests.auth.HTTPBasicAuth(self.reddit_key, self.reddit_secret)

            try:
                response = requests.post(
                    'https://www.reddit.com/api/v1/access_token',
                    auth=auth,
                    data={
                        'grant_type': 'client_credentials',
                        'username': self.reddit_key,
                        'password': self.reddit_secret
                    },
                    headers={
                        'User-Agent': user_agent
                    }
                )

                response_json = response.json()
                expires_in = response_json.get('expires_in', 0)
                self.reddit_access_token = response_json.get('access_token', None)
                self.reddit_access_token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            except:
                return None

        return self.reddit_access_token


if __name__ == '__main__':
    with open('nda.conf', 'r') as f:
        conf = json.load(f)

    lg = LinkGenerator(
        conf.get('reddit_consumer_key', None),
        conf.get('reddit_consumer_secret', None),
        conf.get('pastebin_api_key', None)
    )
    print('found: ' + lg.imgur())
    print('found: ' + lg.reddit())
    print('found: ' + lg.xhamster())
    print('found: ' + lg.wikihow())
    print(lg.penis())
    print(lg.penis())
    print(lg.make_pastebin('nda says hi :)'))
