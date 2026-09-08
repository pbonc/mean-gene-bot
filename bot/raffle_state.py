import json
import os
from types import MappingProxyType


class SimpleRaffleState:
    """Read-only legacy projection for raffle odds.

    All writes belong to commands.raffle_cog.SimpleRaffleState. Loading this
    projection never creates, repairs, or saves a state file.
    """

    def __init__(self, state_file):
        self.state_file = state_file
        self.entries = MappingProxyType({})
        self.picks = MappingProxyType({})
        self.prize = None
        self.load()

    def load(self):
        data = {}
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        self.entries = MappingProxyType(dict(data.get("entries", {})))
        self.picks = MappingProxyType(dict(data.get("picks", {})))
        self.prize = data.get("prize")

    def available_entries(self, user):
        return self.entries.get(user, 0)

    def user_picks(self, user):
        return sorted([num for num, u in self.picks.items() if u == user], key=int)

    def all_picks(self):
        return sorted(self.picks.items(), key=lambda item: int(item[0]))
