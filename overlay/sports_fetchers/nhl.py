import aiohttp
import datetime
import pytz

NHL_TEAM_ABBR = {
    "Anaheim Ducks": "ANA", "Arizona Coyotes": "ARI", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF",
    "Calgary Flames": "CGY", "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL",
    "Columbus Blue Jackets": "CBJ", "Dallas Stars": "DAL", "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM",
    "Florida Panthers": "FLA", "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL",
    "Nashville Predators": "NSH", "New Jersey Devils": "NJD", "New York Islanders": "NYI", "New York Rangers": "NYR",
    "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS",
    "Seattle Kraken": "SEA", "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
    "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK", "Washington Capitals": "WSH", "Winnipeg Jets": "WPG"
}

def get_team_abbr(name):
    return NHL_TEAM_ABBR.get(name, name or "")

def safe_score(val):
    try:
        if val is None:
            return "0"
        return str(int(val))
    except Exception:
        return str(val) if val is not None else "0"

async def get_today_nhl_scores(api_key: str):
    today_utc = datetime.datetime.utcnow().date()
    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventsday.php?d={today_utc.strftime('%Y-%m-%d')}&l=NHL"
    messages = ["NHL Scores"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try:
                    data = await response.json()
                except Exception as e:
                    messages.append(f"NHL: Error decoding response: {e}")
                    return messages

                events = data.get("events")
                if not events:
                    messages.append("No NHL games found.")
                    return messages

                finished = []
                in_progress = []
                upcoming = []

                now_utc = datetime.datetime.now(datetime.timezone.utc)

                for event in events:
                    home = event.get("strHomeTeam")
                    away = event.get("strAwayTeam")
                    home_abbr = get_team_abbr(home)
                    away_abbr = get_team_abbr(away)
                    home_score = event.get("intHomeScore")
                    away_score = event.get("intAwayScore")
                    status = (event.get("strStatus") or "").upper()
                    progress = (event.get("strProgress") or "").upper()
                    event_time_utc = event.get("strTimestamp")

                    pretty_time = ""
                    dt_utc = None
                    if event_time_utc:
                        try:
                            dt_utc = datetime.datetime.strptime(event_time_utc, "%Y-%m-%dT%H:%M:%S")
                            pretty_time_utc = dt_utc.strftime("%H:%M UTC")
                            dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
                            dt_cst = dt_utc.astimezone(pytz.timezone("America/Chicago"))
                            pretty_time_cst = dt_cst.strftime("%I:%M %p CST").lstrip("0")
                            pretty_time = f"{pretty_time_cst} / {pretty_time_utc}"
                        except Exception:
                            pretty_time = ""

                    # Patch: If game is scheduled but time has passed, show as in progress
                    if status == "NS" and event_time_utc:
                        try:
                            dt_utc = datetime.datetime.strptime(event_time_utc, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                            if dt_utc > now_utc:
                                # Pregame, show scheduled time
                                if pretty_time:
                                    upcoming.append({
                                        "msg": f"{away_abbr} at {home_abbr} {pretty_time}",
                                        "dt": dt_utc
                                    })
                                else:
                                    upcoming.append({
                                        "msg": f"{away_abbr} at {home_abbr}",
                                        "dt": datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
                                    })
                                continue
                            else:
                                # Time is in the past, but status still NS
                                in_progress.append(f"{away_abbr} at {home_abbr} IN PROGRESS (API delay)")
                                continue
                        except Exception:
                            pass

                    try:
                        if any(x in status for x in ["POSTPONED", "PPD", "CANCELLED", "DELAYED"]) or any(x in progress for x in ["POSTPONED", "PPD", "CANCELLED", "DELAYED"]):
                            in_progress.append(f"{away_abbr} at {home_abbr} PPD")
                        elif any(x in status for x in ["FINAL", "FT", "F"]) or "FINAL" in progress or "FT" in progress or "F/" in progress:
                            finished.append(f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} (F)")
                        elif (status and status != "NS") or (progress and progress != "NS"):
                            in_progress.append(f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} {status or progress}")
                        else:
                            upcoming.append({
                                "msg": f"{away_abbr} at {home_abbr}",
                                "dt": datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
                            })
                    except Exception as e:
                        messages.append(f"NHL Formatter Error: {e} ({away_abbr} @ {home_abbr})")

                if upcoming:
                    upcoming.sort(key=lambda x: x["dt"])
                    upcoming_msgs = [g["msg"] for g in upcoming]
                else:
                    upcoming_msgs = []

                messages.extend(in_progress)
                messages.extend(upcoming_msgs)
                messages.extend(finished)
    except Exception as e:
        messages.append(f"NHL ERROR: {e}")

    return messages