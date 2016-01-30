import tweepy
from datetime import datetime


class Twitter:
    tweet_rate = 60  # a tweet per 1 minute

    def __init__(self, consumer_key, consumer_secret, access_token, access_token_secret):
        self.last_tweet = datetime.min
        self.api = None

        try:
            for v in [consumer_key, consumer_secret, access_token, access_token_secret]:
                if v is None or len(v) == 0:
                    raise Exception

            auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
            auth.set_access_token(access_token, access_token_secret)
            self.api = tweepy.API(auth)
        except:
            pass

    def tweet(self, msg):
        if self.api is None or len(msg.strip()) == 0 or self.next_tweet_delay() > 0:
            return False

        try:
            self.api.update_status(msg)
            self.last_tweet = datetime.utcnow()
            return True
        except (tweepy.TweepError, tweepy.RateLimitError):
            return False

    def fetch(self, tweet_id):
        if self.api is None:
            return None

        try:
            return self.api.get_status(tweet_id)
        except (tweepy.TweepError, tweepy.RateLimitError):
            return None

    def next_tweet_delay(self):
        diff = self.tweet_rate - (datetime.utcnow() - self.last_tweet).total_seconds()
        return max(int(diff), 0)


if __name__ == '__main__':
    twitter = Twitter('',
                      '',
                      '',
                      '')
    print(twitter.fetch('26971816341798913').text)
    #twitter.tweet('@proogey hi')

