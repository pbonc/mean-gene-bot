import argparse
import asyncio
import json
import aiohttp
from pathlib import Path
import websockets
from websockets.protocol import State
from dotenv import load_dotenv
import os
import time
import datetime
import pytz

# --- ADD ARGPARSE FOR DEV MODE ---
parser = argparse.ArgumentParser(description="Run the TickerServer overlay.")
parser.add_argument('-d', '--dev', action='store_true', help='Enable dev mode (short ticker interval)')
args = parser.parse_args()

# Ticker interval is shorter in dev mode
TICKER_INTERVAL = 2 if args.dev else 10  # seconds

# Load environment variables from the project root .env file
env_path = Path(__file__).parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
print("OPENWEATHER_API_KEY loaded as:", repr(OPENWEATHER_API_KEY))

WRESTLERS_PATH = Path(__file__).parent.parent.parent / "dwf" / "wrestlers.json"
LABELS_DIR = Path(__file__).parent.parent / "data" / "labels"
WEATHER_CITIES_PATH = Path(__file__).parent.parent / "data" / "weather_cities.txt"

# SportsDB API
THESPORTSDB_API_KEY = "3"  # Free user key

# Weather cache globals
weather_cache = []
weather_last_update = 0
WEATHER_UPDATE_INTERVAL = 300  # every 5 minutes (300 seconds)

def read_label_file(filename, formatter):
    file_path = LABELS_DIR / filename
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            value = f.read().strip()
            if value:
                return formatter(value)
    return None

def read_weather_cities():
    if WEATHER_CITIES_PATH.exists():
        with open(WEATHER_CITIES_PATH, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return []

def weather_emoji(cond):
    cond = cond.lower()
    if "rain" in cond: return "🌧️"
    if "cloud" in cond: return "☁️"
    if "clear" in cond: return "☀️"
    if "snow" in cond: return "❄️"
    if "storm" in cond or "thunder" in cond: return "⛈️"
    if "fog" in cond or "mist" in cond: return "🌫️"
    if "drizzle" in cond: return "🌦️"
    return "🌈"

async def get_weather_for_city(session, city):
    if not OPENWEATHER_API_KEY:
        print("[WEATHER] API key not set")
        return None
    url = (
        f"http://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={OPENWEATHER_API_KEY}&units=imperial"
    )
    try:
        async with session.get(url, timeout=10) as resp:
            data = await resp.json()
            if resp.status == 200 and "main" in data and "weather" in data:
                temp = int(round(data["main"]["temp"]))
                cond = data["weather"][0]["main"]
                emoji = weather_emoji(cond)
                return f"{city}: {emoji} {temp}°F"
            else:
                print(f"[WEATHER] Failed response for {city}: {data}")
                return None
    except Exception as e:
        print(f"[WEATHER ERROR] {city}: {e}")
        return None

async def build_ticker_messages():
    global weather_cache, weather_last_update
    messages = []

    # --- Twitch & Stream Stats ---
    msg = read_label_file("total_subscriber_score.txt", lambda v: f"Current Sub Points: {v}")
    if msg: messages.append(msg)
    msg = read_label_file("total_follower_count.txt", lambda v: f"Total Followers: {v}")
    if msg: messages.append(msg)
    msg = read_label_file("all_time_top_donator.txt", lambda v: f"Top Total Dono - {v}")
    if msg: messages.append(msg)
    msg = read_label_file("all_time_top_sub_gifter.txt", lambda v: f"Top Gifter - {v}")
    if msg: messages.append(msg)
    msg = read_label_file("all_time_top_cheerer.txt", lambda v: f"Top Bits: {v}")
    if msg: messages.append(msg)

    # --- DWF Titleholders ---
    if WRESTLERS_PATH.exists():
        with open(WRESTLERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            current_titles = data.get("current_titles", {})
            for title_name, info in current_titles.items():
                wrestler = info.get("name", "Unknown")
                defenses = info.get("defenses", 0)
                messages.append(
                    f"Current {title_name}: {wrestler} (Defenses: {defenses})"
                )

    # --- Sports: MLB, NBA, NHL ---
    from sports_fetchers.mlb import get_today_mlb_scores
    from sports_fetchers.nba import get_today_nba_scores
    from sports_fetchers.nhl import get_today_nhl_scores

    api_key = os.environ.get("THESPORTSDB_API_KEY", "3")

    mlb_msgs = await get_today_mlb_scores(api_key)
    messages.extend(mlb_msgs)

    nba_msgs = await get_today_nba_scores(api_key)
    messages.extend(nba_msgs)

    nhl_msgs = await get_today_nhl_scores(api_key)
    messages.extend(nhl_msgs)

    # --- Weather (cache, update every WEATHER_UPDATE_INTERVAL) ---
    now = time.time()
    if now - weather_last_update > WEATHER_UPDATE_INTERVAL:
        cities = read_weather_cities()
        if cities and OPENWEATHER_API_KEY:
            async with aiohttp.ClientSession() as session:
                weather_msgs = await asyncio.gather(
                    *(get_weather_for_city(session, city) for city in cities)
                )
                weather_cache = [wmsg for wmsg in weather_msgs if wmsg]
                weather_last_update = now
    # Add cached weather messages to ticker
    messages.extend(weather_cache)

    if not messages:
        messages = ["Welcome to the Darmunist News Network."]
    return messages

class TickerServer:
    def __init__(self):
        self.clients = set()
        self.messages = []
        self.idx = 0

    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"New overlay connected. Total: {len(self.clients)}")

    async def unregister(self, websocket):
        self.clients.remove(websocket)
        print(f"Overlay disconnected. Total: {len(self.clients)}")

    async def handler(self, websocket):
        await self.register(websocket)
        try:
            while True:
                await asyncio.sleep(1)
        finally:
            await self.unregister(websocket)

    async def ticker_loop(self):
        while True:
            self.messages = await build_ticker_messages()
            if self.messages:
                msg = {
                    "type": "ticker",
                    "text": self.messages[self.idx % len(self.messages)]
                }
                print("Broadcasting:", msg["text"])
                await asyncio.gather(*[
                    ws.send(json.dumps(msg))
                    for ws in self.clients
                    if ws.state == State.OPEN
                ])
                self.idx += 1
            await asyncio.sleep(TICKER_INTERVAL)

    async def main(self):
        print(f"Starting TickerServer in {'DEV' if args.dev else 'PRODUCTION'} mode. Ticker interval: {TICKER_INTERVAL} seconds.")
        server = await websockets.serve(self.handler, "localhost", 6789)
        print("TickerServer WebSocket running on ws://localhost:6789")
        await self.ticker_loop()

if __name__ == "__main__":
    server = TickerServer()
    asyncio.run(server.main())