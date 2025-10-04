import json
import os

class SimpleRaffleState:
    def __init__(self, state_file):
        self.state_file = state_file
        self.entries = {}  # user -> available entries (int)
        self.picks = {}    # 'NNN' -> user
        self.prize = None
        self.load()

    def load(self):
        if os.path.exists(self.state_file):
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.entries = data.get("entries", {})
            self.picks = data.get("picks", {})
            self.prize = data.get("prize", None)
        else:
            self.save()

    def save(self):
        # Save picks sorted by number for readability
        sorted_picks = {k: self.picks[k] for k in sorted(self.picks, key=lambda x: int(x))}
        data = {"entries": self.entries, "picks": sorted_picks}
        if self.prize is not None:
            data["prize"] = self.prize
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def set_prize(self, prize):
        self.prize = prize
        self.save()

    def add_entries(self, user, count):
        self.entries[user] = self.entries.get(user, 0) + count
        self.save()

    def use_entry(self, user):
        if self.entries.get(user, 0) > 0:
            self.entries[user] -= 1
            self.save()
            return True
        return False

    def pick_number(self, user, number):
        # Validate: must be a 3-digit string, not already picked
        if not (isinstance(number, str) and number.isdigit() and len(number) == 3 and 0 <= int(number) <= 999):
            return False, "Pick must be a three-digit number (e.g., 007, 123)."
        if number in self.picks:
            return False, f"{number} is already picked."
        if not self.use_entry(user):
            return False, "No entries left."
        self.picks[number] = user
        self.save()
        return True, f"Pick accepted: {number}"

    def reset(self):
        self.entries = {}
        self.picks = {}
        self.save()

    def available_entries(self, user):
        return self.entries.get(user, 0)

    def user_picks(self, user):
        return sorted([num for num, u in self.picks.items() if u == user], key=lambda x: int(x))

    def all_picks(self):
        # Returns sorted list of (number, user) tuples
        return sorted(self.picks.items(), key=lambda x: int(x[0]))