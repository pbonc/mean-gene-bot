from dotenv import load_dotenv
import os
import pathlib

# Always load .env from project root, no matter where script is run from
project_root = pathlib.Path(__file__).resolve().parents[2]  # 2 levels up: bot/overlay -> bot -> project root
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

from sports_fetchers.nba import get_today_nba_scores
from sports_fetchers.mlb import get_today_mlb_scores
from sports_fetchers.nhl import get_today_nhl_scores

API_KEY = os.getenv("THESPORTSDB_API_KEY")
print("DEBUG: API_KEY is", API_KEY)  # <--- TEMP: REMOVE after confirming it prints your real key!

async def main():
    nba = await get_today_nba_scores(API_KEY)
    mlb = await get_today_mlb_scores(API_KEY)
    nhl = await get_today_nhl_scores(API_KEY)

    print("=== NBA ===")
    for line in nba:
        print(line)
    print("\n=== NHL ===")
    for line in nhl:
        print(line)
    print("\n=== MLB ===")
    for line in mlb:
        print(line)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())