import json
import os
import random
from typing import List, Dict, Optional


class RaffleManager:
    def __init__(self, filename: str):
        self.filename = filename
        self.state = {
            "raffle_active": False,
            "daily_entry_amount": 1,
            "raffle_id": None,
            "temporary_grants": {},
            "persistent_grants": {},
            "entries": {},
            "number_to_user": {}
        }
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                self.state = json.load(f)

    def save(self):
        with open(self.filename, "w") as f:
            json.dump(self.state, f, indent=2)

    def open_raffle(self, entry_amount: int, raffle_id: str):
        self.state.update({
            "raffle_active": True,
            "daily_entry_amount": entry_amount,
            "raffle_id": raffle_id,
            "temporary_grants": {},
            "entries": {},
            "number_to_user": {}
        })
        self.save()

    def close_raffle(self):
        self.state["raffle_active"] = False
        self.state["temporary_grants"] = {}
        self.save()

    def grant_daily_entry(self, username: str):
        if not self.state["raffle_active"]:
            return False
        if username not in self.state["temporary_grants"]:
            self.state["temporary_grants"][username] = self.state["daily_entry_amount"]
            self.save()
            return True
        return False

    def grant_persistent_entries(self, username: str, count: int):
        user_data = self.state["persistent_grants"].setdefault(username, {"total": 0, "redeemed": 0})
        user_data["total"] += count
        self.save()

    def available_entries(self, username: str) -> int:
        temp = self.state["temporary_grants"].get(username, 0)
        persistent = self.state["persistent_grants"].get(username, {"total": 0, "redeemed": 0})
        return temp + (persistent["total"] - persistent["redeemed"])

    def redeem_entries(self, username: str, numbers: List[str]) -> bool:
        if len(numbers) > self.available_entries(username):
            return False
        for number in numbers:
            if number in self.state["number_to_user"]:
                return False  # Duplicate number
        for number in numbers:
            self.state["number_to_user"][number] = username
            self.state["entries"].setdefault(username, []).append(number)
            if self.state["temporary_grants"].get(username, 0) > 0:
                self.state["temporary_grants"][username] -= 1
            else:
                self.state["persistent_grants"][username]["redeemed"] += 1
        self.save()
        return True

    def draw_winner(self) -> Optional[str]:
        if not self.state["number_to_user"]:
            return None
        number = random.choice(list(self.state["number_to_user"].keys()))
        winner = self.state["number_to_user"][number]
        self.open_raffle(self.state["daily_entry_amount"], f"{self.state['raffle_id']}_next")
        return f"🎉 Winner: {winner} with number {number}"

    def get_user_entries(self, username: str) -> List[str]:
        return self.state["entries"].get(username, [])

    def get_summary(self) -> Dict[str, int]:
        return {user: len(entries) for user, entries in self.state["entries"].items()}
