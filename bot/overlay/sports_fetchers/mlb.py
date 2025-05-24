import aiohttp
import datetime
import pytz
import re

MLB_TEAM_NAMES = {
    "Arizona Diamondbacks", "Atlanta Braves", "Baltimore Orioles", "Boston Red Sox",
    "Chicago Cubs", "Chicago White Sox", "Cincinnati Reds", "Cleveland Guardians",
    "Colorado Rockies", "Detroit Tigers", "Houston Astros", "Kansas City Royals",
    "Los Angeles Angels", "Los Angeles Dodgers", "Miami Marlins", "Milwaukee Brewers",
    "Minnesota Twins", "New York Mets", "New York Yankees", "Oakland Athletics",
    "Philadelphia Phillies", "Pittsburgh Pirates", "San Diego Padres", "San Francisco Giants",
    "Seattle Mariners", "St. Louis Cardinals", "Tampa Bay Rays", "Texas Rangers",
    "Toronto Blue Jays", "Washington Nationals", "Athletics"
}

MLB_TEAM_ABBR = {
    "Arizona Diamondbacks": "ARI", "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CWS", "Cincinnati Reds": "CIN", "Cleveland Guardians": "CLE",
    "Colorado Rockies": "COL", "Detroit Tigers": "DET", "Houston Astros": "HOU", "Kansas City Royals": "KC",
    "Los Angeles Angels": "LAA", "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN", "New York Mets": "NYM", "New York Yankees": "NYY", "Oakland Athletics": "OAK",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT", "San Diego Padres": "SD", "San Francisco Giants": "SF",
    "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TB", "Texas Rangers": "TEX",
    "Toronto Blue Jays": "TOR", "Washington Nationals": "WSH", "Athletics": "OAK"
}

def safe_score(val):
    try:
        return int(val)
    except Exception:
        return 0

def extract_final_inning(str_result, home_score, away_score):
    """
    Parse the inning breakdown in strResult to determine final inning played.
    If the breakdown is missing an extra inning, try to infer from the score.
    """
    if not str_result:
        return 9
    # Find all 'Innings:<br>X X X X ...' groups
    inning_lines = re.findall(r'Innings:<br>([0-9 ]+)', str_result.replace('\n',''))
    inning_numbers = []
    last_runs = []
    if inning_lines:
        for line in inning_lines:
            nums = [int(x) for x in line.strip().split() if x.isdigit()]
            inning_numbers.append(len(nums))
            if nums:
                last_runs.append(nums[-1])
        if inning_numbers:
            max_inning = max(inning_numbers)
            if max_inning == 10 and any(x > 0 for x in last_runs):
                return 11
            return max_inning
    return 9

def parse_inning_status(status: str, progress: str, inning_field):
    s = (progress or status or '').upper().replace(" ", "")
    arrow, inning, is_end = None, None, False
    progress_str = ""
    is_extra = False
    targets = [progress, status]
    for t in targets:
        if not t:
            continue
        ts = t.upper().replace(" ", "")
        if ts.startswith("TOP"):
            arrow = "▲"
            try: inning = int(ts[3:])
            except Exception: inning = None
            progress_str = f"{arrow}{inning}" if inning else ""
            break
        elif ts.startswith("BOT"):
            arrow = "▼"
            try: inning = int(ts[3:])
            except Exception: inning = None
            progress_str = f"{arrow}{inning}" if inning else ""
            break
        elif ts.startswith("END"):
            is_end = True
            try: inning = int(ts[3:])
            except Exception: inning = None
            progress_str = f"E{inning}" if inning else ""
            break
        elif ts.startswith("IN"):
            try: inning = int(ts[2:])
            except Exception: inning = None
            arrow = "▲"
            progress_str = f"{arrow}{inning}" if inning else ""
            break
    if inning is None and inning_field:
        try:
            inning = int(inning_field)
        except Exception:
            pass
    if inning and inning > 9:
        is_extra = True
    return arrow, inning, is_end, progress_str, is_extra

def get_team_abbr(name: str) -> str:
    return MLB_TEAM_ABBR.get(name, name)

def is_final_status(status, progress):
    s = (status or "").strip().upper()
    p = (progress or "").strip().upper()
    if any(x in p for x in ("TOP", "BOT", "END")):
        return False
    if p.startswith("IN"):
        try:
            int(p[2:])
            return False
        except Exception:
            pass
    if any(word == s for word in ("FT", "FINAL", "F")):
        return True
    return False

def is_in_progress(status, progress):
    s = (status or "").strip().upper()
    p = (progress or "").strip().upper()
    if "TOP" in p or "BOT" in p or "END" in p:
        return True
    if p.startswith("IN"):
        try:
            int(p[2:])
            return True
        except Exception:
            pass
    if "TOP" in s or "BOT" in s or "END" in s:
        return True
    if s.startswith("IN"):
        try:
            int(s[2:])
            return True
        except Exception:
            pass
    if s == "NS":
        return False
    return False

async def get_today_mlb_scores(api_key: str):
    central = pytz.timezone("America/Chicago")
    today_cst = datetime.datetime.now(central).date()
    url = f"https://www.thesportsdb.com/api/v1/json/{api_key}/eventsday.php?d={today_cst.strftime('%Y-%m-%d')}&l=MLB"
    messages = ["MLB Scores"]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                events = data.get("events")
                if not events:
                    return messages

                finished = []
                in_progress = []
                upcoming = []

                for event in events:
                    home = event.get("strHomeTeam")
                    away = event.get("strAwayTeam")
                    home_abbr = get_team_abbr(home)
                    away_abbr = get_team_abbr(away)
                    home_score = event.get("intHomeScore")
                    away_score = event.get("intAwayScore")
                    status = event.get("strStatus", "")
                    progress = event.get("strProgress", "")
                    inning_field = event.get("strInning")
                    str_result = event.get("strResult")
                    event_time_utc = event.get("strTimestamp")

                    if event_time_utc:
                        dt_utc = datetime.datetime.strptime(event_time_utc, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.utc)
                        dt_cst = dt_utc.astimezone(central)
                        pretty_time_cst = dt_cst.strftime("%I:%M %p CST").lstrip("0")
                        pretty_time_utc = dt_utc.strftime("%H:%M UTC")
                        if dt_cst.date() != today_cst:
                            continue
                        pretty_time = f"{pretty_time_cst} / {pretty_time_utc}"
                    else:
                        pretty_time = ""
                        dt_cst = None

                    if home in MLB_TEAM_NAMES and away in MLB_TEAM_NAMES:
                        status_up = (status or '').upper()
                        # Patch: treat POST as PPD for user clarity
                        if status_up == "POST":
                            status_up = "PPD"
                        arrow, inning, is_end, progress_str, is_extra = parse_inning_status(status, progress, inning_field)

                        if any(x in status_up for x in ["PPD", "WD", "DELAY", "POSTPONED", "CANCELLED"]):
                            in_progress.append(
                                f"{away_abbr} at {home_abbr} PPD"
                            )
                        elif is_final_status(status, progress):
                            final_inning = extract_final_inning(str_result, home_score, away_score) or inning or 9
                            if final_inning > 9:
                                finished.append(
                                    f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} F/{final_inning}"
                                )
                            else:
                                finished.append(
                                    f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} F"
                                )
                        elif is_in_progress(status, progress):
                            if arrow and inning:
                                tag = f"{arrow}{inning}"
                            elif progress_str:
                                tag = progress_str
                            elif inning:
                                tag = f"{inning}"
                            else:
                                tag = ""
                            in_progress.append(
                                f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} {tag}"
                            )
                        elif status in ("NS", "", None):
                            if pretty_time and dt_cst is not None:
                                upcoming.append({
                                    "msg": f"{away_abbr} at {home_abbr} Starts {pretty_time}",
                                    "dt": dt_cst
                                })
                            else:
                                upcoming.append({
                                    "msg": f"{away_abbr} at {home_abbr} Scheduled",
                                    "dt": datetime.datetime.max.replace(tzinfo=central)
                                })
                        else:
                            if home_score is not None and away_score is not None:
                                in_progress.append(
                                    f"{away_abbr} {safe_score(away_score)} - {home_abbr} {safe_score(home_score)} {status}"
                                )
                            else:
                                upcoming.append({
                                    "msg": f"{away_abbr} at {home_abbr} {status}",
                                    "dt": datetime.datetime.max.replace(tzinfo=central)
                                })

                if upcoming:
                    upcoming.sort(key=lambda x: x["dt"])
                    upcoming_msgs = [g["msg"] for g in upcoming]
                else:
                    upcoming_msgs = []

                messages.extend(in_progress)
                messages.extend(upcoming_msgs)
                messages.extend(finished)

    except Exception as e:
        print(f"[MLB ERROR - score fetch]: {e}")

    return messages