import json
from pathlib import Path

# Adjust this path to match your actual wrestlers.json location!
# If this file lives in bot/utils/wrestlers.py and your JSON is in mean-gene-bot/dwf/wrestlers.json, this works:
WRESTLER_FILE = Path(__file__).resolve().parents[2] / "dwf" / "wrestlers.json"
print("WRESTLER_FILE path:", WRESTLER_FILE.resolve())

TITLE_LIST = [
    "DWF World Heavyweight Title",
    "DWF Intercontinental Title",
    "DWF NDA Title",
    "DWF Christeweight Title"
]

def load_wrestlers():
    if not WRESTLER_FILE.exists():
        print(f"⚠️ Wrestlers file does not exist at {WRESTLER_FILE.resolve()}")
        return {}

    try:
        with open(WRESTLER_FILE, "r", encoding="utf-8") as f:
            wrestlers = json.load(f)
    except json.JSONDecodeError:
        print("⚠️ Failed to decode wrestlers.json")
        return {}

    # Ensure all wrestler dicts have a 'titles' block for legacy support
    for data in wrestlers.values():
        if isinstance(data, dict):
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
        print(f"✅ Saved wrestler data to {WRESTLER_FILE.resolve()}")
    except Exception as e:
        print(f"❌ Failed to save wrestlers.json: {e}")

def set_new_champion(data, title_name, wrestler_name, send_twitch_func=None):
    """
    Set a new champion for a title, updating both the current_titles block
    and the corresponding wrestler's current_title field.
    Optionally sends a Twitch message if send_twitch_func is provided.
    """
    # Update current_titles
    if "current_titles" in data and title_name in data["current_titles"]:
        data["current_titles"][title_name]["name"] = wrestler_name
        data["current_titles"][title_name]["defenses"] = 0
    # Update all wrestler objects' current_title fields
    for wrestler in data.values():
        if isinstance(wrestler, dict) and "wrestler" in wrestler:
            if wrestler.get("current_title") == title_name:
                wrestler["current_title"] = None
            if wrestler["wrestler"] == wrestler_name:
                wrestler["current_title"] = title_name
    # Optional twitch message
    if send_twitch_func:
        msg = f"🏆 {wrestler_name} is the NEW {title_name} Champion!"
        try:
            send_twitch_func(msg)
        except Exception as e:
            print(f"⚠️ Failed to send Twitch message: {e}")

def increment_title_defense(data, title_name):
    """Increment the defense count for a given title in current_titles."""
    if "current_titles" in data and title_name in data["current_titles"]:
        data["current_titles"][title_name]["defenses"] += 1

def vacate_title(data, title_name, send_twitch_func=None):
    """
    Vacate a title everywhere, updating current_titles and all wrestler objects.
    Optionally sends a Twitch message if send_twitch_func is provided.
    """
    if "current_titles" in data and title_name in data["current_titles"]:
        data["current_titles"][title_name]["name"] = "VACANT"
        data["current_titles"][title_name]["defenses"] = 0
    for wrestler in data.values():
        if isinstance(wrestler, dict) and wrestler.get("current_title") == title_name:
            wrestler["current_title"] = None
    if send_twitch_func:
        msg = f"🚫 {title_name} has been vacated. The title is now vacant!"
        try:
            send_twitch_func(msg)
        except Exception as e:
            print(f"⚠️ Failed to send Twitch message: {e}")