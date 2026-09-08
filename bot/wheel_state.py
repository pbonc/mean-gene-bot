"""Authoritative Wheel persistence and narrowly scoped state operations."""
import json
import os
import random
import re
import copy
import tempfile
from functools import wraps

WHEEL_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "wheel_state.json")
MAX_SLOTS_PER_ADD = 500


class WheelOperationError(ValueError):
    """Validation, refresh or persistence failed before an operation committed."""


def staged(operation):
    """Publish only after success; synchronous operations never yield mid-commit.

    Work on a private copy so failed validation, loading or persistence cannot
    mutate live containers (including references held by readers).
    """
    @wraps(operation)
    def commit(self, *args, **kwargs):
        candidate = copy.deepcopy(self)
        try:
            if operation.__name__ != "load":
                reconciled = candidate._load()
            result = operation(candidate, *args, **kwargs)
            if operation.__name__ != "load" and reconciled and candidate._persisted_fields.get("slots") != candidate.slots:
                # No-op operations still commit a refreshed legacy reconciliation.
                candidate.save()
        except (OSError, ValueError, TypeError) as error:
            raise WheelOperationError(str(error)) from error
        self.__dict__.update(candidate.__dict__)
        return result
    return commit


def validated_count(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_SLOTS_PER_ADD:
        raise ValueError("Count must be an integer between 1 and 500.")
    return value


def validated_enabled(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ("on", "true", "yes", "1"):
            return True
        if value in ("off", "false", "no", "0"):
            return False
    raise ValueError("Use on or off.")


def validated_user(user):
    if not isinstance(user, str) or not user.strip().lstrip("@"):
        raise ValueError("A participant name is required.")
    return user.strip().lstrip("@").lower()


def normalize_hex_color(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value.startswith("#"):
        value = "#" + value
    return value.lower() if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else None


def validated_color(value):
    color = normalize_hex_color(value)
    if color is None:
        raise ValueError("Invalid color. Use a hex code like #ff33aa.")
    return color

class WheelState:
    def __init__(self, state_file=WHEEL_STATE_FILE):
        self.state_file = state_file
        self._persisted_fields = {}
        self.slots = {}
        self.scores = {}
        self.last_winner = None
        self.remove_on_win = False
        self.wheel_locked = False
        self.last_man_standing = False
        self.order = []
        self.colors = {}
        self.multiplier = 1
        self.manual_users = set()
        self.load()

    @staged
    def load(self, create_missing=True):
        if self._load() or (create_missing and not os.path.exists(self.state_file)):
            self.save()

    def _load(self):
        """Refresh a private candidate; return whether counts need persistence."""
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._persisted_fields = data.copy()
            self.slots = {k: int(v) for k, v in data.get("slots", {}).items() if int(v) > 0}
            self.scores = {k: int(v) for k, v in data.get("scores", {}).items() if int(v) >= 0}
            self.last_winner = data.get("last_winner", None)
            self.remove_on_win = bool(data.get("remove_on_win", False))
            self.wheel_locked = bool(data.get("wheel_locked", False))
            self.last_man_standing = bool(data.get("last_man_standing", False))
            self.order = [u for u in data.get("order", []) if u in self.slots]
            for u in sorted(self.slots.keys()):
                if u not in self.order:
                    self.order.append(u)
            self.colors = {k: v for k, v in data.get("colors", {}).items() if isinstance(v, str)}
            self.multiplier = validated_count(data.get("multiplier", 1))
            self.manual_users = {
                u for u in data.get("manual_users", []) if isinstance(u, str) and u in self.slots
            }
            if not self.wheel_locked and any(count != self.multiplier for count in self.slots.values()):
                self.slots = {user: self.multiplier for user in self.slots}
                return True
        return False

    def save(self):
        data = {
            **self._persisted_fields,
            "slots": self.slots,
            "scores": self.scores,
            "last_winner": self.last_winner,
            "remove_on_win": self.remove_on_win,
            "wheel_locked": self.wheel_locked,
            "last_man_standing": self.last_man_standing,
            "order": self.order,
            "colors": self.colors,
            "multiplier": self.multiplier,
            "manual_users": sorted(self.manual_users),
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                    dir=os.path.dirname(os.path.abspath(self.state_file)),
                    prefix=".wheel-", suffix=".tmp", delete=False) as f:
                temporary = f.name
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.state_file)
            self._persisted_fields = copy.deepcopy(data)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    @staged
    def add_slots(self, user, count=1, allow_multi=False, color=None, manual=False):
        user = validated_user(user)
        count = validated_count(count)
        if color is not None:
            color = validated_color(color)
        if self.wheel_locked or user in self.slots:
            return False
        self.slots = {name: self.multiplier for name in self.slots}
        self.slots[user] = self.multiplier
        if user not in self.order:
            self.order.append(user)
        if color:
            self.colors[user] = validated_color(color)
        if manual:
            self.manual_users.add(user)
        self.save()
        return True

    @staged
    def remove_user(self, user):
        user = validated_user(user)
        if user in self.slots:
            del self.slots[user]
            if user in self.order:
                self.order = [u for u in self.order if u != user]
            if user in self.manual_users:
                self.manual_users.discard(user)
            self.save()
            return True
        return False

    def join(self, user, color=None):
        """Join once, at the configured universal multiplier, only while unlocked."""
        return self.add_slots(user, color=color)

    @staged
    def set_all_counts(self, count):
        """While locked, replace remaining counts; unlocked, configure all joins too."""
        count = validated_count(count)
        self.slots = {user: count for user in self.slots}
        if not self.wheel_locked:
            self.multiplier = count
        self.save()

    @staged
    def set_color(self, user, color):
        user = validated_user(user)
        if user not in self.slots:
            return False
        self.colors[user] = validated_color(color)
        self.save()
        return True

    @staged
    def set_multiplier(self, multiplier):
        multiplier = validated_count(multiplier)
        self.multiplier = multiplier
        if not self.slots:
            self.save()
            return False
        updated = False
        for user in list(self.slots.keys()):
            if self.slots.get(user) != multiplier:
                self.slots[user] = multiplier
                updated = True
        self.save()
        return updated

    @staged
    def set_remove_on_win(self, enabled: bool):
        self.remove_on_win = validated_enabled(enabled)
        self.save()

    @staged
    def set_wheel_locked(self, enabled: bool):
        self.wheel_locked = validated_enabled(enabled)
        if not self.wheel_locked:
            self.slots = {user: self.multiplier for user in self.slots}
        self.save()

    @staged
    def set_last_man_standing(self, enabled: bool):
        self.last_man_standing = validated_enabled(enabled)
        self.save()

    @staged
    def reset(self):
        self.slots = {}
        self.scores = {}
        self.last_winner = None
        self.wheel_locked = False
        self.last_man_standing = False
        self.order = []
        self.colors = {}
        self.multiplier = 1
        self.manual_users = set()
        self.save()

    def build_slots_list(self):
        ordered_users = [u for u in self.order if u in self.slots]
        for u in sorted(self.slots.keys()):
            if u not in ordered_users:
                ordered_users.append(u)
        if not ordered_users:
            return []
        max_count = max(max(1, int(self.slots[u])) for u in ordered_users)
        slots_list = []
        for i in range(max_count):
            for u in ordered_users:
                if i < int(self.slots[u]):
                    slots_list.append(u)
        return slots_list

    @staged
    def spin(self):
        slots_list = self.build_slots_list()
        if not slots_list:
            return None, None, None
        if not self.wheel_locked and (self.remove_on_win or self.last_man_standing):
            raise WheelOperationError("Lock the wheel with !wheellock on before an elimination spin.")
        winner_index = random.randrange(len(slots_list))
        winner = slots_list[winner_index]
        self.last_winner = winner
        self.scores[winner] = self.scores.get(winner, 0) + 1
        if winner in self.slots:
            if self.last_man_standing:
                remaining = int(self.slots.get(winner, 0)) - 1
                if remaining > 0:
                    self.slots[winner] = remaining
                else:
                    del self.slots[winner]
                    if winner in self.order:
                        self.order = [u for u in self.order if u != winner]
                    if winner in self.manual_users:
                        self.manual_users.discard(winner)
            elif self.remove_on_win:
                remaining = int(self.slots.get(winner, 0)) - 1
                if remaining > 0:
                    self.slots[winner] = remaining
                else:
                    del self.slots[winner]
                    if winner in self.order:
                        self.order = [u for u in self.order if u != winner]
                    if winner in self.manual_users:
                        self.manual_users.discard(winner)
        self.save()
        return winner, winner_index, slots_list

    def get_state_payload(self):
        slots_payload = [
            {"name": name, "count": int(count), "color": self.colors.get(name)}
            for name, count in [(u, self.slots[u]) for u in self.order if u in self.slots]
        ]
        scores_payload = [
            {"name": name, "score": int(score)}
            for name, score in sorted(self.scores.items(), key=lambda x: (-x[1], x[0]))
        ]
        total_slots = sum(int(c) for c in self.slots.values())
        return {
            "type": "wheel_state",
            "slots": slots_payload,
            "scores": scores_payload,
            "total_slots": total_slots,
            "last_winner": self.last_winner,
            "remove_on_win": self.remove_on_win,
            "wheel_locked": self.wheel_locked,
            "last_man_standing": self.last_man_standing,
        }

_states = {}


def get_wheel_state(state_file=None):
    """Share the live state between Twitch and overlay controls in this process."""
    path = os.path.normcase(os.path.abspath(state_file or WHEEL_STATE_FILE))
    if path not in _states:
        _states[path] = WheelState(path)
    return _states[path]


def apply_wheel_control(state, action, value):
    """Adapt the existing WebSocket action schema without redefining it."""
    if action == "set_multiplier":
        state.set_multiplier(value)
    elif action == "set_remove_on_win":
        state.set_remove_on_win(value)
    else:
        return False
    return True
