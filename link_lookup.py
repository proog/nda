import urllib.request
import re
import json
from urllib.error import *


def extract_youtube_id(message):
    match = re.match(r'.*(youtube.com/watch\?v=|youtu.be/)([a-zA-Z0-9_\-]{11}).*', message)

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


if __name__ == '__main__':
    print(youtube_lookup('https://www.youtube.com/watch?v=g6QW-rFtKfA&feature=youtu.be&t=1529'))