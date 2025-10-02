import os
import asyncio
from bot.twitch_stats import get_stream_info
from bot.weather_utils import get_random_weather_messages

LABELS_DIR = os.path.join(os.path.dirname(__file__), "data", "labels")

LABEL_FILES = {
    "Top D": "session_top_donator.txt",      # Top cash donator (session)
    "Top G": "session_top_sub_gifter.txt",   # Top gifted sub gifter (session)
    "Top B": "session_top_cheerer.txt",      # Top bit cheerer (session)
    "Top 3 D": "all_time_top_donators.txt",      # Top 3 all-time donators
    "Top 3 G": "all_time_top_sub_gifters.txt",   # Top 3 all-time sub gifters
    "Top 3 B": "all_time_top_cheerers.txt",      # Top 3 all-time cheerers
}

def read_label(label):
    path = os.path.join(LABELS_DIR, LABEL_FILES[label])
    if not os.path.isfile(path):
        return "N/A"
    with open(path, "r", encoding="utf-8") as f:
        value = f.read().strip()
        # For top 3, parse first 3 entries (comma-separated)
        if label.startswith("Top 3"):
            # Handle both multi-line and single-line comma-separated
            if label.startswith("Top 3"):
                # Use regex to split on ', ' only when followed by a name (not inside numbers)
                import re
                # Pattern: split on ', ' only if followed by a word character (name)
                entries = re.split(r", (?=\w+[:])", value)
                entries = [entry.strip() for entry in entries if entry.strip()]
                # Remove extra spaces before colon for Top 3 D and Top 3 G
                if label in ("Top 3 D", "Top 3 G"):
                    entries = [e.replace(" :", ":") for e in entries]
                return ", ".join(entries[:3]) if entries else "N/A"
            else:
                lines = [line.strip() for line in value.splitlines() if line.strip()]
                return ", ".join(lines[:3]) if lines else "N/A"
        return value if value else "N/A"

def read_follower_count():
    path = os.path.join(LABELS_DIR, "total_follower_count.txt")
    if not os.path.isfile(path):
        return "N/A"
    with open(path, "r", encoding="utf-8") as f:
        value = f.read().strip()
        return value if value else "N/A"

async def get_follower_count():
    # Read follower count from file instead of Twitch API
    return read_follower_count()

async def get_ticker_messages():
    messages = []
    try:
        info = await get_stream_info()
        messages.append(f"Title: {info.get('title', 'N/A') if info else 'N/A'}")
        messages.append(f"Viewers: {info.get('viewers', 'N/A') if info else 'N/A'}")
        raw_uptime = info.get('uptime', 'N/A') if info else 'N/A'
        if raw_uptime and raw_uptime != 'N/A':
            import re
            match = re.match(r"(?:(\d+) days?, )?(\d+):(\d+):", raw_uptime)
            if match:
                days = int(match.group(1)) if match.group(1) else 0
                hours = int(match.group(2)) if match.group(2) else 0
                minutes = int(match.group(3)) if match.group(3) else 0
                messages.append(f"Uptime: {hours + days * 24}h {minutes}m")
            else:
                messages.append(f"Uptime: {raw_uptime}")
        else:
            messages.append("Uptime: N/A")
        # Add latest subscriber and follower before follower count
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        labels_dir = os.path.join(workspace_root, "bot", "data", "labels")
        latest_sub = "N/A"
        latest_follower = "N/A"
        try:
            sub_path = os.path.join(labels_dir, "most_recent_resubscriber.txt")
            if os.path.isfile(sub_path):
                with open(sub_path, "r", encoding="utf-8") as f:
                    latest_sub = f.read().strip() or "N/A"
        except Exception:
            pass
        try:
            follower_path = os.path.join(labels_dir, "most_recent_follower.txt")
            if os.path.isfile(follower_path):
                with open(follower_path, "r", encoding="utf-8") as f:
                    latest_follower = f.read().strip() or "N/A"
        except Exception:
            pass
        messages.append(f"Latest Subscriber: {latest_sub}")
        messages.append(f"Latest Follower: {latest_follower}")
        follower_count = await get_follower_count()
        messages.append(f"Followers: {follower_count}")
        for label, filename in LABEL_FILES.items():
            value = read_label(label)
            messages.append(f"{label}: {value}")
        from bot.weather_utils import load_weather_messages, fetch_weather
        locations = load_weather_messages()
        import random
        if locations:
            chosen = random.sample(locations, min(5, len(locations)))
            for loc in chosen:
                weather = await fetch_weather(loc)
                # Strip 'Weather: ' if present
                if weather.startswith("Weather: "):
                    messages.append(weather[len("Weather: "):])
                else:
                    messages.append(weather)
        # Add modnews
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        assets_txt_dir = os.path.join(workspace_root, "assets", "txt")
        modnews_path = os.path.join(assets_txt_dir, "modnews.txt")
        modnews_exists = os.path.isfile(modnews_path)
        modnews_msgs = []
        if modnews_exists:
            with open(modnews_path, "r", encoding="utf-8") as f:
                for line in f:
                    msg = line.strip()
                    if msg:
                        modnews_msgs.append(f"ModNews: {msg}")
        if not modnews_msgs:
            messages.append("There is no mod news.")
        else:
            messages.extend(modnews_msgs)
        # Add a random quote
        try:
            import json
            from datetime import datetime
            quotes_path = os.path.join(workspace_root, "data", "quotes.json")
            if os.path.isfile(quotes_path):
                with open(quotes_path, "r", encoding="utf-8") as f:
                    quotes = json.load(f)
                valid_quotes = {qid: q for qid, q in quotes.items() if q["text"] != "MISSING QUOTE"}
                if valid_quotes:
                    quote_id = sorted(valid_quotes.keys(), key=lambda x: int(x))
                    qid = random.choice(quote_id)
                    quote = valid_quotes[qid]
                    try:
                        dt = datetime.strptime(quote["date"], "%m/%d/%Y")
                        formatted_date = dt.strftime("%B %d, %Y")
                    except Exception:
                        formatted_date = quote["date"]
                    messages.append(f'Quote #{qid}: "{quote["text"]}" — {quote["user"]} ({formatted_date})')
        except Exception as e:
            pass
        # Add a random derpism and tic
        try:
            derpisms_path = os.path.join(workspace_root, "assets", "txt", "derpisms.txt")
            if os.path.isfile(derpisms_path):
                with open(derpisms_path, "r", encoding="utf-8") as f:
                    derpisms = [line.strip() for line in f if line.strip()]
                if derpisms:
                    derpism = random.choice(derpisms)
                    messages.append(f'Derpism: {derpism}')
                    tic_path = os.path.join(workspace_root, "assets", "txt", "tic.txt")
                    if os.path.isfile(tic_path):
                        with open(tic_path, "r", encoding="utf-8") as tf:
                            tics = [line.strip() for line in tf if line.strip()]
                        if tics:
                            tic = random.choice(tics)
                            messages.append(f'Tic: {tic}')
        except Exception as e:
            pass
    except Exception as e:
        messages.append(f"[ERROR] Ticker data unavailable: {e}")
    return messages if messages else ["Ticker: No data available."]

async def get_afk_weather_message():
        try:
            from bot.weather_utils import load_weather_messages, fetch_weather
            import random
            locations = load_weather_messages()
            if not locations:
                return ["Weather: N/A"]
            loc = random.choice(locations)
            weather = await fetch_weather(loc)
            # Strip 'Weather: ' if present
            if weather.startswith("Weather: "):
                return [weather[len("Weather: "):]]
            else:
                return [weather]
        except Exception as e:
            return [f"AFK Weather: Error: {e}"]

# Example usage:
# msgs = get_ticker_messages()
# for msg in msgs:
#     print(msg)
