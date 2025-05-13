import json
from pathlib import Path

WRESTLER_FILE = Path(__file__).parent.parent / "data" / "wrestlers.json"

TITLE_LIST = [
    "DWF World Heavyweight",
    "DWF Intercontinental",
    "DWF NDA"
]

def load_wrestlers():
    if not WRESTLER_FILE.exists():
        return {}

    try:
        with open(WRESTLER_FILE, "r", encoding="utf-8") as f:
            wrestlers = json.load(f)
    except json.JSONDecodeError:
        print("⚠️ Failed to decode wrestlers.json")
        return {}

    # Ensure all wrestlers have a titles block
    for data in wrestlers.values():
        if "titles" not in data:
            data["titles"] = {title: None for title in TITLE_LIST}
        else:
            for title in TITLE_LIST:
                data["titles"].setdefault(title, None)

    return wrestlers

def save_wrestlers(data):
    try:
        with open(WRESTLER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save wrestlers.json: {e}")
