import urllib.request
import re
import json
import html.parser
import random
from urllib.error import *


def extract_youtube_id(message):
    match = re.search(r'(youtube.com/watch\?v=|youtu.be/)([a-zA-Z0-9_\-]{11})', message)

    if match is not None and len(match.groups()) == 2:
        return match.group(2)
    return None


def contains_youtube(message):
    return extract_youtube_id(message) is not None


def youtube_lookup(message):
    api_key = 'AIzaSyApSlFsotpdr3IRoh_dT0ElL3V9XN0lMyo'
    youtube_id = extract_youtube_id(message)

    if youtube_id is None:
        return None

    try:
        response = urllib.request.urlopen('https://www.googleapis.com/youtube/v3/videos?part=snippet&id=%s&key=%s' % (youtube_id, api_key))
        data = response.read()
        json_data = json.loads(data.decode('utf-8'))

        if 'items' in json_data \
                and len(json_data['items']) > 0 \
                and 'snippet' in json_data['items'][0] \
                and 'title' in json_data['items'][0]['snippet']:
            return json_data['items'][0]['snippet']['title']
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
    link = extract_link(message)

    if link is None:
        return None

    try:
        response = urllib.request.urlopen(link)

        if response.status != 200:
            return None

        data = response.read().decode('utf-8', errors='ignore').replace('\n', '')
        title_match = re.search(r'.*<title>(.+)</title>.*', data, flags=re.IGNORECASE)

        if title_match is not None and len(title_match.groups()) == 1:
            return title_match.group(1)
        else:
            return None
    except (HTTPError, URLError):
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
            self.comments.append(data)

        def error(self, message):
            pass

    parser = Parser()

    try:
        response = urllib.request.urlopen(link)
        parser.feed(response.read().decode('utf-8'))
    except:
        return None

    comments = sorted(parser.comments, key=lambda x: len(x), reverse=True)
    return comments[0] if len(comments) > 0 else None


if __name__ == '__main__':
    print(youtube_lookup('https://www.youtube.com/watch?v=g6QW-rFtKfA&feature=youtu.be&t=1529'))
    print(generic_lookup('hi here is a link for you https://permortensen.com/about'))
