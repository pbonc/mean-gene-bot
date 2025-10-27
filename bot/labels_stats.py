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
from bot.twitch_stats import get_stream_info
from bot.weather_utils import get_random_weather_messages
from bot.sports_api import SportsAPIManager

# Initialize sports manager
sports_manager = SportsAPIManager()

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
_ticker_cache_duration = 30  # Used for legacy cache logic


# Shared data cache for API results
_shared_data_cache = {
    'sports': [],
    'weather': [],
    'timestamp': 0
}
_shared_data_cache_interval = 120  # seconds

# Ticker "on deck" system
_ticker_on_deck = []
_ticker_on_deck_timestamp = 0
_ticker_on_deck_interval = 120  # seconds (2 minutes, matches broadcast interval)


def start_ticker_refresh_loop():
    """Starts background tasks to refresh shared data and ticker messages every 2 minutes."""
    loop = asyncio.get_event_loop()
    loop.create_task(_refresh_shared_data_cache())
    loop.create_task(_refresh_local_text_cache())
    loop.create_task(_refresh_ticker_on_deck())
async def _refresh_local_text_cache():
    import logging
    global _local_text_cache
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            assets_txt_dir = os.path.join(workspace_root, "assets", "txt")
            # Modnews
            modnews_path = os.path.join(assets_txt_dir, "modnews.txt")
            modnews_msgs = []
            if os.path.isfile(modnews_path):
                with open(modnews_path, "r", encoding="utf-8") as f:
                    for line in f:
                        msg = line.strip()
                        if msg:
                            modnews_msgs.append(f"ModNews: {msg}")
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
                    raw_quotes = json.load(f)
                quotes = [q for q in raw_quotes.values() if q["text"] != "MISSING QUOTE"]
            # Update cache
            _local_text_cache['modnews'] = modnews_msgs
            _local_text_cache['derpisms'] = derpisms
            _local_text_cache['tics'] = tics
            _local_text_cache['quotes'] = quotes
            _local_text_cache['timestamp'] = int(asyncio.get_event_loop().time())
            logging.info(f"[CACHE] Updated local text cache: modnews={len(modnews_msgs)}, derpisms={len(derpisms)}, tics={len(tics)}, quotes={len(quotes)}")
        except Exception as e:
            logging.error(f"[CACHE] Error in local text cache refresh: {e}")
        await asyncio.sleep(_local_text_cache_interval)
async def _refresh_shared_data_cache():
    import logging
    global _shared_data_cache
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            # Fetch sports data
            sports_messages = []
            try:
                sports_messages = await sports_manager.get_sports_messages()
            except Exception as e:
                logging.error(f"[CACHE] Error fetching sports data: {e}")
            # Fetch weather data
            weather_messages = []
            try:
                from bot.weather_utils import get_random_weather_messages
                weather_messages = await get_random_weather_messages(5)
            except Exception as e:
                logging.error(f"[CACHE] Error fetching weather data: {e}")
            # Update cache
            _shared_data_cache['sports'] = sports_messages or []
            _shared_data_cache['weather'] = weather_messages or []
            _shared_data_cache['timestamp'] = int(asyncio.get_event_loop().time())
            logging.info(f"[CACHE] Updated shared data cache: sports={len(sports_messages)}, weather={len(weather_messages)}")
        except Exception as e:
            logging.error(f"[CACHE] Error in shared data cache refresh: {e}")
        await asyncio.sleep(_shared_data_cache_interval)

async def _refresh_ticker_on_deck():
    global _ticker_on_deck, _ticker_on_deck_timestamp
    import logging
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            messages = await get_ticker_messages(force_rebuild=True)
            logging.info(f"[TICKER] Background refresh. Generated messages: {messages}")
            if messages and isinstance(messages, list) and len(messages) > 0:
                _ticker_on_deck = messages
                _ticker_on_deck_timestamp = int(asyncio.get_event_loop().time())
                logging.info(f"[TICKER] Refreshed 'on deck' ticker with {len(messages)} messages.")
            else:
                logging.warning(f"[TICKER] No messages generated during refresh.")
        except Exception as e:
            logging.error(f"[TICKER] Error refreshing 'on deck' ticker: {e}")
        await asyncio.sleep(_ticker_on_deck_interval)

def get_ticker_on_deck():
    """Returns the current 'on deck' ticker messages, rebuilding if expired or empty."""
    now = int(asyncio.get_event_loop().time())
    expired = (now - _ticker_on_deck_timestamp) > _ticker_on_deck_interval
    import logging
    if not _ticker_on_deck or expired:
        logging.warning("[TICKER] 'On deck' ticker expired or empty, scheduling async refresh.")
        # Schedule async refresh, but do NOT block
        loop = asyncio.get_event_loop()
        try:
            loop.create_task(_refresh_ticker_on_deck())
        except Exception as e:
            logging.error(f"[TICKER] Could not schedule async refresh: {e}")
        # Return default message instantly
        return ["Ticker: No data available."]
    logging.info(f"[TICKER] Returning on deck ticker: {_ticker_on_deck}")
    return _ticker_on_deck

async def get_ticker_messages(force_rebuild=False):
    global _last_ticker_build, _ticker_cache
    
    # Check if we should use cached ticker to reduce API calls
    import time
    now = time.time()
    

    # Only use cache if it has content, isn't too old, and is not empty
    cache_valid = (
        not force_rebuild and
        _ticker_cache and
        isinstance(_ticker_cache, list) and
        len(_ticker_cache) > 0 and
        (now - _last_ticker_build) < _ticker_cache_duration
    )
    if cache_valid:
        return _ticker_cache

    # Build new ticker
    print(f"[TICKER] Building new ticker messages (last build {int(now - _last_ticker_build)}s ago)")
    _last_ticker_build = now


    import re, random, pytz
    from datetime import datetime
    def strip_html_tags(text):
        return re.sub(r'<[^>]+>', '', text)

    try:
        # 1. Timestamp
        now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
        now_cst = now_utc.astimezone(pytz.timezone('US/Central'))
        cst_str = now_cst.strftime('%I:%M %p CST')
        utc_str = now_utc.strftime('%H:%M UTC')
        messages = [f'[{cst_str} | {utc_str}]']

        # 2. Title
        from bot.twitch_stats import get_stream_info
        try:
            info = await get_stream_info()
            title = info.get('title', 'N/A') if info else 'N/A'
        except Exception:
            title = 'N/A'
        messages.append(f"Title: {title}")

        # 3. Encouragement (guaranteed)
        encouragement_msg = "Get in the raffle!"
        try:
            encouragement = await get_raffle_encouragement() if callable(get_raffle_encouragement) else get_raffle_encouragement
            if encouragement:
                encouragement_msg = encouragement
        except Exception:
            pass
        messages.append(encouragement_msg)

        # 4. Jackpot (guaranteed)
        jackpot_msg = "The current bad beat jackpot is N/A entries!"
        try:
            state_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raffle_state.json')
            if os.path.isfile(state_file):
                import json
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                jackpot = data.get('bad_beat_jackpot', None)
                if jackpot is not None:
                    jackpot_msg = f"The current bad beat jackpot is {jackpot} entries!"
        except Exception:
            pass
        messages.append(jackpot_msg)

        # 5. Followers
        follower_count = read_follower_count()
        if follower_count and follower_count != "N/A":
            messages.append(f"Followers: {follower_count}")

        # 6. Sub Points
        messages.append(f"Sub Points: N/A")

        # 7. Latest Follower
        messages.append(f"Latest Follower: {read_label('Top D')}")

        # 8. Latest Subscriber
        messages.append(f"Latest Subscriber: {read_label('Top G')}")

        # 9. Single Tops
        messages.append(f"Top B: {read_label('Top B')}")
        messages.append(f"Top G: {read_label('Top G')}")
        messages.append(f"Top D: {read_label('Top D')}")

        # 10. Top 3s
        messages.append(f"Top 3 G: {strip_html_tags(read_label('Top 3 G'))}")
        messages.append(f"Top 3 D: {strip_html_tags(read_label('Top 3 D'))}")
        messages.append(f"Top 3 B: {strip_html_tags(read_label('Top 3 B'))}")

        # 11. Sports (if available)
        sports_msgs = _shared_data_cache.get('sports', [])
        if sports_msgs:
            for sm in sports_msgs:
                messages.append(strip_html_tags(sm))

        # 12. Weather (if available)
        weather_msgs = _shared_data_cache.get('weather', [])
        if weather_msgs:
            for wm in weather_msgs:
                messages.append(strip_html_tags(wm))

        # 13. ModNews (limit to 1)
        modnews_msgs = _local_text_cache.get('modnews', [])
        if modnews_msgs:
            messages.append(strip_html_tags(random.choice(modnews_msgs)))

        # 14. Quote
        quotes = _local_text_cache.get('quotes', [])
        if quotes:
            quote = random.choice(quotes)
            try:
                from datetime import datetime as dtmod
                dt = dtmod.strptime(quote["date"], "%m/%d/%Y")
                formatted_date = dt.strftime("%B %d, %Y")
            except Exception:
                formatted_date = quote["date"]
            messages.append(strip_html_tags(f'Quote: "{quote["text"]}" — {quote["user"]} ({formatted_date})'))

        # 15. Derpism
        derpisms = _local_text_cache.get('derpisms', [])
        if derpisms:
            messages.append(f'Derpism: {random.choice(derpisms)}')

        # 16. Tic
        tics = _local_text_cache.get('tics', [])
        if tics:
            messages.append(f'Tic: {random.choice(tics)}')

        # Remove duplicates while preserving order
        seen = set()
        cleaned = []
        for m in messages:
            if m not in seen and m != "N/A" and not m.startswith("[ERROR]") and not m.startswith("Ticker: No data available."):
                cleaned.append(m)
                seen.add(m)
        messages = cleaned

    except Exception as e:
        print(f"[TICKER] Error building ticker: {e}")
        messages = [f"[ERROR] Ticker data unavailable: {e}"]

    if not messages or not isinstance(messages, list) or len(messages) == 0:
        messages = ["Ticker: No data available."]

    _ticker_cache = messages
    print(f"[TICKER] Cached {len(messages)} messages for {_ticker_cache_duration}s")
    return _ticker_cache

# Start the ticker refresh loop when module is loaded
try:
    start_ticker_refresh_loop()
except Exception as e:
    print(f"[TICKER] Could not start refresh loop: {e}")

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