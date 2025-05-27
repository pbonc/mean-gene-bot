import random

class BattleshipGame:
    def __init__(self, num_ships, test_mode=False):
        self.num_ships = num_ships
        self.test_mode = test_mode
        self.active = False
        self.players = []
        self.player_turn_index = 0
        self.guessed_this_round = set()
        self.ships = set()
        self.guesses = {}  # {username: set of guessed cells}
        self.raffle_hits = {}  # {username: hit count}
        self.all_guessed_cells = set()  # Track all guessed cells globally
        self.intel_used_this_turn = set()  # Track which players used intel this turn

    def register_player(self, username):
        username = username.lower()
        if username not in self.players:
            self.players.append(username)
            self.guesses[username] = set()

    def start_game(self):
        self.active = True
        self.player_turn_index = 0
        self.guessed_this_round = set()
        self.ships = self._random_ships()
        self.all_guessed_cells = set()
        # Reset all guesses for new game
        for p in self.players:
            self.guesses[p] = set()
        self.raffle_hits = {}
        self.intel_used_this_turn = set()

    def _random_ships(self):
        rows = [chr(ord('A') + i) for i in range(10)]  # A-J
        cols = [str(i+1) for i in range(10)]           # 1-10
        all_cells = [row+col for row in rows for col in cols]
        chosen = set(random.sample(all_cells, min(self.num_ships, len(all_cells))))
        return chosen

    def is_valid_cell(self, cell):
        cell = cell.upper()
        if len(cell) < 2 or len(cell) > 3:
            return False
        row = cell[0]
        col_str = cell[1:]
        if row not in "ABCDEFGHIJ":
            return False
        if not col_str.isdigit():
            return False
        col = int(col_str)
        return 1 <= col <= 10

    def get_current_player(self):
        if not self.players:
            return None
        return self.players[self.player_turn_index % len(self.players)]

    def has_guessed(self, username):
        return username in self.guessed_this_round

    def mark_guessed(self, username):
        self.guessed_this_round.add(username)

    def mark_intel(self, username):
        self.intel_used_this_turn.add(username)

    def has_used_intel(self, username):
        return username in self.intel_used_this_turn

    def guess(self, username, cell):
        username = username.lower()
        cell = cell.upper()
        # Validate cell
        if not self.is_valid_cell(cell):
            return ("Invalid", None, [])
        if cell in self.all_guessed_cells:
            nearby = self.get_nearby_open_cells(cell)
            return ("Already guessed", None, nearby)
        if username not in self.guesses:
            self.guesses[username] = set()
        self.guesses[username].add(cell)
        self.all_guessed_cells.add(cell)
        is_hit = cell in self.ships
        if is_hit:
            self.ships.remove(cell)
            self.raffle_hits[username] = self.raffle_hits.get(username, 0) + 1
        return ("Hit" if is_hit else "Miss", is_hit, [])

    def get_nearby_open_cells(self, cell):
        cell = cell.upper()
        if not self.is_valid_cell(cell):
            return []
        row = cell[0]
        col_str = cell[1:]
        col = int(col_str)
        rows = "ABCDEFGHIJ"
        row_idx = rows.find(row)
        neighbors = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        for dr, dc in directions:
            new_row_idx = row_idx + dr
            new_col = col + dc
            if 0 <= new_row_idx < 10 and 1 <= new_col <= 10:
                neighbor = f"{rows[new_row_idx]}{new_col}"
                if neighbor not in self.all_guessed_cells:
                    neighbors.append(neighbor)
        return neighbors

    def get_random_open_cells(self, count=5):
        rows = "ABCDEFGHIJ"
        cols = range(1, 11)
        all_cells = [f"{r}{c}" for r in rows for c in cols]
        open_cells = [cell for cell in all_cells if cell not in self.all_guessed_cells]
        if not open_cells:
            return []
        random.shuffle(open_cells)
        return open_cells[:count]

    def next_turn(self):
        self.player_turn_index = (self.player_turn_index + 1) % len(self.players)
        self.guessed_this_round = set()
        self.intel_used_this_turn = set()

    def is_game_over(self):
        return len(self.ships) == 0 or not self.active or not self.players

    def remove_player(self, username):
        username = username.lower()
        if username in self.players:
            idx = self.players.index(username)
            del self.players[idx]
            if username in self.guesses:
                del self.guesses[username]
            if username in self.raffle_hits:
                del self.raffle_hits[username]
            if idx <= self.player_turn_index and self.player_turn_index > 0:
                self.player_turn_index -= 1
            if not self.players:
                self.active = False