import os
import asyncio
from sports_fetchers import is_mlb_in_season, get_today_mlb_scores

THESPORTSDB_API_KEY = os.environ.get("THESPORTSDB_API_KEY", "3")

async def get_all_sports_scores():
    messages = []

    # MLB
    if await is_mlb_in_season(THESPORTSDB_API_KEY):
        mlb_scores = await get_today_mlb_scores(THESPORTSDB_API_KEY)
        messages.extend(mlb_scores)

    # Add similar code for other leagues as you expand

    if not messages:
        messages.append("No games today or no leagues in season.")
    return messages

# For testing
if __name__ == "__main__":
    scores = asyncio.run(get_all_sports_scores())
    for msg in scores:
        print(msg)