import aiohttp
import datetime
import pytz
import re

NBA_TEAM_ABBR = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM", "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP", "New York Knicks": "NYK",
    "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
    "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS", "Toronto Raptors": "TOR",
    "Utah Jazz": "UTA", "Washington Wizards": "WAS"
}

NBA_TEAM_NAMES = set(NBA_TEAM_ABBR.keys())

def get_team_abbr(name):
    return NBA_TEAM_ABBR.get(name, name or "")

def safe_score(val):
    try:
        if val is None:
            return "0"
        return str(int(val))
    except Exception:
        return str(val) if val is not None else "0"

def parse_status(status, progress):
    s = (status or "").upper()
    p = (progress or "").upper()
    if any(x in s for x in ["POSTPONED", "PPD", "CANCELLED", "DELAYED"]):
        return "PPD"
    if any(x in p for x in ["POSTPONED", "PPD", "CANCELLED", "DELAYED"]):
        return "PPD"
    if any(x in s for x in ["FINAL", "FT", "F"]) or "FINAL" in p or "FT" in p or "F/" in p:
        ot_match = re.search(r'F/(\d+)', p)
        if ot_match:
            return f"F/{ot_match.group(1)}"
        if "OT" in p or "OT" in s:
            return "F/OT"
        return "F"
    quarter = ""
    q_match = re.search(r'(Q\d)', p)
    if q_match:
        quarter = q_match.group(1)
    elif "HALFTIME" in p:
        quarter = "HT"
    elif "END" in p and "Q" in p:
        quarter = p
    elif "OT" in p:
        quarter = "OT"
    if quarter:
        return quarter
    return ""

async def get_today_nba_scores(api_key: str):
    today_utc = datetime.datetime.utcnow().date()
    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventsday.php?d={today_utc.strftime('%Y-%m-%d')}&l=NBA"
    messages = ["NBA Scores"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try:
                    data = await response.json()
                except Exception as e:
                    messages.append(f"NBA: Error decoding response: {e}")
                    return messages

                events = data.get("events")
                if not events:
                    messages.append("No NBA games found.")
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
                    status = event.get("strStatus", "")
                    progress = event.get("strProgress", "")
                    event_time_utc = event.get("strTimestamp")

                    if home not in NBA_TEAM_NAMES or away not in NBA_TEAM_NAMES:
                        continue

                    pretty_time = ""
                    dt_utc = None
                    if event_time_utc:
                        try:
                            dt_utc = datetime.datetime.strptime(event_time_utc, "%Y-%m-%dT%H:%M:%S")
                            dt_utc = dt_utc.replace(tzinfo=datetime.timezone.utc)
                            dt_cst = dt_utc.astimezone(pytz.timezone("America/Chicago"))
                            pretty_time_cst = dt_cst.strftime("%I:%M %p CST").lstrip("0")
                            pretty_time_utc = dt_utc.strftime("%H:%M UTC")
                            pretty_time = f"{pretty_time_cst} / {pretty_time_utc}"
                        except Exception:
                            pretty_time = ""

                    # Patch: If game is scheduled but time has passed, show as in progress
                    if status.strip().upper() == "NS" and event_time_utc:
                        try:
                            dt_utc_check = datetime.datetime.strptime(event_time_utc, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                            if dt_utc_check > now_utc:
                                # Pregame, show scheduled time
                                if pretty_time:
                                    upcoming.append({
                                        "msg": f"{away_abbr} at {home_abbr} {pretty_time}",
                                        "dt": dt_utc_check
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

                    tag = parse_status(status, progress)

                    try:
                        if tag == "PPD":
                            in_progress.append(f"{away_abbr} at {home_abbr} PPD")
                        elif tag.startswith("F"):
                            finished.append(f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} {tag}")
                        elif tag:
                            in_progress.append(f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} {tag}")
                        else:
                            upcoming.append({
                                "msg": f"{away_abbr} at {home_abbr}",
                                "dt": datetime.datetime.max.replace(tzinfo=datetime.timezone.utc)
                            })
                    except Exception as e:
                        messages.append(f"NBA Formatter Error: {e} ({away_abbr} @ {home_abbr})")

                if upcoming:
                    upcoming.sort(key=lambda x: x["dt"])
                    upcoming_msgs = [g["msg"] for g in upcoming]
                else:
                    upcoming_msgs = []

                messages.extend(in_progress)
                messages.extend(upcoming_msgs)
                messages.extend(finished)
    except Exception as e:
        messages.append(f"NBA ERROR: {e}")

    return messages