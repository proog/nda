import random
from rpg.util import Log
from rpg.entities import NamedEntity


class Actor(NamedEntity):
    def __init__(self, id_, name, description, hp, mp, atk, def_, matk, mdef, spd):
        super(Actor, self).__init__(id_, name, description)
        self.max_hp = hp
        self.hp = hp
        self.max_mp = mp
        self.mp = mp
        self.atk = atk
        self.def_ = def_
        self.matk = matk
        self.mdef = mdef
        self.spd = spd

    def attack(self, actor, multiplier, piercing, log):
        diff = self.atk if piercing else max(self.atk - actor.def_, 0)
        rand = random.randint(1,3)
        dmg = ((diff ** 2) / 8 - 0.8 * diff + rand) * multiplier
        dmg2 = dmg
        dmg = max(int(round(dmg, 0)), 1)
        actor.hp = max(actor.hp - dmg, 0)
        log.add('%s attacked %s for %i DMG (%i/%i HP)!' % (self.name, actor.name, dmg, actor.hp, actor.max_hp))
        #log.add('random %i, attacker multiplier %f, unrounded damage %f' % (rand, multiplier, dmg2))

    def spell(self, actor, spell, log):
        if self.mp < spell.mp:
            log.add('%s doesn\'t have enough MP to use %s!' % (self.name, spell.name))
            return

        diff = self.matk if spell.piercing else max(self.matk - actor.mdef_, 0)
        rand = random.randint(1,3)
        dmg = ((diff ** 2) / 8 - 0.8 * diff + rand) * spell.multiplier
        dmg2 = dmg
        dmg = int(round(dmg, 0))
        actor.hp = max(actor.hp - dmg, 0)
        self.mp -= spell.mp

        if spell.multiplier < 0:
            log.add('%s healed %s by %i HP (%i/%i HP)!' % (self.name, actor.name, abs(dmg), actor.hp, actor.max_hp))
        else:
            log.add('%s attacked %s for %i DMG (%i/%i HP)!' % (self.name, actor.name, dmg, actor.hp, actor.max_hp))
        #log.add('random %i, attacker multiplier %f, unrounded damage %f' % (rand, multiplier, dmg2))

    def dead(self):
        return self.hp <= 0

    def alive(self):
        return self.hp > 0

    def respawn(self):
        self.hp = self.max_hp
        self.mp = self.max_mp

    def __str__(self):
        return '%s (HP %i/%i | ATK %i | MATK %i | DEF %i | MDEF %i | SPD %i)' % (self.name, self.hp, self.max_hp, self.atk, self.matk, self.def_, self.mdef, self.spd)


class Player(Actor):
    def __init__(self, name, starting_weapon):
        hp = random.randint(14, 26)
        mp = random.randint(14, 26)
        atk = random.randint(1, 6)
        def_ = random.randint(1, 6)
        matk = random.randint(1, 6)
        mdef = random.randint(1, 6)
        spd = random.randint(1, 6)
        super(Player, self).__init__(None, name, 'The hero of the story.', hp, mp, atk, def_, matk, mdef, spd)
        self.lck = random.randint(1, 6)
        self.exp = 0
        self.gold = 0
        self.lvl = 1
        self.weapon = None
        self.spells = []
        self.change_weapon(starting_weapon, Log())

    def level_up(self, log):
        self.lvl += 1
        self.max_hp += random.randint(8, 16)
        self.max_mp += random.randint(8, 16)
        self.atk += random.randint(1, 4)
        self.def_ += random.randint(1, 4)
        self.matk += random.randint(1, 4)
        self.mdef += random.randint(1, 4)
        self.spd += random.randint(1, 4)
        self.lck += random.randint(1, 4)
        self.respawn()
        log.add('%s attained level %i! Abilities are enhanced!' % (self.name, self.lvl))
        log.add(str(self))

    def change_weapon(self, weapon, log):
        self.weapon = weapon
        log.add('%s got a new weapon: %s!' % (self.name, weapon.name))

    def add_spell(self, spell, log):
        self.spells.append(spell)
        log.add('%s got a new spell: %s!' % (self.name, spell.name))

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
        return '%s (LVL %i | HP %i/%i | MP %i/%i | ATK %i | MATK %i | DEF %i | MDEF %i | SPD %i' % (self.name, self.lvl, self.hp, self.max_hp, self.mp, self.max_mp, self.atk, self.matk, self.def_, self.mdef, self.spd)


class Enemy(Actor):
    def __init__(self, definition):
        super(Enemy, self).__init__(definition['id'],
                                    definition['name'],
                                    definition['description'],
                                    definition['hp'],
                                    definition['mp'],
                                    definition['atk'],
                                    definition['def'],
                                    definition['matk'],
                                    definition['mdef'],
                                    definition['spd'])
        self.multiplier = definition['multiplier']
        self.exp = definition['exp']
        self.gold = definition['gold']
