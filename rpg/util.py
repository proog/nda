import os.path
import random


def relative_path(filename):
    return os.path.join(os.path.dirname(__file__), filename)


def weighted_choice(item_weight_tuples):
    total = sum(weight for item, weight in item_weight_tuples)
    r = random.uniform(0, total)
    upto = 0
    for item, weight in item_weight_tuples:
        if upto + weight >= r:
            return item
        upto += weight


class Log:
    def __init__(self):
        self.messages = []

    def add(self, msg):
        self.messages.append(msg)

    def add_many(self, msgs):
        self.messages += msgs

    def output(self):
        return [msg for msg in self.messages]
