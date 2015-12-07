import random
from rpg.entities import LoadedNamedEntity
from rpg.actors import Enemy
from rpg.util import weighted_choice


class Dungeon(LoadedNamedEntity):
    max_encounters = 5

    def __init__(self, player, definition, enemy_definitions):
        super(Dungeon, self).__init__(definition)

        self.player = player
        self.definition = definition
        self.enemy_definitions = enemy_definitions
        self.encounter_count = 0

        if len(definition['enemies']) == 0 or 'boss' not in definition:
            raise ValueError('Dungeon must have at least one enemy and exactly one boss')

    def enemies(self):
        ret = []
        for id, probability in self.definition['enemies'].items():
            for enemy in filter(lambda e: e['id'] == id, self.enemy_definitions):
                ret.append((Enemy(enemy), probability))
        return ret

    def boss(self):
        for enemy in self.enemy_definitions:
            if enemy['id'] == self.definition['boss']:
                return Enemy(enemy)

    def finished(self):
        return self.encounter_count >= self.max_encounters

    def new_encounter(self, log):
        enemy = self.boss() if self.encounter_count == self.max_encounters - 1 else weighted_choice(self.enemies())
        encounter = Encounter(self.player, enemy, log)

        log.add(random.choice([
            '%s notices some strange shadows.' % self.player.name,
            'Everything seems peaceful, when suddenly...',
            '%s has a lust for blood!' % enemy.name,
            'A rabid %s appears before %s!' % (enemy.name, self.player.name),
            '"Now this is what I call adventure!" %s says to no one in particular.' % self.player.name,
            '%s looks around. "What a strange place..."' % self.player.name
        ]))

        if random.randint(0, 1) == 0:
            log.add('%s encountered %s!' % (self.player.name, enemy))
        else:
            log.add('%s ambushed %s!' % (enemy, self.player.name))
            encounter.enemy_attack(log)

        self.encounter_count += 1
        return encounter


class Encounter:
    def __init__(self, player, enemy, log):
        self.fled = False
        self.player = player
        self.enemy = enemy

    def active(self):
        return not self.won() and not self.lost() and not self.tie()

    def won(self):
        return self.enemy.dead()

    def lost(self):
        return self.player.dead()

    def tie(self):
        return self.fled

    def enemy_attack(self, log):
        self.enemy.attack(self.player, log)
        if self.player.dead():
            log.add('%s was defeated...' % self.player.name)
            log.add(random.choice([
                '... but a friendly hand reaches out...',
                '... but it\'s not over quite yet...',
                '... but %s stays determined...' % self.player.name,
                '... but some friendly animals help %s to safety...' % self.player.name,
                '... but %s won\'t give up...' % self.player.name,
                '... "%s, don\'t give up!"' % self.player.name,
                '... but a traveling band of friendly bards discover %s on the ground...' % self.player.name
            ]))

    def player_attack(self, log):
        self.player.attack(self.enemy, log)

        if self.enemy.alive():
            self.enemy_attack(log)
        else:
            log.add('%s vanquished!' % self.enemy.name)
            self.player.add_rewards(self.enemy.exp, self.enemy.gold, log)

    def player_flee(self, log):
        self.fled = random.randint(0, self.enemy.spd + self.player.spd) > self.enemy.spd

        if self.fled:
            log.add('%s flees!' % self.player.name)
        else:
            log.add('%s couldn\'t flee!' % self.player.name)
            self.enemy_attack(log)
