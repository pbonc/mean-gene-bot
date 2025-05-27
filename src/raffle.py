import json
import os
import random
import asyncio
import logging

RAFFLE_JSON_PATH = "raffle_state.json"

class RaffleState:
    def __init__(self, path=RAFFLE_JSON_PATH):
        self.path = path
        self.state = {
            "entries": {},  # {username: int}
            "picks": {},    # {number_str: username}
            "is_open": False,
            "entries_per_chat": 1,
            "nuclear_key": {
                "closeraffle": [],
                "drawraffle": [],
                "clearraffle": []
            }
        }
        self.chat_awarded = set()
        self.load()

    def load(self):
        try:
            with open(self.path, "r") as f:
                self.state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.save()

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.state, f, indent=2)

    # --- Entry Logic ---
    def add_entries(self, username: str, amount: int):
        self.state["entries"][username] = self.state["entries"].get(username, 0) + amount
        self.save()

    def remove_entries(self, username: str, amount: int):
        self.state["entries"][username] = max(self.state["entries"].get(username, 0) - amount, 0)
        self.save()

    def set_entries(self, username: str, amount: int):
        self.state["entries"][username] = amount
        self.save()

    def get_entries(self, username: str) -> int:
        return self.state["entries"].get(username, 0)

    # --- Picks Logic ---
    def pick_numbers(self, username: str, numbers):
        if self.get_entries(username) < len(numbers):
            return False, "Not enough numbers left to register all picks."
        for n in numbers:
            if n in self.state["picks"]:
                return False, "One or more numbers are already taken."
        for n in numbers:
            self.state["picks"][n] = username
        self.remove_entries(username, len(numbers))
        self.save()
        return True, numbers

    def get_user_picks(self, username: str):
        return [n for n, u in self.state["picks"].items() if u == username]

    def clear_picks(self):
        self.state["picks"] = {}
        self.save()

    def pick_random_numbers(self, username: str, count: int):
        available_numbers = [f"{i:03d}" for i in range(1000) if f"{i:03d}" not in self.state["picks"]]
        if len(available_numbers) < count or self.get_entries(username) < count:
            return False, None
        chosen = random.sample(available_numbers, count)
        ok, _ = self.pick_numbers(username, chosen)
        if ok:
            return True, chosen
        return False, None

    # --- Batch/Series Picks ---
    def pick_series(self, username: str, start: int, count: int, direction: str):
        numbers = []
        current = start
        for _ in range(count):
            num_str = f"{current:03d}"
            if num_str in self.state["picks"]:
                return False, None
            numbers.append(num_str)
            if direction == "+":
                current = (current + 1) % 1000
            else:
                current = (current - 1) % 1000
        if self.get_entries(username) < count:
            return False, None
        ok, _ = self.pick_numbers(username, numbers)
        if ok:
            return True, numbers
        return False, None

    # --- Raffle State ---
    def open_raffle(self, entries_per_chat: int):
        self.state["is_open"] = True
        self.state["entries_per_chat"] = entries_per_chat
        self.chat_awarded = set()
        self.save()

    def close_raffle(self):
        self.state["is_open"] = False
        self.save()

    def is_open(self) -> bool:
        return self.state.get("is_open", False)

    # --- Nuclear Key ---
    def nuclear_attempt(self, action: str, username: str) -> bool:
        if action not in self.state["nuclear_key"]:
            self.state["nuclear_key"][action] = []
        if username not in self.state["nuclear_key"][action]:
            self.state["nuclear_key"][action].append(username)
        self.save()
        return len(self.state["nuclear_key"][action]) >= 2

    def clear_nuclear(self, action: str):
        self.state["nuclear_key"][action] = []
        self.save()

    # --- Draw ---
    def draw(self):
        digits = [random.randint(0, 9) for _ in range(3)]
        number = "".join(str(d) for d in digits)
        winner = self.state["picks"].get(number)
        return digits, number, winner

    def test_draw(self):
        number = f"{random.randint(0, 999):03d}"
        winner = self.state["picks"].get(number)
        return number, winner

    def get_pick_owner(self, number: str):
        return self.state["picks"].get(number)

    def reset_chat_awarded(self):
        self.chat_awarded = set()

    def award_chat(self, username: str):
        self.chat_awarded.add(username)

    def has_chat_award(self, username: str):
        return username in self.chat_awarded