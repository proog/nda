import urllib.request
import re
import json
import html.parser
import random
from urllib.error import *


youtube_api_key = None
user_agents = [
    'Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11',
    'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:41.0) Gecko/20100101 Firefox/41.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/45.0.2454.101 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_4) AppleWebKit/534.57.2 (KHTML, like Gecko) Version/5.1.7 Safari/534.57.2',
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)',
    'Opera/9.80 (Windows NT 5.1; U; en) Presto/2.10.229 Version/11.60'
]


def extract_youtube_id(message):
    match = re.search(r'(youtube.com/watch\?v=|youtu.be/)([a-zA-Z0-9_\-]{11})', message)

    if match is not None and len(match.groups()) == 2:
        return match.group(2)
    return None


def contains_youtube(message):
    return extract_youtube_id(message) is not None


def youtube_lookup(message):
    if youtube_api_key is None or len(youtube_api_key) == 0:
        return None

    youtube_id = extract_youtube_id(message)

    if youtube_id is None:
        return None

    try:
        response = urllib.request.urlopen('https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails&id=%s&key=%s' % (youtube_id, youtube_api_key))
        data = response.read()
        json_data = json.loads(data.decode('utf-8'))

        if 'items' in json_data and len(json_data['items']) > 0:
            title = json_data['items'][0]['snippet']['title']

            duration_replace = {
                'P': '',
                'W': ':',
                'D': ':',
                'T': '',
                'H': ':',
                'M': ':',
                'S': ''
            }
            duration = json_data['items'][0]['contentDetails']['duration']
            for a, b in duration_replace.items():
                duration = duration.replace(a, b)
            duration = ':'.join([x.zfill(2) for x in duration.split(':')]).lstrip('0')
            if ':' not in duration:  # if under a minute, add 0: to the front
                duration = '0:' + duration
            return '%s [%s]' % (title, duration)
        else:
            return None
    except (HTTPError, URLError):
        return None


def extract_link(message):
    match = re.search(r'.*(http(s)?://.+)(\s+|$)', message)

    if match is not None and len(match.groups()) == 3:
        return match.group(1)
    return None


def contains_link(message):
    return extract_link(message) is not None


def generic_lookup(message):
    class Parser(html.parser.HTMLParser):
        in_head = False
        in_title = False
        title = None

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

    link = extract_link(message)

    if link is None:
        return None

    try:
        request = urllib.request.Request(link, headers={
            'Accept-Language': 'en-US',  # to avoid geo-specific response language from e.g. twitter
            'User-Agent': random.choice(user_agents)
        })
        response = urllib.request.urlopen(request)

        if response.status != 200 or 'text/html' not in response.getheader('Content-Type', '').lower():
            return None

        parser = Parser(convert_charrefs=True)
        parser.feed(response.read().decode('utf-8'))
        title = parser.title

        return title if title is not None and len(title) > 0 else None
    except (HTTPError, URLError, UnicodeDecodeError):
        return None


def xhamster_comment(link):
    class Parser(html.parser.HTMLParser):
        comments = []
        in_comments_block = False
        in_comment = False

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

    parser = Parser(convert_charrefs=True)

    try:
        request = urllib.request.Request(link, headers={
            'User-Agent': random.choice(user_agents)
        })
        response = urllib.request.urlopen(request)
        parser.feed(response.read().decode('utf-8'))
    except:
        return 'couldn\'t load comments :('

    comments = sorted(parser.comments, key=lambda x: len(x), reverse=True)
    return comments[0] if len(comments) > 0 else 'no comments :('


if __name__ == '__main__':
    with open('bot.conf') as f:
        youtube_api_key = json.load(f).get('youtube_api_key', None)

    print(youtube_lookup('https://www.youtube.com/watch?v=g6QW-rFtKfA&feature=youtu.be&t=1529'))
    print(generic_lookup('hi here is a link for you https://twitter.com/qataraxia/status/672901207845961728'))
    #print(xhamster_comment('http://xhamster.com/movies/3949336/merry_christmas_and_happy_new_year.html'))
