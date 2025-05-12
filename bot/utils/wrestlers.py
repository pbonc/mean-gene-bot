import json
from bot.utils.paths import WRESTLERS_FILE

def load_wrestlers():
    if WRESTLERS_FILE.exists():
        with open(WRESTLERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_wrestlers(data):
    WRESTLERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(WRESTLERS_FILE, "w") as f:
        json.dump(data, f, indent=2)
