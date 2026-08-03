import json
import os
import random
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STATE_FILE = os.path.join(DATA_DIR, "bittleships_state.json")
BOARD_SIZE = 10
MAX_SHIPS = BOARD_SIZE * BOARD_SIZE
COORDINATE_RE = re.compile(r"^([A-Ja-j])\s*(10|[1-9])$")
CLASSIC_FLEET = (
    ("Destroyer", 2),
    ("Submarine", 3),
    ("Cruiser", 3),
    ("Battleship", 4),
    ("Aircraft Carrier", 5),
)
CLASSIC_TURN_SECONDS = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> Dict[str, Any]:
    return {
        "admiral": None,
        "mode": "single",
        "phase": "idle",
        "active": False,
        "ship_count": 0,
        "ships": [],
        "shots": {},
        "revealed": {},
        "hits": 0,
        "misses": 0,
        "classic": {},
        "suspended_game": None,
        "last_event": "Waiting for an admiral.",
        "started_at": None,
        "updated_at": None,
    }


def normalize_username(username: str) -> str:
    return str(username or "").strip().lstrip("@").lower()


def parse_coordinate(value: str) -> Optional[str]:
    match = COORDINATE_RE.fullmatch(str(value or "").strip())
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2)}"


def _all_coordinates():
    return [f"{letter}{number}" for letter in "ABCDEFGHIJ" for number in range(1, 11)]


def _coordinate(column: int, row: int) -> str:
    return f"{chr(ord('A') + column)}{row + 1}"


class BittleshipsManager:
    def __init__(self, state_file: str = STATE_FILE, rng=None):
        self.state_file = state_file
        self.rng = rng or random.SystemRandom()
        self.state = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_file):
            return _empty_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as handle:
                saved = json.load(handle)
            if not isinstance(saved, dict):
                return _empty_state()
            state = _empty_state()
            state.update(saved)
            return state
        except (OSError, ValueError, TypeError):
            return _empty_state()

    def reload(self) -> None:
        self.state = self._load()

    def save(self) -> None:
        directory = os.path.dirname(self.state_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self.state["updated_at"] = _now_iso()
        temporary = f"{self.state_file}.tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2)
        os.replace(temporary, self.state_file)

    @property
    def admiral(self) -> Optional[str]:
        return self.state.get("admiral")

    def set_admiral(self, username: str) -> str:
        target = normalize_username(username)
        if not target:
            raise ValueError("Admiral username cannot be empty.")
        previous = self.admiral
        self.state["admiral"] = target
        shots = self.state.setdefault("shots", {})
        shots.pop(target, None)
        if previous != target:
            self.state["last_event"] = f"@{target} is now the admiral."
        self.save()
        return target

    def clear_admiral(self) -> None:
        self.state["admiral"] = None
        self.state["last_event"] = "The admiral position is vacant."
        self.save()

    def start_game(self, ship_count: int) -> None:
        if not self.admiral:
            raise ValueError("Assign an admiral before starting a game.")
        if ship_count < 1 or ship_count > MAX_SHIPS:
            raise ValueError(f"Ship count must be between 1 and {MAX_SHIPS}.")
        self.state.update({
            "mode": "single",
            "phase": "playing",
            "active": True,
            "ship_count": ship_count,
            "ships": sorted(self.rng.sample(_all_coordinates(), ship_count)),
            "shots": {},
            "revealed": {},
            "hits": 0,
            "misses": 0,
            "classic": {},
            "suspended_game": None,
            "last_event": f"Battle started with {ship_count} hidden ship{'s' if ship_count != 1 else ''}.",
            "started_at": _now_iso(),
        })
        self.save()

    def stop_game(self) -> None:
        self.state["active"] = False
        self.state["phase"] = "ended"
        self.state["shots"] = {}
        self.state["last_event"] = "Battle stopped by command."
        self.save()

    def grant_shots(self, username: str, count: int = 1) -> int:
        target = normalize_username(username)
        if not self.state.get("active"):
            raise ValueError("No Bittleships game is active.")
        if not target:
            raise ValueError("Player username cannot be empty.")
        if target == self.admiral:
            raise ValueError("The admiral cannot receive or fire shots.")
        if count < 1 or count > 20:
            raise ValueError("Grant between 1 and 20 shots at a time.")
        shots = self.state.setdefault("shots", {})
        shots[target] = int(shots.get(target, 0)) + count
        self.state["last_event"] = f"@{target} received {count} shot{'s' if count != 1 else ''}."
        self.save()
        return shots[target]

    def fire(self, username: str, coordinate: str) -> Tuple[str, int, bool]:
        if self.state.get("mode") == "classic":
            raise ValueError("Classic mode uses the turn order.")
        player = normalize_username(username)
        cell = parse_coordinate(coordinate)
        if not self.state.get("active"):
            raise ValueError("No Bittleships game is active.")
        if player == self.admiral:
            raise ValueError("The admiral cannot play while commanding the fleet.")
        if not cell:
            raise ValueError("Invalid coordinate. Use A1 through J10.")
        revealed = self.state.setdefault("revealed", {})
        if cell in revealed:
            raise ValueError(f"{cell} has already been fired on.")
        shots = self.state.setdefault("shots", {})
        remaining = int(shots.get(player, 0))
        if remaining <= 0:
            raise ValueError("You do not have a shot. The admiral must grant one.")

        remaining -= 1
        if remaining:
            shots[player] = remaining
        else:
            shots.pop(player, None)

        hit = cell in set(self.state.get("ships", []))
        result = "hit" if hit else "miss"
        revealed[cell] = {
            "result": result,
            "player": player,
            "fired_at": _now_iso(),
        }
        counter = "hits" if hit else "misses"
        self.state[counter] = int(self.state.get(counter, 0)) + 1
        won = int(self.state["hits"]) >= int(self.state.get("ship_count", 0))
        if won:
            self.state["active"] = False
            self.state["shots"] = {}
            self.state["last_event"] = f"@{player} hit {cell}. All enemy ships have been sunk!"
        else:
            self.state["last_event"] = f"@{player} fired at {cell}: {result.upper()}!"
        self.save()
        return result, remaining, won

    def _place_classic_fleet(self) -> List[Dict[str, Any]]:
        for _ in range(500):
            occupied = set()
            fleet = []
            for name, length in CLASSIC_FLEET:
                placed = False
                candidates = []
                for horizontal in (True, False):
                    max_column = BOARD_SIZE - length if horizontal else BOARD_SIZE - 1
                    max_row = BOARD_SIZE - 1 if horizontal else BOARD_SIZE - length
                    for column in range(max_column + 1):
                        for row in range(max_row + 1):
                            cells = [
                                _coordinate(
                                    column + (offset if horizontal else 0),
                                    row + (0 if horizontal else offset),
                                )
                                for offset in range(length)
                            ]
                            if occupied.isdisjoint(cells):
                                candidates.append(cells)
                if candidates:
                    cells = self.rng.choice(candidates)
                    occupied.update(cells)
                    fleet.append({"name": name, "length": length, "cells": cells})
                    placed = True
                if not placed:
                    break
            if len(fleet) == len(CLASSIC_FLEET):
                return fleet
        raise RuntimeError("Unable to place the classic fleet.")

    def start_classic_join(self, minutes: int, fighter_enabled: bool = False) -> None:
        if minutes < 1 or minutes > 10:
            raise ValueError("Classic join time must be between 1 and 10 minutes.")
        fleet = self._place_classic_fleet()
        occupied = {cell for ship in fleet for cell in ship["cells"]}
        fighter_cell = None
        if fighter_enabled:
            fighter_cell = self.rng.choice(
                [cell for cell in _all_coordinates() if cell not in occupied]
            )
        now = datetime.now(timezone.utc)
        if self.state.get("mode") != "classic":
            self.state["suspended_game"] = {
                key: deepcopy(self.state.get(key))
                for key in (
                    "mode",
                    "phase",
                    "active",
                    "ship_count",
                    "ships",
                    "shots",
                    "revealed",
                    "hits",
                    "misses",
                    "classic",
                    "last_event",
                    "started_at",
                )
            }
        self.state.update({
            "mode": "classic",
            "phase": "joining",
            "active": False,
            "ship_count": len(fleet),
            "ships": fleet,
            "shots": {},
            "revealed": {},
            "hits": 0,
            "misses": 0,
            "started_at": None,
            "classic": {
                "join_deadline": (now + timedelta(minutes=minutes)).isoformat(),
                "players": [],
                "pending_players": [],
                "turn_order": [],
                "turn_index": 0,
                "round": 0,
                "turn_deadline": None,
                "scores": {},
                "sunk": [],
                "fighter_enabled": bool(fighter_enabled),
                "fighter_alive": bool(fighter_enabled),
                "fighter_cell": fighter_cell,
                "sudden_death": False,
                "sudden_death_players": [],
                "winner": None,
            },
            "last_event": f"Classic mode signup is open for {minutes} minute{'s' if minutes != 1 else ''}.",
        })
        self.save()

    def restore_suspended_game(self, message: Optional[str] = None) -> bool:
        suspended = self.state.get("suspended_game")
        if not isinstance(suspended, dict):
            return False
        admiral = self.admiral
        restored = _empty_state()
        restored.update(deepcopy(suspended))
        restored["admiral"] = admiral
        restored["suspended_game"] = None
        if message:
            restored["last_event"] = message
        self.state = restored
        self.save()
        return True

    def join_classic(self, username: str) -> int:
        player = normalize_username(username)
        classic = self.state.get("classic", {})
        phase = self.state.get("phase")
        if self.state.get("mode") != "classic" or phase not in ("joining", "playing"):
            raise ValueError("Classic mode is not accepting players.")
        if phase == "playing" and classic.get("sudden_death"):
            raise ValueError("Classic mode is in sudden death and is not accepting players.")
        if phase == "joining":
            deadline = datetime.fromisoformat(classic["join_deadline"])
            if datetime.now(timezone.utc) >= deadline:
                raise ValueError("The Classic join window has closed.")
        if not player:
            raise ValueError("Unable to identify the joining player.")
        players = classic.setdefault("players", [])
        if player in players:
            raise ValueError("You have already joined Classic mode.")
        players.append(player)
        classic.setdefault("scores", {})[player] = {"hits": 0, "sinks": 0, "points": 0}
        if phase == "playing":
            if self.state.get("revealed"):
                classic.setdefault("pending_players", []).append(player)
                self.state["last_event"] = (
                    f"@{player} joined Classic mode and will enter at the end of the next round."
                )
            else:
                classic.setdefault("turn_order", []).append(player)
                self.state["last_event"] = (
                    f"@{player} joined Classic mode before the first shot."
                )
        else:
            self.state["last_event"] = f"@{player} joined Classic mode."
        self.save()
        return len(players)

    def begin_classic(self) -> List[str]:
        classic = self.state.get("classic", {})
        if self.state.get("mode") != "classic" or self.state.get("phase") != "joining":
            raise ValueError("Classic signup is not open.")
        players = list(classic.get("players", []))
        if not players:
            self.state["phase"] = "ended"
            self.state["last_event"] = "Classic mode ended because nobody joined."
            self.save()
            return []
        self.rng.shuffle(players)
        classic["turn_order"] = players
        classic["turn_index"] = 0
        classic["round"] = 1
        classic["turn_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=CLASSIC_TURN_SECONDS)
        ).isoformat()
        self.state["phase"] = "playing"
        self.state["active"] = True
        self.state["started_at"] = _now_iso()
        self.state["last_event"] = f"Classic battle started. @{players[0]} fires first."
        self.save()
        return players

    def _move_fighter(self) -> Optional[str]:
        classic = self.state.get("classic", {})
        if not classic.get("fighter_enabled") or not classic.get("fighter_alive"):
            return None
        occupied = {cell for ship in self.state.get("ships", []) for cell in ship["cells"]}
        revealed = set(self.state.get("revealed", {}))
        current = classic.get("fighter_cell")
        choices = [
            cell for cell in _all_coordinates()
            if cell not in occupied and cell not in revealed and cell != current
        ]
        if not choices:
            classic["fighter_alive"] = False
            classic["fighter_cell"] = None
            return None
        classic["fighter_cell"] = self.rng.choice(choices)
        return classic["fighter_cell"]

    def _launch_sudden_death_fighter(self) -> str:
        classic = self.state["classic"]
        occupied = {cell for ship in self.state.get("ships", []) for cell in ship["cells"]}
        revealed = set(self.state.get("revealed", {}))
        choices = [
            cell for cell in _all_coordinates()
            if cell not in occupied and cell not in revealed
        ]
        if not choices:
            raise RuntimeError("No unrevealed cell is available for sudden death.")
        classic["fighter_enabled"] = True
        classic["fighter_alive"] = True
        classic["fighter_cell"] = self.rng.choice(choices)
        return classic["fighter_cell"]

    def _begin_sudden_death(self, tied_players: List[str], last_player: str) -> None:
        classic = self.state["classic"]
        original_order = list(classic["turn_order"])
        tied = set(tied_players)
        order = [player for player in original_order if player in tied]
        if not order:
            order = list(tied_players)
        try:
            last_index = original_order.index(last_player)
        except ValueError:
            last_index = -1
        next_player = next(
            (
                original_order[(last_index + offset) % len(original_order)]
                for offset in range(1, len(original_order) + 1)
                if original_order[(last_index + offset) % len(original_order)] in tied
            ),
            order[0],
        )
        next_index = order.index(next_player)
        classic["sudden_death"] = True
        classic["sudden_death_players"] = order
        classic["turn_order"] = order
        classic["turn_index"] = next_index
        classic["pending_players"] = []
        classic["turn_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=CLASSIC_TURN_SECONDS)
        ).isoformat()
        if not classic.get("fighter_alive") or not classic.get("fighter_cell"):
            self._launch_sudden_death_fighter()

    def _advance_classic_turn(self) -> bool:
        classic = self.state["classic"]
        order = classic["turn_order"]
        classic["turn_index"] += 1
        new_round = classic["turn_index"] >= len(order)
        if new_round:
            classic["turn_index"] = 0
            classic["round"] += 1
            pending_players = classic.setdefault("pending_players", [])
            if pending_players:
                order.extend(pending_players)
                pending_players.clear()
            self._move_fighter()
        classic["turn_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=CLASSIC_TURN_SECONDS)
        ).isoformat()
        return new_round

    def classic_fire(self, username: str, coordinate: str) -> Dict[str, Any]:
        player = normalize_username(username)
        cell = parse_coordinate(coordinate)
        classic = self.state.get("classic", {})
        if self.state.get("mode") != "classic" or self.state.get("phase") != "playing":
            raise ValueError("A Classic game is not currently playing.")
        current_player = classic["turn_order"][classic["turn_index"]]
        if player != current_player:
            raise ValueError(f"It is @{current_player}'s turn.")
        if not cell:
            raise ValueError("Invalid coordinate. Use A1 through J10.")
        revealed = self.state.setdefault("revealed", {})
        if cell in revealed:
            raise ValueError(f"{cell} has already been fired on.")

        target_ship = next(
            (ship for ship in self.state.get("ships", []) if cell in ship["cells"]),
            None,
        )
        fighter_hit = bool(
            classic.get("fighter_alive") and cell == classic.get("fighter_cell")
        )
        hit = target_ship is not None or fighter_hit
        sunk_name = None
        bonus = 0
        if fighter_hit:
            sunk_name = "Fighter"
            bonus = 1
            classic["fighter_alive"] = False
            classic["fighter_cell"] = None
        elif target_ship:
            previously_hit = {
                coordinate
                for coordinate, record in revealed.items()
                if record.get("target") == target_ship["name"]
            }
            if set(target_ship["cells"]).issubset(previously_hit | {cell}):
                sunk_name = target_ship["name"]
                if sunk_name not in classic["sunk"]:
                    classic["sunk"].append(sunk_name)
                    bonus = 1

        result = "hit" if hit else "miss"
        revealed[cell] = {
            "result": result,
            "target": "Fighter" if fighter_hit else (target_ship["name"] if target_ship else None),
            "player": player,
            "fired_at": _now_iso(),
        }
        self.state["hits" if hit else "misses"] += 1
        score = classic["scores"][player]
        if hit:
            score["hits"] += 1
            score["points"] += 1 + bonus
        if bonus:
            score["sinks"] += 1

        fleet_destroyed = len(classic["sunk"]) == len(CLASSIC_FLEET)
        sudden_death = bool(classic.get("sudden_death"))
        sudden_death_started = False
        winner = None
        winner_score = None
        won = sudden_death and fighter_hit
        new_round = False
        if fleet_destroyed and not sudden_death:
            top_score = max(record["points"] for record in classic["scores"].values())
            tied_players = [
                name
                for name, record in classic["scores"].items()
                if record["points"] == top_score
            ]
            if len(tied_players) > 1:
                self._begin_sudden_death(tied_players, player)
                sudden_death_started = True
            else:
                won = True
                winner = tied_players[0]
                winner_score = classic["scores"][winner]["points"]
        elif won:
            winner = player
            winner_score = score["points"]

        if won:
            self.state["active"] = False
            self.state["phase"] = "ended"
            classic["turn_deadline"] = None
            classic["winner"] = winner
        elif not sudden_death_started:
            new_round = self._advance_classic_turn()
        next_player = None if won else classic["turn_order"][classic["turn_index"]]
        event = f"@{player} fired at {cell}: {result.upper()}!"
        if sunk_name:
            event += f" {sunk_name} destroyed! Bonus point!"
        if sudden_death_started:
            event += " The fleet is sunk with the lead tied; fighter sudden death begins!"
        elif won and sudden_death:
            event += f" @{player} destroyed the sudden-death fighter and wins!"
        elif won:
            event += " The fleet has been sunk!"
        elif new_round and classic.get("fighter_alive"):
            event += f" Round {classic['round']} begins; the fighter has moved."
        self.state["last_event"] = event
        self.save()
        return {
            "result": result,
            "sunk": sunk_name,
            "bonus": bonus,
            "won": won,
            "winner": winner,
            "winner_score": winner_score,
            "sudden_death": bool(classic.get("sudden_death")),
            "sudden_death_started": sudden_death_started,
            "new_round": new_round,
            "next_player": next_player,
            "round": classic["round"],
            "score": dict(score),
        }

    def skip_classic_turn(
        self,
        expected_player: Optional[str] = None,
        expected_deadline: Optional[str] = None,
    ) -> str:
        classic = self.state.get("classic", {})
        if self.state.get("mode") != "classic" or self.state.get("phase") != "playing":
            raise ValueError("A Classic game is not currently playing.")
        skipped = classic["turn_order"][classic["turn_index"]]
        if expected_player and skipped != normalize_username(expected_player):
            raise ValueError("That turn has already advanced.")
        if expected_deadline and classic.get("turn_deadline") != expected_deadline:
            raise ValueError("That turn timer is no longer current.")
        new_round = self._advance_classic_turn()
        next_player = classic["turn_order"][classic["turn_index"]]
        self.state["last_event"] = f"@{skipped}'s turn was skipped. @{next_player} is up."
        if new_round and classic.get("fighter_alive"):
            self.state["last_event"] += " The fighter moved for the new round."
        self.save()
        return skipped

    def public_payload(self, message: Optional[str] = None) -> Dict[str, Any]:
        revealed = self.state.get("revealed", {})
        cells = {
            coordinate: {
                "result": record.get("result"),
                "player": record.get("player"),
            }
            for coordinate, record in revealed.items()
            if isinstance(record, dict)
        }
        mode = self.state.get("mode", "single")
        classic = self.state.get("classic", {})
        if mode == "classic":
            ships_remaining = max(0, len(CLASSIC_FLEET) - len(classic.get("sunk", [])))
        else:
            ships_remaining = max(
                0,
                int(self.state.get("ship_count", 0)) - int(self.state.get("hits", 0)),
            )
        scores = [
            {"name": name, **record}
            for name, record in classic.get("scores", {}).items()
        ]
        scores.sort(key=lambda row: (-row["points"], -row["hits"], row["name"]))
        current_player = None
        order = classic.get("turn_order", [])
        if self.state.get("phase") == "playing" and order:
            current_player = order[classic.get("turn_index", 0)]
        return {
            "type": "bittleships_state",
            "mode": mode,
            "phase": self.state.get("phase", "idle"),
            "active": bool(self.state.get("active")),
            "admiral": self.admiral,
            "board_size": BOARD_SIZE,
            "ship_count": int(self.state.get("ship_count", 0)),
            "ships_remaining": ships_remaining,
            "hits": int(self.state.get("hits", 0)),
            "misses": int(self.state.get("misses", 0)),
            "shots_fired": len(cells),
            "pending_shots": {
                username: int(count)
                for username, count in self.state.get("shots", {}).items()
                if int(count) > 0
            },
            "classic": {
                "join_deadline": classic.get("join_deadline"),
                "players": list(classic.get("players", [])),
                "pending_players": list(classic.get("pending_players", [])),
                "turn_order": list(order),
                "current_player": current_player,
                "round": int(classic.get("round", 0)),
                "turn_deadline": classic.get("turn_deadline"),
                "scores": scores,
                "sunk": list(classic.get("sunk", [])),
                "fighter_enabled": bool(classic.get("fighter_enabled")),
                "fighter_alive": bool(classic.get("fighter_alive")),
                "sudden_death": bool(classic.get("sudden_death")),
                "sudden_death_players": list(classic.get("sudden_death_players", [])),
                "winner": classic.get("winner"),
            } if mode == "classic" else None,
            "cells": cells,
            "message": message or self.state.get("last_event"),
            "started_at": self.state.get("started_at"),
            "updated_at": self.state.get("updated_at"),
        }
