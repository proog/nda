class Maze:
    player = '@'
    space = ' '
    walls = ['#']
    dangers = ['!']
    exits = ['>', '<', '^', 'V']
    NO_ACTION = 0
    BLOCKED = 1
    MOVED = 2
    DIED = 3
    WON = 4
    LOOKED = 5
    status_lines = {
        NO_ACTION: 'you are okay :)',
        BLOCKED: 'a wall blocked your path :(',
        MOVED: 'you moved :)',
        DIED: 'you are dead :(',
        WON: 'you won :D',
        LOOKED: 'you looked around :)'
    }
    status = NO_ACTION

    def __init__(self):
        self.level = []
        self.restart()

    def _find_player(self):
        for y in range(0, len(self.level)):
            x = self.level[y].find(self.player)
            if x > -1:
                return x, y
        return 0, 0

    def _set_position(self, new_x, new_y):
        self.level = [line.replace(self.player, self.space) for line in self.level]
        self.level[new_y] = self.level[new_y][:new_x] + self.player + self.level[new_y][(new_x + 1):]

    def _move(self, x, y):
        if self.status in [self.DIED, self.WON]:
            return self.NO_ACTION

        old_x, old_y = self._find_player()
        new_x, new_y = old_x + x, old_y + y

        if self.level[new_y][new_x] == self.space:
            self._set_position(new_x, new_y)
            self.status = self.MOVED
        elif self.level[new_y][new_x] in self.exits:
            self._set_position(new_x, new_y)
            self.status = self.WON
        elif self.level[new_y][new_x] in self.dangers:
            self._set_position(new_x, new_y)
            self.status = self.DIED
        elif self.level[new_y][new_x] in self.walls:
            self.status = self.BLOCKED

    def output(self):
        return self.level + [self.status_lines[self.status]]

    def restart(self):
        with open('maze.txt', 'r', encoding='utf-8') as f:
            self.level = f.read().splitlines()
        self.status = self.NO_ACTION
        return self.output()

    def look(self):
        self.status = self.LOOKED
        return self.output()

    def up(self):
        self._move(0, -1)
        return self.output()

    def down(self):
        self._move(0, 1)
        return self.output()

    def left(self):
        self._move(-1, 0)
        return self.output()

    def right(self):
        self._move(1, 0)
        return self.output()


if __name__ == '__main__':
    m = Maze()
    output = m.output()
    while True:
        print('\n'.join(output))
        inp = input()
        if inp == 'up':
            output = m.up()
        elif inp == 'down':
            output = m.down()
        elif inp == 'left':
            output = m.left()
        elif inp == 'right':
            output = m.right()
        elif inp == 'look':
            output = m.look()
        elif inp == 'restart':
            output = m.restart()
