import random
from rpg.util import Log
from rpg.entities import NamedEntity


class Actor(NamedEntity):
    def __init__(self, id_, name, description, hp, atk, def_, spd, multiplier):
        super(Actor, self).__init__(id_, name, description)
        self.max_hp = hp
        self.hp = hp
        self.atk = atk
        self.def_ = def_
        self.spd = spd
        self.multiplier = multiplier

    def attack(self, actor, log):
        atk_def_diff = max(self.atk - actor.def_, 0)
        rand = random.randint(1,3)
        dmg = ((atk_def_diff ** 2) / 8 - 0.8 * atk_def_diff + rand) * self.multiplier
        dmg2 = dmg
        dmg = max(int(round(dmg, 0)), 1)
        actor.hp = max(actor.hp - dmg, 0)
        log.add('%s attacked %s for %i DMG (%i/%i HP)!' % (self.name, actor.name, dmg, actor.hp, actor.max_hp))
        #log.add('random %i, attacker multiplier %f, unrounded damage %f' % (rand, self.multiplier, dmg2))

    def dead(self):
        return self.hp <= 0

    def alive(self):
        return self.hp > 0

    def respawn(self):
        self.hp = self.max_hp

    def __str__(self):
        return '%s (HP %i/%i | ATK %i | DEF %i | SPD %i)' % (self.name, self.hp, self.max_hp, self.atk, self.def_, self.spd)


class Player(Actor):
    def __init__(self, name, starting_weapon):
        hp = random.randint(14, 26)
        atk = random.randint(1, 6)
        def_ = random.randint(1, 6)
        spd = random.randint(1, 6)
        super(Player, self).__init__(None, name, 'The hero of the story.', hp, atk, def_, spd, 1)
        self.lck = random.randint(1, 6)
        self.exp = 0
        self.gold = 0
        self.lvl = 1
        self.weapon = None
        self.change_weapon(starting_weapon, Log())

    def level_up(self, log):
        self.lvl += 1
        self.max_hp += random.randint(8, 16)
        self.hp = self.max_hp
        self.atk += random.randint(1, 4)
        self.def_ += random.randint(1, 4)
        self.spd += random.randint(1, 4)
        self.lck += random.randint(1, 4)
        log.add('%s attained level %i! Abilities are enhanced!' % (self.name, self.lvl))
        log.add(str(self))

    def change_weapon(self, weapon, log):
        self.weapon = weapon
        self.multiplier = weapon.multiplier
        log.add('%s got a new weapon: %s!' % (self.name, weapon.name))

    def next_lvl_exp(self, exp):
        base = 10
        while round(base, 0) <= exp:
            base += base * 1.5
        return int(round(base, 0))

    def add_exp(self, exp, log):
        next = self.next_lvl_exp(self.exp)
        self.exp += exp

        while self.exp >= next:
            self.level_up(log)
            next = self.next_lvl_exp(next)

    def add_gold(self, gold):
        self.gold += gold

    def add_rewards(self, exp, gold, log):
        log.add('%s gains %i EXP and %i gold!' % (self.name, exp, gold))
        self.add_gold(gold)
        self.add_exp(exp, log)

    def remove_gold(self, gold, log):
        self.gold -= gold
        log.add('%i gold removed.' % gold)

    def __str__(self):
        return '%s (LVL %i | HP %i/%i | ATK %i | DEF %i | SPD %i | %i gold | %s x%.1f)' % (self.name, self.lvl, self.hp, self.max_hp, self.atk, self.def_, self.spd, self.gold, self.weapon.name, self.multiplier)


class Enemy(Actor):
    def __init__(self, definition):
        super(Enemy, self).__init__(definition['id'],
                                    definition['name'],
                                    definition['description'],
                                    definition['hp'],
                                    definition['atk'],
                                    definition['def'],
                                    definition['spd'],
                                    definition['multiplier'])
        self.exp = definition['exp']
        self.gold = definition['gold']
