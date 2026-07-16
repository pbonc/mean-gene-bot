import json
import logging
import os
import random
import csv
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
INVENTORY_FILE = os.path.join(DATA_DIR, "grid_inventory.json")
STATE_FILE = os.path.join(DATA_DIR, "grid_state.json")
LOGGER = logging.getLogger("grid")

MAX_TILES = 100
LEVEL_TO_TIER = {
    "common": 1,
    "uncommon": 2,
    "legendary": 3,
}
LEVEL_ALIASES = {
    "unommon": "uncommon",
}
TIER_TO_LEVEL = {tier: level for level, tier in LEVEL_TO_TIER.items()}
MIN_TIER = 1
MAX_TIER = 3
MAX_HITS = 10


def _ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _current_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


_ZERO_WIDTH_FILTER = {"\u034f"}


def _sanitize_description(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    clean_chars = []
    for ch in normalized:
        if unicodedata.category(ch)[0] == "C":
            continue
        if ch in _ZERO_WIDTH_FILTER:
            continue
        clean_chars.append(ch)
    return "".join(clean_chars).strip()


def _empty_state() -> Dict[str, Any]:
    return {
        "locked": False,
        "hits_remaining": 0,
        "tiles": [],
        "last_award": None,
        "updated_at": None,
        "clear_locked": False,
        "pick_tokens": {},
    }


def _tile_from_entry(entry: Any, index: int) -> Dict[str, Any]:
    if isinstance(entry, dict):
        name = entry.get("name") or f"Prize {index + 1:03d}"
        tier = _clamp(_safe_int(entry.get("tier", MIN_TIER), MIN_TIER), MIN_TIER, MAX_TIER)
        flair = entry.get("flair")
        description = entry.get("description")
    else:
        name = str(entry)
        tier = MIN_TIER
        flair = None
        description = None
    return {
        "id": index,
        "name": name,
        "tier": tier,
        "flair": flair,
        "description": description,
        "revealed": False,
        "reserved_for": None,
        "awarded_to": None,
        "revealed_at": None,
    }


class GridManager:
    def __init__(self) -> None:
        _ensure_data_dir()
        self.state = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if not os.path.exists(STATE_FILE):
            return _empty_state()
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                return _empty_state()
            result = _empty_state()
            result.update(data)
            return result
        except Exception:
            return _empty_state()

    def reload(self) -> None:
        self.state = self._load_state()

    def save(self) -> None:
        self.state["updated_at"] = _current_iso()
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump(self.state, handle, indent=2)

    def _read_inventory(self) -> List[Any]:
        if not os.path.exists(INVENTORY_FILE):
            return []
        try:
            with open(INVENTORY_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            LOGGER.exception("Invalid grid inventory JSON in %s", INVENTORY_FILE)
            raise ValueError(f"Grid inventory JSON is malformed: {exc}") from exc
        if not isinstance(data, Sequence):
            raise ValueError("Grid inventory must be a list of prizes.")
        return list(data)

    def _write_inventory(self, entries: Sequence[Any]) -> None:
        _ensure_data_dir()
        LOGGER.debug("Writing %d inventory entries to %s", len(entries), INVENTORY_FILE)
        with open(INVENTORY_FILE, "w", encoding="utf-8") as handle:
            json.dump(list(entries), handle, indent=2)
        LOGGER.debug("Inventory file size now %d", len(entries))

    def clear_inventory(self) -> None:
        LOGGER.info("Clearing grid inventory file")
        self._write_inventory([])

    def _summary_inventory(self) -> Tuple[List[Dict[str, Any]], int]:
        inventory = self._read_inventory()
        if not inventory:
            return [], 0
        summary: Dict[str, Dict[str, Any]] = {}
        for entry in inventory:
            if isinstance(entry, dict):
                name = str(entry.get("name") or entry.get("description"))
                tier = _clamp(_safe_int(entry.get("tier", MIN_TIER), MIN_TIER), MIN_TIER, MAX_TIER)
            else:
                name = str(entry)
                tier = MIN_TIER
            name = name.strip() or "Prize"
            record = summary.setdefault(name, {"name": name, "tier": tier, "count": 0})
            record["count"] += 1
        entries = sorted(summary.values(), key=lambda item: (-item["count"], item["name"]))
        return entries, len(inventory)

    def randomize_grid(self, hits: int = 1) -> List[Dict[str, Any]]:
        inventory = self._read_inventory()
        if not inventory:
            raise ValueError("Grid inventory does not contain any prizes.")
        tile_count = min(MAX_TILES, len(inventory))
        selection = random.sample(inventory, tile_count)
        random.shuffle(selection)
        tiles = [_tile_from_entry(entry, idx) for idx, entry in enumerate(selection)]
        self.state.update({
            "locked": True,
            "hits_remaining": _clamp(hits, 1, MAX_HITS),
            "tiles": tiles,
            "last_award": None,
            "clear_locked": False,
        })
        self.save()
        return tiles

    def reset(self) -> None:
        self.state = _empty_state()
        self.save()

    def grant_pick_for(self, winner: str) -> bool:
        self.reload()
        tiles: List[Dict[str, Any]] = self.state.get("tiles", [])
        available = [tile for tile in tiles if not tile.get("revealed") and not tile.get("reserved_for")]
        if not available:
            return False
        tokens = self.state.get("pick_tokens")
        if not isinstance(tokens, dict):
            tokens = {}
        winner_key = str(winner).strip().lower()
        if not winner_key:
            return False
        tokens[winner_key] = max(0, _safe_int(tokens.get(winner_key, 0), 0)) + 1
        self.state["pick_tokens"] = tokens
        hits_left = max(0, _safe_int(self.state.get("hits_remaining", 0), 0) - 1)
        self.state["hits_remaining"] = hits_left
        if hits_left <= 0:
            self.state["locked"] = False
        self.state["last_award"] = {
            "granted_to": winner,
            "pick_tokens": tokens[winner_key],
            "timestamp": _current_iso(),
            "pending": True,
        }
        self.save()
        return True

    def reveal_tile(self, tile_id: int, user: str, bypass: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        self.reload()
        tiles: List[Dict[str, Any]] = self.state.get("tiles", [])
        if tile_id < 0 or tile_id >= len(tiles):
            return None, "Tile number out of range."
        tile = tiles[tile_id]
        if tile.get("revealed"):
            return None, "That tile has already been revealed."
        reserved = tile.get("reserved_for")
        user_key = str(user).lower()
        tokens = self.state.get("pick_tokens")
        if not isinstance(tokens, dict):
            tokens = {}
        consumed_token = False
        if reserved and reserved.lower() != user_key and not bypass:
            return None, "That tile is reserved for someone else."
        if not bypass and not reserved:
            remaining = max(0, _safe_int(tokens.get(user_key, 0), 0))
            if remaining <= 0:
                return None, "You were not awarded a grid pick."
            remaining -= 1
            consumed_token = True
            if remaining > 0:
                tokens[user_key] = remaining
            elif user_key in tokens:
                tokens.pop(user_key, None)
            self.state["pick_tokens"] = tokens
        tile["reserved_for"] = None
        tile["revealed"] = True
        tile["awarded_to"] = user
        tile["revealed_at"] = _current_iso()
        self.state["last_award"] = {
            "tile_id": tile_id,
            "name": tile["name"],
            "tier": tile.get("tier", MIN_TIER),
            "awarded_to": user,
            "flair": tile.get("flair"),
            "timestamp": tile["revealed_at"],
            "pending": False,
            "consumed_token": consumed_token,
        }
        self.save()
        return tile, None

    def available_tiles_count(self) -> int:
        tiles: List[Dict[str, Any]] = self.state.get("tiles", [])
        return sum(1 for tile in tiles if not tile.get("revealed") and not tile.get("reserved_for"))

    def is_locked(self) -> bool:
        return bool(self.state.get("locked"))

    def is_clear_locked(self) -> bool:
        return bool(self.state.get("clear_locked", False))

    def lock_clear(self) -> None:
        self.state["clear_locked"] = True
        self.save()

    def unlock_clear(self) -> None:
        self.state["clear_locked"] = False
        self.save()

    def add_prizes(self, level: str, count: int, description: str) -> int:
        normalized = LEVEL_ALIASES.get(level.lower(), level.lower())
        tier = LEVEL_TO_TIER.get(normalized)
        if tier is None:
            raise ValueError("Prize level must be common, uncommon, or legendary.")
        if count <= 0:
            raise ValueError("Prize count must be a positive number.")
        description = _sanitize_description(description)
        if not description:
            raise ValueError("Prize description cannot be empty.")
        inventory = self._read_inventory()
        LOGGER.info(
            "Adding %d %s prize(s): %s (inventory before: %d)",
            count,
            normalized,
            description,
            len(inventory),
        )
        if len(inventory) + count > MAX_TILES:
            raise ValueError(f"Cannot exceed {MAX_TILES} prizes in the inventory.")
        entry = {
            "name": description,
            "tier": tier,
            "flair": normalized,
            "description": description,
        }
        inventory.extend({**entry} for _ in range(count))
        self._write_inventory(inventory)
        return len(inventory)

    def import_prizes_from_csv(self, filename: str, replace: bool = False) -> Tuple[int, int]:
        csv_name = os.path.basename(str(filename or "").strip())
        if not csv_name:
            raise ValueError("Please provide a CSV filename.")
        if not csv_name.lower().endswith(".csv"):
            raise ValueError("CSV filename must end with .csv")
        csv_path = os.path.join(DATA_DIR, csv_name)
        if not os.path.exists(csv_path):
            raise ValueError(f"CSV file not found in data/: {csv_name}")

        pending: List[Tuple[str, int, str]] = []
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(4096)
            handle.seek(0)
            try:
                has_header = csv.Sniffer().has_header(sample)
            except Exception:
                has_header = False

            if has_header:
                reader = csv.DictReader(handle)
                for line_num, row in enumerate(reader, start=2):
                    if not row:
                        continue
                    level = str(row.get("level") or row.get("rarity") or row.get("tier") or "").strip().lower()
                    description = str(row.get("description") or row.get("name") or row.get("prize") or "").strip()
                    count_text = str(row.get("count") or row.get("qty") or row.get("quantity") or "1").strip()
                    if not level and not description:
                        continue
                    try:
                        count = int(count_text)
                    except ValueError as exc:
                        raise ValueError(f"Row {line_num}: count must be a whole number.") from exc
                    normalized = LEVEL_ALIASES.get(level, level)
                    if normalized not in LEVEL_TO_TIER:
                        raise ValueError(f"Row {line_num}: invalid level '{level}'. Use common, uncommon, or legendary.")
                    description = _sanitize_description(description)
                    if not description:
                        raise ValueError(f"Row {line_num}: description cannot be empty.")
                    if count <= 0:
                        raise ValueError(f"Row {line_num}: count must be positive.")
                    pending.append((normalized, count, description))
            else:
                reader = csv.reader(handle)
                for line_num, row in enumerate(reader, start=1):
                    cells = [str(cell).strip() for cell in row]
                    if not cells or all(not cell for cell in cells):
                        continue
                    level = cells[0].lower()
                    if len(cells) < 2:
                        raise ValueError(f"Row {line_num}: expected at least level and description.")
                    count = 1
                    if len(cells) >= 3:
                        try:
                            count = int(cells[1])
                            description = ", ".join(cells[2:]).strip()
                        except ValueError:
                            description = ", ".join(cells[1:]).strip()
                    else:
                        description = cells[1]
                    normalized = LEVEL_ALIASES.get(level, level)
                    if normalized not in LEVEL_TO_TIER:
                        raise ValueError(f"Row {line_num}: invalid level '{level}'. Use common, uncommon, or legendary.")
                    description = _sanitize_description(description)
                    if not description:
                        raise ValueError(f"Row {line_num}: description cannot be empty.")
                    if count <= 0:
                        raise ValueError(f"Row {line_num}: count must be positive.")
                    pending.append((normalized, count, description))

        if not pending:
            raise ValueError("No prize rows found in CSV.")

        existing_count = 0 if replace else len(self._read_inventory())
        incoming_total = sum(count for _, count, _ in pending)
        if existing_count + incoming_total > MAX_TILES:
            raise ValueError(f"Import would exceed {MAX_TILES} total prizes.")

        if replace:
            self.clear_inventory()
        total = len(self._read_inventory())
        for level, count, description in pending:
            total = self.add_prizes(level, count, description)
        return len(pending), total

    def get_import_animation_sequence(self) -> List[Dict[str, Any]]:
        entries, _ = self._summary_inventory()
        ordered = sorted(
            entries,
            key=lambda item: (
                _clamp(_safe_int(item.get("tier", MIN_TIER), MIN_TIER), MIN_TIER, MAX_TIER),
                str(item.get("name") or "").strip().lower(),
            ),
        )
        sequence: List[Dict[str, Any]] = []
        for entry in ordered:
            tier = _clamp(_safe_int(entry.get("tier", MIN_TIER), MIN_TIER), MIN_TIER, MAX_TIER)
            flair = TIER_TO_LEVEL.get(tier, "common")
            name = str(entry.get("name") or "Prize").strip() or "Prize"
            count = max(0, _safe_int(entry.get("count", 0), 0))
            for _ in range(count):
                sequence.append({"name": name, "tier": tier, "flair": flair})
        return sequence

    def get_payload(
        self,
        reveal: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        import_sequence: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        tiles: List[Dict[str, Any]] = self.state.get("tiles", [])
        payload_tiles = []
        for tile in tiles:
            payload_tiles.append({
                "id": tile["id"],
                "number": tile["id"] + 1,
                "name": tile["name"] if tile.get("revealed") else None,
                "prize_name": tile["name"],
                "tier": tile.get("tier", MIN_TIER),
                "flair": tile.get("flair"),
                "revealed": bool(tile.get("revealed")),
                "description": tile.get("description"),
                "awarded_to": tile.get("awarded_to"),
                "reserved_for": tile.get("reserved_for"),
            })
        available = sum(1 for tile in payload_tiles if not tile["revealed"] and not tile.get("reserved_for"))
        try:
            inventory_entries, inventory_total = self._summary_inventory()
        except ValueError:
            inventory_entries, inventory_total = [], 0
        return {
            "type": "grid_state",
            "tiles": payload_tiles,
            "locked": self.state.get("locked", False),
            "hits_remaining": _safe_int(self.state.get("hits_remaining", 0), 0),
            "available_tiles": available,
            "last_award": self.state.get("last_award"),
            "reveal": reveal,
            "message": message or "",
            "updated_at": self.state.get("updated_at"),
            "total_tiles": len(payload_tiles),
            "clear_locked": self.state.get("clear_locked", False),
            "inventory_summary": inventory_entries,
            "inventory_total": inventory_total,
            "import_sequence": import_sequence or [],
        }

    def summary(self) -> str:
        tiles = self.state.get("tiles", [])
        if not tiles:
            return "Grid is empty. Run !grid set to populate it."
        hits = _safe_int(self.state.get("hits_remaining", 0), 0)
        available = self.available_tiles_count()
        state = "locked" if self.is_locked() else "unlocked"
        return f"Grid {state} • {available}/{len(tiles)} tiles remaining • {hits} hits left."
