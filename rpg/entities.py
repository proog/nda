class NamedEntity:
    def __init__(self, id_, name, description):
        self.id = id_
        self.name = name
        self.description = description


class LoadedNamedEntity(NamedEntity):
    def __init__(self, definition):
        super(LoadedNamedEntity, self).__init__(definition['id'], definition['name'], definition['description'])


class Item(LoadedNamedEntity):
    pass


class Weapon(Item):
    def __init__(self, definition):
        super(Weapon, self).__init__(definition)
        self.multiplier = definition['multiplier']
        self.cost = definition['cost']


class Armor(Item):
    pass
