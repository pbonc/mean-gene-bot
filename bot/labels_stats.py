async def get_raffle_encouragement():
    """Encouragement message for raffle, including current prize as $XX."""
    prize = get_raffle_prize()
    if prize and prize.isdigit():
        return f"Type !raffle random to enter for a chance to win a ${int(prize):d} gift card!"
    else:
        return "Type !raffle random to enter the raffle!"
def get_raffle_prize():
    try:
        from bot.raffle_state import SimpleRaffleState
        state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raffle_state.json')
        if not os.path.isfile(state_file):
            return None
        state = SimpleRaffleState(state_file)
        return state.prize
    except Exception:
        return None
def get_raffle_odds():
    """Return a string describing current raffle odds, or 'No raffle running'."""
    try:
        from bot.raffle_state import SimpleRaffleState
        state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raffle_state.json')
        if not os.path.isfile(state_file):
            return "Raffle Odds: No raffle running."
        state = SimpleRaffleState(state_file)
        total_entries = sum(state.entries.values())
        total_picks = len(state.picks)
        if total_entries > 0 and total_picks > 0:
            odds = f"Raffle Odds: 1 in {total_picks}"
        elif total_entries > 0:
            odds = f"Raffle Odds: 1 in {total_entries}"
        else:
            odds = "Raffle Odds: No entries."
        return odds
    except Exception:
        return "Raffle Odds: (unavailable)"
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
        # Always add encouragement first
        encouragement = await get_raffle_encouragement() if callable(get_raffle_encouragement) else get_raffle_encouragement
        if encouragement:
            messages.append(encouragement)

        # Always add bad beat jackpot message second
        from bot.raffle_state import SimpleRaffleState
        state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raffle_state.json')
        jackpot = 25
        if os.path.isfile(state_file):
            state = SimpleRaffleState(state_file)
            jackpot = state.bad_beat_jackpot if hasattr(state, 'bad_beat_jackpot') else 25
        jackpot_msg = f"The current bad beat jackpot is {jackpot} entries!"
        messages.append(jackpot_msg)

        # Always add odds third
        odds = get_raffle_odds()
        if odds:
            messages.append(odds)

        # Add follower count (deduplicated, only once)
        follower_count = read_follower_count()
        if follower_count and follower_count != "N/A":
            messages.append(f"Followers: {follower_count}")

        # Add modnews (limit to 5 random items)
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
        import random
        if modnews_msgs:
            messages.extend(random.sample(modnews_msgs, min(5, len(modnews_msgs))))

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
        except Exception:
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
        except Exception:
            pass

        # Add weather messages (5 random)
        from bot.weather_utils import get_random_weather_messages
        weather_msgs = await get_random_weather_messages(5)
        if weather_msgs:
            messages.extend(weather_msgs)
    except Exception as e:
        messages.append(f"[ERROR] Ticker data unavailable: {e}")
    return messages if messages else ["Ticker: No data available."]
async def get_raffle_odds_message():
    """Async wrapper for raffle odds for AFK/anime overlays."""
    return get_raffle_odds()

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
