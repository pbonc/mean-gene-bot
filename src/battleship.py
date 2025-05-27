import random

class BattleshipGame:
    def __init__(self, num_ships=5, test_mode=False):
        self.num_ships = num_ships
        self.test_mode = test_mode
        self.players = []
        self.active = False
        self.board = set()
        self.hits = set()
        self.turn_index = 0
        self.guessed_this_turn = set()
        self.intel_this_turn = set()

    def register_player(self, username):
        username = username.lower()
        if username not in self.players:
            self.players.append(username)

    def start_game(self):
        self.active = True
        self.board = self.generate_board()
        self.hits = set()
        self.turn_index = 0
        self.guessed_this_turn = set()
        self.intel_this_turn = set()

    def generate_board(self):
        cells = [f"{chr(r)}{c}" for r in range(ord('A'), ord('J')+1) for c in range(1, 11)]
        return set(random.sample(cells, self.num_ships))

    def get_current_player(self):
        if not self.players:
            return None
        return self.players[self.turn_index % len(self.players)]

    def guess(self, username, cell):
        username = username.lower()
        cell = cell.upper()
        if cell not in [f"{chr(r)}{c}" for r in range(ord('A'), ord('J')+1) for c in range(1, 11)]:
            return "Invalid", False, []
        if cell in self.hits:
            return "Already guessed", False, self.get_nearby_open_cells(cell)
        hit = cell in self.board
        if hit:
            self.hits.add(cell)
        return "Hit" if hit else "Miss", hit, []

    def is_game_over(self):
        return self.active and len(self.hits) >= self.num_ships

    def mark_guessed(self, username):
        self.guessed_this_turn.add(username.lower())

    def has_guessed(self, username):
        return username.lower() in self.guessed_this_turn

    def has_used_intel(self, username):
        return username.lower() in self.intel_this_turn

    def mark_intel(self, username):
        self.intel_this_turn.add(username.lower())

    def next_turn(self):
        self.turn_index = (self.turn_index + 1) % len(self.players)
        self.guessed_this_turn = set()
        self.intel_this_turn = set()

    def get_random_open_cells(self, n=5):
        all_cells = [f"{chr(r)}{c}" for r in range(ord('A'), ord('J')+1) for c in range(1, 11)]
        open_cells = [cell for cell in all_cells if cell not in self.hits]
        return random.sample(open_cells, min(n, len(open_cells)))

    def get_nearby_open_cells(self, cell):
        # Simple: return up to 3 random open cells (not already guessed)
        all_cells = [f"{chr(r)}{c}" for r in range(ord('A'), ord('J')+1) for c in range(1, 11)]
        open_cells = [c for c in all_cells if c not in self.hits and c != cell]
        return random.sample(open_cells, min(3, len(open_cells)))