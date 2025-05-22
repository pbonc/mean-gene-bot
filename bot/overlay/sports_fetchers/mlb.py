import aiohttp
import datetime
import pytz

MLB_LEAGUE_ID = "4424"
MLB_TEAM_NAMES = {
    "Arizona Diamondbacks", "Atlanta Braves", "Baltimore Orioles", "Boston Red Sox",
    "Chicago Cubs", "Chicago White Sox", "Cincinnati Reds", "Cleveland Guardians",
    "Colorado Rockies", "Detroit Tigers", "Houston Astros", "Kansas City Royals",
    "Los Angeles Angels", "Los Angeles Dodgers", "Miami Marlins", "Milwaukee Brewers",
    "Minnesota Twins", "New York Mets", "New York Yankees", "Oakland Athletics",
    "Philadelphia Phillies", "Pittsburgh Pirates", "San Diego Padres", "San Francisco Giants",
    "Seattle Mariners", "St. Louis Cardinals", "Tampa Bay Rays", "Texas Rangers",
    "Toronto Blue Jays", "Washington Nationals"
}

async def is_mlb_in_season(api_key: str) -> bool:
    """Returns True if there is an MLB game today."""
    central = pytz.timezone("America/Chicago")
    today_str = datetime.datetime.now(central).strftime("%Y-%m-%d")
    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventspastleague.php?id={MLB_LEAGUE_ID}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            events = data.get("events", [])
            for event in events:
                if event.get("dateEvent") == today_str and event.get("strHomeTeam") in MLB_TEAM_NAMES and event.get("strAwayTeam") in MLB_TEAM_NAMES:
                    return True
    return False

async def get_today_mlb_scores(api_key: str):
    """Fetch today's MLB scores (all games for today)."""
    central = pytz.timezone("America/Chicago")
    today_str = datetime.datetime.now(central).strftime("%Y-%m-%d")
    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventspastleague.php?id={MLB_LEAGUE_ID}"
    messages = []

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            events = data.get("events", [])
            for event in events:
                date = event.get("dateEvent")
                home = event.get("strHomeTeam")
                away = event.get("strAwayTeam")
                if date == today_str and home in MLB_TEAM_NAMES and away in MLB_TEAM_NAMES:
                    home_score = event.get("intHomeScore")
                    away_score = event.get("intAwayScore")
                    if home_score is not None and away_score is not None:
                        messages.append(f"MLB: {home} {home_score}, {away} {away_score} ({date})")
    return messages