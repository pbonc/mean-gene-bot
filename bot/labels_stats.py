# Non-API cache for local text sources
_local_text_cache = {
    'modnews': [],
    'derpisms': [],
    'tics': [],
    'quotes': [],
    'timestamp': 0
}
_local_text_cache_interval = 30  # seconds
import os
import asyncio
from datetime import datetime
from bot.twitch_stats import get_stream_info
from bot.weather_utils import get_random_weather_messages
from bot.sports_api import SportsAPIManager

# Initialize sports manager
sports_manager = SportsAPIManager()

async def get_raffle_encouragement():
    """Encouragement message for raffle, including current prize as $XX."""
    amount = get_raffle_prize()
    if amount and amount > 0:
        return f"The current giveaway is a ${amount:.0f} gift card. Type !raffle random to enter!"
    else:
        return "Type !raffle random to enter the raffle!"

def get_raffle_prize():
    try:
        from bot.commands.raffle_cog import SimpleRaffleState
        state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raffle_state.json')
        if not os.path.isfile(state_file):
            return None
        state = SimpleRaffleState(state_file)
        return state.get_giveaway_amount()
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

LABELS_DIR = os.path.join(os.path.dirname(__file__), "data", "labels")

LABEL_FILES = {
    "Top D": "session_top_donator.txt",
    "Top G": "session_top_sub_gifter.txt",
    "Top B": "session_top_cheerer.txt",
    "Top 3 D": "all_time_top_donators.txt",
    "Top 3 G": "all_time_top_sub_gifters.txt",
    "Top 3 B": "all_time_top_cheerers.txt",
}

def read_label(label):
    path = os.path.join(LABELS_DIR, LABEL_FILES[label])
    if not os.path.isfile(path):
        return "N/A"
    with open(path, "r", encoding="utf-8") as f:
        value = f.read().strip()
        if label.startswith("Top 3"):
            import re
            entries = re.split(r", (?=\w+[:])", value)
            entries = [entry.strip() for entry in entries if entry.strip()]
            if label in ("Top 3 D", "Top 3 G"):
                entries = [e.replace(" :", ":") for e in entries]
            return ", ".join(entries[:3]) if entries else "N/A"
        return value if value else "N/A"

def read_follower_count():
    path = os.path.join(LABELS_DIR, "total_follower_count.txt")
    if not os.path.isfile(path):
        return "N/A"
    with open(path, "r", encoding="utf-8") as f:
        value = f.read().strip()
        return value if value else "N/A"

async def get_follower_count():
    return read_follower_count()

# Track ticker build frequency to limit sports API calls
_last_ticker_build = 0
_ticker_cache = []
_ticker_cache_duration = 300  # Cache ticker for 5 minutes to limit external API calls
_ticker_lock = None  # asyncio.Lock initialized on first use to prevent concurrent rebuilds

async def get_ticker_messages():
    global _last_ticker_build, _ticker_cache
    
    # Check if we should use cached ticker to reduce API calls
    import time
    now = time.time()
    
    # Only use cache if it has content AND isn't too old
    if (_ticker_cache and 
        len(_ticker_cache) > 0 and 
        (now - _last_ticker_build) < _ticker_cache_duration):
        return _ticker_cache


    def get_ticker_on_deck():
        """Synchronous helper for overlays: return the currently cached ticker messages.

        This intentionally does not trigger a rebuild; callers that require fresh
        data should call the async get_ticker_messages().
        """
        return list(_ticker_cache) if _ticker_cache else []
    
    # Build new ticker (guarded by a lock to prevent concurrent, blocking rebuilds)
    global _ticker_lock
    if _ticker_lock is None:
        _ticker_lock = asyncio.Lock()

    async with _ticker_lock:
        # Re-check cache inside the lock in case another coroutine already updated it
        now_inner = time.time()
        if (_ticker_cache and len(_ticker_cache) > 0 and (now_inner - _last_ticker_build) < _ticker_cache_duration):
            return _ticker_cache

        # compute elapsed since previous build for logging
        prev_last = _last_ticker_build
        print(f"[TICKER] Building new ticker messages (last build {int(now_inner - prev_last)}s ago)")
        _last_ticker_build = now_inner

        messages = []
        try:
            # Always add encouragement first
            encouragement = await get_raffle_encouragement() if callable(get_raffle_encouragement) else get_raffle_encouragement
            if encouragement:
                messages.append(encouragement)

            # Always add bad beat jackpot message second
            from bot.commands.raffle_cog import SimpleRaffleState
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

            # Add sports scores (only when building new ticker)
            try:
                sports_messages = await sports_manager.get_sports_messages()
                if sports_messages:
                    messages.extend(sports_messages)
                    print(f"[TICKER] Added {len(sports_messages)} sports messages to ticker")
            except Exception as e:
                print(f"Error getting sports messages: {e}")

            # Add modnews (limit to 1 random item)
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
                messages.append(random.choice(modnews_msgs))

            # Add a random quote
            try:
                workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                assets_txt_dir = os.path.join(workspace_root, "assets", "txt")
                # Derpisms
                derpisms_path = os.path.join(assets_txt_dir, "derpisms.txt")
                derpisms = []
                if os.path.isfile(derpisms_path):
                    with open(derpisms_path, "r", encoding="utf-8") as f:
                        derpisms = [line.strip() for line in f if line.strip()]
                # Tics
                tic_path = os.path.join(assets_txt_dir, "tic.txt")
                tics = []
                if os.path.isfile(tic_path):
                    with open(tic_path, "r", encoding="utf-8") as tf:
                        tics = [line.strip() for line in tf if line.strip()]
                # Quotes
                quotes_path = os.path.join(workspace_root, "data", "quotes.json")
                quotes = []
                if os.path.isfile(quotes_path):
                    import json
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
            print(f"[TICKER] Error building ticker: {e}")
            messages.append(f"[ERROR] Ticker data unavailable: {e}")

        # Ensure we always have at least one message
        if not messages:
            messages = ["Ticker: No data available."]

        # Cache the completed ticker (success or handled exception)
        _ticker_cache = messages
        print(f"[TICKER] Cached {len(messages)} messages for {_ticker_cache_duration}s")
        return _ticker_cache

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
        if weather.startswith("Weather: "):
            return [weather[len("Weather: "):]]
        else:
            return [weather]
    except Exception as e:
        return [f"AFK Weather: Error: {e}"]