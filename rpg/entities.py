class NamedEntity:
    def __init__(self, id_, name, description):
        self.id = id_
        self.name = name
        self.description = description


class LoadedNamedEntity(NamedEntity):
    def __init__(self, definition):
        super(LoadedNamedEntity, self).__init__(definition['id'], definition['name'], definition['description'])


class Item(LoadedNamedEntity):
    def __init__(self, definition):
        super(Item, self).__init__(definition)
        self.cost = definition['cost']


class ActiveItem(Item):
    def __init__(self, definition):
        super(ActiveItem, self).__init__(definition)
        self.piercing = definition['piercing']
        self.multiplier = definition['multiplier']


class Weapon(ActiveItem):
    def __init__(self, definition):
        super(Weapon, self).__init__(definition)


class Spell(ActiveItem):
    def __init__(self, definition):
        super(Spell, self).__init__(definition)


class Armor(Item):
    pass
