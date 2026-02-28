import json
import os
import logging
from functools import lru_cache

DEFAULT_MEDIA_TRIGGERS = {
    "bonk",
    "strike",
    "cleave",
    "fight",
    "gun",
    "skills",
    "stats",
    "spawn",
    "shout",
}

ROUTING_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "command_routing.json")
)


def _load_routing_file():
    try:
        with open(ROUTING_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            triggers = data.get("media_triggers", []) or []
            return {str(item).strip().lower() for item in triggers if str(item).strip()}
    except FileNotFoundError:
        return set()
    except Exception as exc:
        logging.getLogger("command_routing").warning("Failed to load command_routing.json: %s", exc)
        return set()


def _combined_triggers(file_set: set[str]) -> set[str]:
    if not file_set:
        return set(DEFAULT_MEDIA_TRIGGERS)
    return set(DEFAULT_MEDIA_TRIGGERS) | set(file_set)


@lru_cache(maxsize=1)
def get_media_trigger_set() -> set[str]:
    file_set = _load_routing_file()
    return _combined_triggers(file_set)


def refresh_media_trigger_set() -> set[str]:
    get_media_trigger_set.cache_clear()
    return get_media_trigger_set()
