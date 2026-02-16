import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

STREAMLABS_TOKEN = os.getenv("STREAMLABS_TOKEN")
STREAMLABS_API_BASE = "https://streamlabs.com/api/v1.0"

async def get_recent_events():
    """Fetch recent events from Streamlabs (subs, bits, donations, etc)."""
    if not STREAMLABS_TOKEN:
        print("[Streamlabs] Missing API token.")
        return []
    url = f"{STREAMLABS_API_BASE}/events?access_token={STREAMLABS_TOKEN}&limit=50"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print(f"[Streamlabs] API error: {resp.status}")
                return []
            data = await resp.json()
            # Events are in 'events' key
            return data.get("events", [])

# Example usage:
# events = await get_recent_events()
# for event in events:
#     print(event)
