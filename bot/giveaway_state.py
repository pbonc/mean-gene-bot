import json
import os
import random
import re
from datetime import datetime, timezone


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(PROJECT_ROOT, "data", "giveaway_state.json")


def normalize_username(value):
    return str(value or "").strip().lstrip("@").lower()


def matches_entry(content, entry_phrase):
    content = str(content or "").strip()
    phrase = str(entry_phrase or "").strip()
    if not content or not phrase:
        return False
    if phrase.startswith("!"):
        return content.split(maxsplit=1)[0].casefold() == phrase.casefold()
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", content, re.I))


class GiveawayState:
    def __init__(self, state_file=STATE_FILE, rng=None):
        self.state_file = state_file
        self.rng = rng or random.SystemRandom()
        self.state = self._load()

    def _empty(self):
        return {
            "is_open": False,
            "prize": None,
            "entry_phrase": None,
            "entrants": [],
            "winner": None,
            "draw_id": 0,
            "opened_at": None,
            "closed_at": None,
            "updated_at": None,
        }

    def _load(self):
        state = self._empty()
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                state.update(data)
        except (OSError, ValueError, TypeError):
            pass
        state["entrants"] = list(dict.fromkeys(
            normalize_username(name) for name in state.get("entrants", []) if normalize_username(name)
        ))
        return state

    def save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        temporary = self.state_file + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2)
        os.replace(temporary, self.state_file)

    def open(self, prize, entry_phrase):
        prize = str(prize or "").strip()
        entry_phrase = str(entry_phrase or "").strip()
        if not prize or not entry_phrase:
            raise ValueError('Usage: !giveaway open "prize" "word or !sfx"')
        if len(prize) > 160:
            raise ValueError("Giveaway prize descriptions must be 160 characters or fewer.")
        if len(entry_phrase) > 80:
            raise ValueError("Giveaway entry phrases must be 80 characters or fewer.")
        self.state.update({
            "is_open": True,
            "prize": prize,
            "entry_phrase": entry_phrase,
            "entrants": [],
            "winner": None,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "closed_at": None,
        })
        self.save()

    def close(self):
        if not self.state.get("prize"):
            raise ValueError("No giveaway has been opened.")
        self.state["is_open"] = False
        self.state["closed_at"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def enter(self, username, content):
        if not self.state.get("is_open") or not matches_entry(content, self.state.get("entry_phrase")):
            return False
        username = normalize_username(username)
        if not username or username in self.state["entrants"]:
            return False
        self.state["entrants"].append(username)
        self.save()
        return True

    def draw(self):
        if self.state.get("is_open"):
            raise ValueError("Close the giveaway before drawing.")
        if not self.state.get("entrants"):
            raise ValueError("Nobody has entered this giveaway.")
        winner = self.rng.choice(self.state["entrants"])
        self.state["winner"] = winner
        self.state["draw_id"] = int(self.state.get("draw_id") or 0) + 1
        self.save()
        return winner

    def payload(self, animate=False):
        return {
            "type": "giveaway_state",
            "is_open": bool(self.state.get("is_open")),
            "prize": self.state.get("prize"),
            "entry_phrase": self.state.get("entry_phrase"),
            "entrants": list(self.state.get("entrants", [])),
            "winner": self.state.get("winner"),
            "draw_id": int(self.state.get("draw_id") or 0),
            "animate": bool(animate),
        }
