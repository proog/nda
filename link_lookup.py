import re
import json
import html
import html.parser
import random
import requests
from requests.exceptions import RequestException
from twitter import Twitter


class LinkLookup:
    timeout = 5
    user_agents = [
        'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/601.3.9 (KHTML, like Gecko) Version/9.0.2 Safari/601.3.9',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.106 Safari/537.36'
    ]

    def __init__(self, youtube_api_key=None, twitter=None):
        self.youtube_api_key = youtube_api_key
        self.twitter_api = twitter

    def contains_youtube(self, message):
        return self._extract_youtube_id(message) is not None

    def youtube(self, message):
        if self.youtube_api_key is None or len(self.youtube_api_key) == 0:
            return None

        youtube_id = self._extract_youtube_id(message)

        if youtube_id is None:
            return None

        try:
            response = requests.get(
                'https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id=%s&key=%s' % (youtube_id, self.youtube_api_key),
                timeout=self.timeout
            )
            json_data = response.json()

            if 'items' in json_data and len(json_data['items']) > 0:
                title = json_data['items'][0]['snippet']['title']
                duration = self._youtube_duration(json_data['items'][0]['contentDetails']['duration'])
                return '%s [%s]' % (title, duration)
            else:
                return None
        except RequestException:
            return None

    def contains_link(self, message):
        return self._extract_link(message) is not None

    def generic(self, message):
        link = self._extract_link(message)

        if link is None:
            return None

        try:
            response = requests.get(link, timeout=self.timeout, headers={
                'Accept-Language': 'en-US',  # to avoid geo-specific response language from e.g. twitter
                'User-Agent': random.choice(self.user_agents)
            })

            if response.status_code != 200 or 'text/html' not in response.headers.get('Content-Type', '').lower():
                return None

            parser = PageTitleParser()
            parser.feed(response.text)
            title = parser.title

            if title is not None and len(title.strip()) > 0:
                return title.strip()
            return None
        except RequestException:
            return None

    def xhamster_comment(self, link):
        parser = XhamsterCommentParser()

        try:
            response = requests.get(link, timeout=self.timeout, headers={
                'User-Agent': random.choice(self.user_agents)
            })
            parser.feed(response.text)
        except:
            return 'couldn\'t load comments :('

        comments = sorted(parser.comments, key=len, reverse=True)
        return comments[0] if len(comments) > 0 else 'no comments :('

    def contains_twitter(self, message):
        return self._extract_twitter_id(message) is not None

    def twitter(self, message):
        tweet_id = self._extract_twitter_id(message)

        if tweet_id is None or self.twitter_api is None:
            return None

        tweet = self.twitter_api.fetch(tweet_id)

        if tweet is not None:
            handle = tweet.author.screen_name
            author = html.unescape(tweet.author.name)
            text = html.unescape(tweet.text)
            return '%s (@%s): %s' % (author, handle, text)
        return None

    def _extract_link(self, message):
        match = re.search(r'.*(http(s)?://.+)(\s+|$)', message)

        if match is not None and len(match.groups()) == 3:
            return match.group(1)
        return None

    def _extract_youtube_id(self, message):
        match = re.search(r'(youtube.com/watch\?v=|youtu.be/)([a-zA-Z0-9_\-]{11})', message)

        if match is not None and len(match.groups()) == 2:
            return match.group(2)
        return None

    def _extract_twitter_id(self, message):
        match = re.search(r'twitter.com/.+/status/(\d+)', message)

        if match is not None and len(match.groups()) == 1:
            return match.group(1)
        return None

    def _youtube_duration(self, duration):
        match = re.match(r'^P(\d+W)?(\d+D)?T(\d+H)?(\d+M)?(\d+S)?$', duration)

        if match is None:
            return 'unknown duration'

        tokens = ['0', '00']
        started = False
        for group in match.groups():
            if group is not None and not started:
                started = True
                tokens = []

            if started:
                tokens.append(group[:-1].zfill(2) if group is not None else '00')

        joined = ':'.join(tokens)

        if len(joined) == 2:
            joined = '0:' + joined  # add zero minute for <1 minute times
        elif joined.startswith('0'):
            joined = joined[1:]  # strip leading zero for >1 minute times

        return joined


class PageTitleParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_head = False
        self.in_title = False
        self.title = None

    def handle_starttag(self, tag, attrs):
        if tag == 'head':
            self.in_head = True
        self.in_title = self.in_head and tag == 'title'

    def handle_endtag(self, tag):
        if tag == 'head':
            self.in_head = False
        self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title = ' '.join(data.strip().split())

    def error(self, message):
        pass


class XhamsterCommentParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.comments = []
        self.in_comments_block = False
        self.in_comment = False

    def handle_starttag(self, tag, attrs):
        if tag == 'div' and ('id', 'commentList') in attrs:
            self.in_comments_block = True
        self.in_comment = self.in_comments_block and tag == 'div' and ('class', 'oh') in attrs

    def handle_endtag(self, tag):
        self.in_comment = False

    def handle_data(self, data):
        if not self.in_comment:
            return
        cleaned = data.replace('\r', '').replace('\n', '').replace('\\', '').strip()
        if cleaned.isprintable() and len(cleaned) > 0:
            self.comments.append(cleaned)

    def error(self, message):
        pass


if __name__ == '__main__':
    with open('nda.conf') as f:
        conf = json.load(f)

    ll = LinkLookup(
        conf.get('youtube_api_key', None),
        Twitter(
            conf.get('twitter_consumer_key', None),
            conf.get('twitter_consumer_secret', None),
            conf.get('twitter_access_token', None),
            conf.get('twitter_access_token_secret', None)
        )
    )
    print(ll.youtube('https://www.youtube.com/watch?v=g6QW-rFtKfA&feature=youtu.be&t=1529'))
    print(ll.youtube('https://www.youtube.com/watch?v=TyTdO5RZY3c'))
    print(ll.generic('hi here is a link for you https://twitter.com/qataraxia/status/672901207845961728'))
    print(ll.xhamster_comment('http://xhamster.com/movies/3949336/merry_christmas_and_happy_new_year.html'))
    print(ll.generic('http://i.imgur.com/wtWCbcf.gifv'))
    print(ll.twitter('laugh at the stupid man https://twitter.com/seanspicer/status/427614837749723136'))
