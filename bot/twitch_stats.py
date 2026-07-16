import os
import aiohttp
import datetime
import asyncio
from dotenv import load_dotenv

load_dotenv()

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_OAUTH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")
TWITCH_CHANNEL = os.getenv("TWITCH_CHANNELS", "").split(",")[0].strip()

API_BASE = "https://api.twitch.tv/helix"

HEADERS = {
    "Client-ID": TWITCH_CLIENT_ID,
    "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}"
}

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=3)

async def get_stream_info():
    """Fetch current stream info: viewers, uptime, title, etc."""
    url = f"{API_BASE}/streams?user_login={TWITCH_CHANNEL}"
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(url, headers=HEADERS) as resp:
                data = await resp.json()
                if "data" in data and data["data"]:
                    stream = data["data"][0]
                    started_at = stream.get("started_at")
                    uptime = None
                    if started_at:
                        started_dt = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                        uptime = datetime.datetime.utcnow() - started_dt.replace(tzinfo=None)
                    return {
                        "viewers": stream.get("viewer_count"),
                        "uptime": str(uptime) if uptime else None,
                        "title": stream.get("title"),
                        "game": stream.get("game_name"),
                    }
                return None
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None
    except Exception:
        return None

async def get_recent_follower():
    """Fetch the most recent follower using Helix endpoint."""
    async with aiohttp.ClientSession() as session:
        # Get user ID for the channel
        async with session.get(f"{API_BASE}/users?login={TWITCH_CHANNEL}", headers=HEADERS) as resp:
            data = await resp.json()
            if "data" not in data or not data["data"]:
                return None
            user_id = data["data"][0]["id"]
        url = f"{API_BASE}/users/follows?to_id={user_id}&first=1"
        async with session.get(url, headers=HEADERS) as resp:
            data = await resp.json()
            if resp.status == 410:
                return "Follower API deprecated"
            if "data" in data and data["data"]:
                follower = data["data"][0]
                # Return display name of the most recent follower
                return follower.get("from_name") or follower.get("from_login") or follower.get("from_id")
            return None

async def get_recent_subscriber():
    """Fetch the most recent subscriber (requires appropriate OAuth scope)."""
    # Twitch API for subscriptions requires broadcaster scope and may be limited
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE}/users?login={TWITCH_CHANNEL}", headers=HEADERS) as resp:
            data = await resp.json()
            if "data" not in data or not data["data"]:
                return None
            user_id = data["data"][0]["id"]
        async with session.get(f"{API_BASE}/subscriptions?broadcaster_id={user_id}&first=1", headers=HEADERS) as resp:
            data = await resp.json()
            if "data" in data and data["data"]:
                sub = data["data"][0]
                return sub.get("user_name")
            return None

async def get_sub_points():
    """Fetch current sub points (requires appropriate OAuth scope)."""
    # Twitch API does not expose sub points directly; may need to estimate from subscriptions
    # This function paginates through all subscriptions and counts them
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.get(f"{API_BASE}/users?login={TWITCH_CHANNEL}", headers=HEADERS) as resp:
                data = await resp.json()
                if "data" not in data or not data["data"]:
                    return None
                user_id = data["data"][0]["id"]
            total_subs = 0
            cursor = None
            while True:
                url = f"{API_BASE}/subscriptions?broadcaster_id={user_id}&first=100"
                if cursor:
                    url += f"&after={cursor}"
                async with session.get(url, headers=HEADERS) as resp:
                    data = await resp.json()
                    if "data" in data:
                        total_subs += len(data["data"])
                        cursor = data.get("pagination", {}).get("cursor")
                        if not cursor or len(data["data"]) == 0:
                            break
                    else:
                        break
            return total_subs
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None
    except Exception:
        return None

# For top gifters/bit donators, you will need to track these manually in a persistent file/database.

# Example usage:
# info = await get_stream_info()
# follower = await get_recent_follower()
# subscriber = await get_recent_subscriber()
# sub_points = await get_sub_points()
