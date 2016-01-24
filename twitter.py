import tweepy


class Twitter:
    def __init__(self, consumer_key, consumer_secret, access_token, access_token_secret):
        try:
            for v in [consumer_key, consumer_secret, access_token, access_token_secret]:
                if v is None or len(v) == 0:
                    raise Exception

            auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
            auth.set_access_token(access_token, access_token_secret)
            self.api = tweepy.API(auth)
        except:
            self.api = None

    def tweet(self, msg):
        if self.api is None or len(msg.strip()) == 0:
            return False

        try:
            self.api.update_status(msg)
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


if __name__ == '__main__':
    twitter = Twitter('',
                      '',
                      '',
                      '')
    print(twitter.fetch('26971816341798913').text)
    #twitter.tweet('@proogey hi')

