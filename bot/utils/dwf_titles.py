import json

def set_new_champion(data, title_name, wrestler_name):
    """Update both current_titles and wrestler data for a new champion."""
    # Update ticker block
    if "current_titles" in data and title_name in data["current_titles"]:
        data["current_titles"][title_name]["name"] = wrestler_name
        data["current_titles"][title_name]["defenses"] = 0
    # Update all wrestler objects
    for wrestler in data.values():
        if isinstance(wrestler, dict) and "wrestler" in wrestler:
            if wrestler.get("current_title") == title_name:
                wrestler["current_title"] = None
            if wrestler["wrestler"] == wrestler_name:
                wrestler["current_title"] = title_name

def increment_title_defense(data, title_name):
    """Increments the defense count for a given title."""
    if "current_titles" in data and title_name in data["current_titles"]:
        data["current_titles"][title_name]["defenses"] += 1

def vacate_title(data, title_name):
    """Vacate a title everywhere."""
    if "current_titles" in data and title_name in data["current_titles"]:
        data["current_titles"][title_name]["name"] = "VACANT"
        data["current_titles"][title_name]["defenses"] = 0
    for wrestler in data.values():
        if isinstance(wrestler, dict) and wrestler.get("current_title") == title_name:
            wrestler["current_title"] = None