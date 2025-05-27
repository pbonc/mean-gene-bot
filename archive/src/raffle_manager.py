import json
import os

class RaffleManager:
    def __init__(self, filename="data/entries.json"):
        self.filename = filename
        self.entries = {}
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except Exception:
                self.entries = {}
        else:
            self.entries = {}

    def save(self):
        with open(self.filename, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2)

    async def award_entries(self, username, amount, channel):
        username = username.lower()
        self.entries[username] = self.entries.get(username, 0) + amount
        self.save()
        if amount == 1:
            msg = f"Welcome in, {username}! Enjoy a complimentary entry in the raffle."
        else:
            msg = f"Welcome in, {username}! Enjoy {amount} complimentary entries in the raffle."
        await channel.send(msg)
        print(f"[DEBUG] {username} was awarded {amount} entry(ies). Now has {self.entries[username]} total.")

    def get_entries(self, username):
        return self.entries.get(username.lower(), 0)

    def use_entry(self, username):
        username = username.lower()
        if self.get_entries(username) > 0:
            self.entries[username] -= 1
            self.save()
            print(f"[DEBUG] {username} used an entry. Remaining: {self.entries[username]}")
            return True
        return False

    def reset(self):
        self.entries = {}
        self.save()

    def all_entries(self):
        return dict(self.entries)