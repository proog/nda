import json
import random
import os.path
from datetime import datetime
from rpg.actors import Player
from rpg.entities import Weapon, Spell
from rpg.instances import Dungeon
from rpg.util import Log, relative_path


A_NEW_GAME = 'newgame'
A_LIST_DUNGEONS = 'map'
A_ENTER_DUNGEON = 'enter'
A_ATTACK = 'attack'
A_FLEE = 'flee'
A_SPELL = 'spell'
A_STATUS = 'status'
A_RESPAWN = 'revive'
A_WEAPON_SHOP = 'weaponshop'
A_SPELL_SHOP = 'spellshop'
A_BUY = 'buy'
A_INVENTORY = 'inventory'
S_START = 0
S_OVERWORLD = 1
S_DUNGEON = 2
S_ENCOUNTER = 3
S_DEAD = 4


class RPG:
    respawn_delay = 5
    save_filename = relative_path('save.json')

    def __init__(self):
        with open(relative_path('dungeons.json')) as dungeons, \
                open(relative_path('enemies.json')) as enemies, \
                open(relative_path('weapons.json')) as weapons, \
                open(relative_path('spells.json')) as spells:
            self.enemy_definitions = json.load(enemies)
            self.dungeon_definitions = json.load(dungeons)
            self.weapons = [Weapon(item) for item in json.load(weapons)]
            self.spells = [Spell(item) for item in json.load(spells)]
        self.encounter = None
        self.player = None
        self.dungeon = None
        self.time_of_death = None
        self.last_used_shop = None
        self.state = S_START
        self.states = {
            S_START: {
                A_NEW_GAME: (self.new_game, 1, 'char_name')
            },
            S_OVERWORLD: {
                A_ENTER_DUNGEON: (self.enter_dungeon, 1, 'place_num'),
                A_LIST_DUNGEONS: (self.list_dungeons, 0, ''),
                A_WEAPON_SHOP: (self.weapon_shop, 0, ''),
                A_SPELL_SHOP: (self.spell_shop, 0, ''),
                A_BUY: (self.buy, 1, 'item_num'),
                A_INVENTORY: (self.inventory, 0, ''),
                A_NEW_GAME: (self.new_game, 1, 'char_name'),
                A_STATUS: (self.status, 0, '')
            },
            S_DUNGEON: {},
            S_ENCOUNTER: {
                A_ATTACK: (self.player_attack, 0, ''),
                A_FLEE: (self.player_flee, 0, ''),
                A_SPELL: (self.player_spell, 2, 'spell_num self|enemy'),
                A_INVENTORY: (self.inventory, 0, ''),
                A_STATUS: (self.status, 0, '')
            },
            S_DEAD: {
                A_RESPAWN: (self.respawn, 0, ''),
                A_WEAPON_SHOP: (self.weapon_shop, 0, ''),
                A_SPELL_SHOP: (self.spell_shop, 0, ''),
                A_BUY: (self.buy, 1, 'item_num'),
                A_INVENTORY: (self.inventory, 0, ''),
                A_NEW_GAME: (self.new_game, 1, 'char_name'),
                A_STATUS: (self.status, 0, '')
            }
        }

        if os.path.exists(self.save_filename):
            self.load()

    def action(self, action):
        tokens = action.strip().split()

        if len(tokens) > 0:
            for a, (func, argc, argdesc) in self.states[self.state].items():
                if tokens[0].lower() == a and len(tokens) - 1 == argc:
                    return func(*tokens[1:])

        return self.available_actions()

    def available_actions(self):
        available_actions = ['%s%s' % (name, ' ' + args if argc > 0 else '') for name, (f, argc, args) in self.states[self.state].items()]
        return ['Possible actions are: %s' % ' | '.join(available_actions)]

    def weapon_shop(self):
        self.last_used_shop = A_WEAPON_SHOP

        if self.state == S_DEAD:
            message = '%s dreams about entering an Olde Weaponne Shoppe. For a dream weaponne shoppe, their selection of weaponnes is limited:' % self.player.name
        else:
            message = '%s enters Ye Olde Weaponne Shoppe and takes a look around. For a weaponne shoppe, their selection of weaponnes is limited:' % self.player.name

        weapon_names = ['%i: %s (%i gold)' % (i+1, weapon.name, weapon.cost) for i, weapon in enumerate(self.weapons)]
        return [message] + weapon_names + ['%s has %i gold.' % (self.player.name, self.player.gold)]

    def spell_shop(self):
        self.last_used_shop = A_SPELL_SHOP

        if self.state == S_DEAD:
            message = '%s dreams about running a spell shop that supplies spells to the good people of the town. But then, they start selling spells to %s instead!' % (self.player.name, self.player.name)
        else:
            message = '%s enters a mysterious spell shop. "Welcome," a mysterious voice calls out, "Take a look at my wares..."' % self.player.name

        spell_names = ['%i: %s (%i gold)' % (i+1, spell.name, spell.cost) for i, spell in enumerate(self.spells)]
        return [message] + spell_names + ['%s has %i gold.' % (self.player.name, self.player.gold)]

    def buy(self, index):
        if self.last_used_shop not in [A_WEAPON_SHOP, A_SPELL_SHOP]:
            return ['%s tries to buy something, but is not inside a shop. The people of the town stare in disbelief as %s haggles with an imaginary shopkeeper.' % (self.player.name, self.player.name)]

        is_weapon_shop = self.last_used_shop == A_WEAPON_SHOP

        try:
            index = int(index) - 1
            if index not in range(0, len(self.weapons if is_weapon_shop else self.spells)):
                raise ValueError
        except ValueError:
            return ['%s inspects the shop intensely, but can\'t find such an item.' % self.player.name]

        log = Log()
        item = self.weapons[index] if is_weapon_shop else self.spells[index]

        if is_weapon_shop and item == self.player.weapon or not is_weapon_shop and item in self.player.spells:
            return ['%s already has that.' % self.player.name]

        if self.player.gold < item.cost:
            if self.state == S_DEAD:
                return ['%s doesn\'t have enough dream gold to buy that.' % self.player.name]
            return ['%s doesn\'t have enough gold to buy that.' % self.player.name]

        if is_weapon_shop:
            self.player.change_weapon(item, log)
        else:
            self.player.add_spell(item, log)

        self.player.remove_gold(item.cost, log)
        self.save()

        if self.state == S_DEAD:
            return log.output() + ['Strangely, it materializes next to the sleeping %s. Perhaps dreams do come true after all!' % self.player.name]
        return log.output()

    def can_respawn(self):
        return self.time_of_death is None or self.state == S_DEAD and (datetime.utcnow() - self.time_of_death).total_seconds() > self.respawn_delay

    def respawn(self):
        if self.can_respawn():
            self.player.respawn()
            self.last_used_shop = None
            self.time_of_death = None
            self.state = S_OVERWORLD
            return [random.choice([
                '%s wakes up at the inn. "How did I get here?" %s wonders.' % (self.player.name, self.player.name),
                'Daylight illuminates the small room. %s awakens, ready to adventure again...' % self.player.name,
                'The horrors of the night are vanquished by the sunrise. %s wakes up.' % self.player.name,
                'A rooster crows in the distance. The sun casts its rays of life on the land. %s awakens.' % self.player.name,
                'A rooster is crowing in the distance. %s expected it to be roostering, but doesn\'t worry much about it.' % self.player.name,
                'The smell of bacon gently awakens %s. Yummy! It turns out it\'s actually the next door orphanage burning to the ground. %s ignores the screaming.' % (self.player.name, self.player.name),
                'Some rowdy troubadours gives %s a rough awakening. The troubadours die of leprosy. %s is ready for adventure.' % (self.player.name, self.player.name)
            ])]
        remaining = int(self.respawn_delay - (datetime.utcnow() - self.time_of_death).total_seconds())
        return ['%s is resting for another %i seconds.' % (self.player.name, remaining)]

    def status(self):
        out = []

        if self.state == S_ENCOUNTER:
            out.append('%s is fighting %s in %s' % (self.player, self.encounter.enemy, self.dungeon.name))
        elif self.state == S_DUNGEON:
            out.append('%s is in %s' % (self.player, self.dungeon.name))
        elif self.state == S_OVERWORLD:
            out.append('%s is outside.' % self.player)
        elif self.state == S_DEAD:
            out.append('%s is resting at the inn.' % self.player)

        return out

    def inventory(self):
        spell_names = ['%i: %s' % (i+1, spell.name) for i, spell in enumerate(self.player.spells)]
        spell_text = 'Spells:' if len(spell_names) > 0 else 'No spells'
        return ['%i gold | Weapon: %s | %s' % (self.player.gold, self.player.weapon.name, spell_text)] + spell_names

    def new_game(self, player_name):
        self.encounter = None
        self.dungeon = None
        self.last_used_shop = None
        self.time_of_death = None
        self.player = Player(player_name, self.weapons[0])
        self.state = S_OVERWORLD
        self.save()
        return ['%s sets out on a new adventure!' % self.player] + self.list_dungeons()

    def list_dungeons(self):
        dungeon_names = ['%i: %s (%s)' % (i+1, dungeon['name'], dungeon['description']) for i, dungeon in enumerate(self.dungeon_definitions)]
        return ['%s examines the old map. %i locations are marked with centuries-old ink:' % (self.player.name, len(dungeon_names))] + dungeon_names

    def enter_dungeon(self, index):
        try:
            index = int(index) - 1
            if index >= len(self.dungeon_definitions):
                raise ValueError
        except ValueError:
            return ['%s searches the map thoroughly, but can\'t find such a location.' % self.player.name]

        self.dungeon = Dungeon(self.player, self.dungeon_definitions[index], self.enemy_definitions)
        self.state = S_DUNGEON
        return ['%s cautiously entered %s!' % (self.player.name, self.dungeon.name)] + self.new_encounter()

    def leave_dungeon(self):
        msg = random.choice([
            'The sun is warm and welcoming.',
            'The breeze is nice and cool.',
            'Why do we even have places like that around here?',
            'The blue summer sky welcomes you back.'
        ])
        out = ['%s leaves %s. %s' % (self.player.name, self.dungeon.name, msg)]

        self.state = S_OVERWORLD
        self.encounter = None
        self.dungeon = None
        self.last_used_shop = None
        return out

    def new_encounter(self):
        log = Log()
        self.state = S_ENCOUNTER
        self.encounter = self.dungeon.new_encounter(log)
        return log.output() + self.encounter_result()

    def player_attack(self):
        log = Log()
        self.encounter.player_attack(log)
        return log.output() + self.encounter_result()

    def player_flee(self):
        log = Log()
        self.encounter.player_flee(log)
        return log.output() + self.encounter_result()

    def player_spell(self, index, target):
        try:
            index = int(index) - 1
            if index >= len(self.player.spells):
                raise ValueError
        except ValueError:
            return ['%s doesn\'t know such a spell. Maybe the spell shop can help...' % self.player.name]

        log = Log()
        self.encounter.player_spell(self.player.spells[index], target, log)
        return log.output() + self.encounter_result()

    def encounter_result(self):
        out = []

        if self.encounter.won() or self.encounter.tie():
            self.save()

            if self.dungeon.finished():
                self.player.respawn()
                out += self.leave_dungeon()
            else:
                out += self.new_encounter()
        elif self.encounter.lost():
            self.time_of_death = datetime.utcnow()
            self.state = S_DEAD
            self.encounter = None
            self.dungeon = None
            self.save()

        return out

    def save(self):
        save = {
            'name': self.player.name,
            'hp': self.player.max_hp,
            'max_hp': self.player.max_hp,
            'mp': self.player.mp,
            'max_mp': self.player.max_mp,
            'atk': self.player.atk,
            'def': self.player.def_,
            'matk': self.player.matk,
            'mdef': self.player.mdef,
            'spd': self.player.spd,
            'lck': self.player.lck,
            'exp': self.player.exp,
            'gold': self.player.gold,
            'lvl': self.player.lvl,
            'weapon_id': self.player.weapon.id,
            'spell_ids': [spell.id for spell in self.player.spells]
        }

        with open(self.save_filename, 'w') as f:
            json.dump(save, f)

    def load(self):
        with open(self.save_filename, 'r') as f:
            sav = json.load(f)

            weapon = self.weapons[0]
            for w in self.weapons:
                if w.id == sav['weapon_id']:
                    weapon = w
                    break

            self.new_game(sav['name'])
            self.player.hp = sav['hp']
            self.player.max_hp = sav['max_hp']
            self.player.mp = sav['mp']
            self.player.max_mp = sav['max_mp']
            self.player.atk = sav['atk']
            self.player.def_ = sav['def']
            self.player.matk = sav['matk']
            self.player.mdef = sav['mdef']
            self.player.spd = sav['spd']
            self.player.lck = sav['lck']
            self.player.exp = sav['exp']
            self.player.gold = sav['gold']
            self.player.lvl = sav['lvl']
            self.player.change_weapon(weapon, Log())

            for spell in self.spells:
                if spell.id in sav['spell_ids']:
                    self.player.add_spell(spell)

            return ['Loaded game.']


if __name__ == '__main__':
    g = RPG()

    while True:
        c = input()
        output = []
        output = g.action(c)

        for line in output:
            print(line)
