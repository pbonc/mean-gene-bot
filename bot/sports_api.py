import aiohttp
import asyncio
import time
from datetime import datetime, timedelta
from typing import List

class SportsAPIManager:
    def __init__(self):
        self.cache = {}
        self.cache_duration = 300  # 5 minutes
        self.last_update = {}
        self.enabled = True  # Can be disabled if causing startup issues
        self.startup_time = time.time()
        self.startup_delay = 5  # Wait 5 seconds after startup before making API calls
        
        # API endpoints - switch to ESPN for current data
        self.espn_nhl_base = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
        self.espn_nba_base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
        self.espn_mlb_base = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
        self.espn_nfl_base = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
        self.sportsdb_base = "https://www.thesportsdb.com/api/v1/json/3"

    def get_current_streaming_day(self):
        """
        Get the current 'streaming day' date with 5 AM reset.
        If it's before 5 AM, consider it the previous calendar day.
        Returns date in YYYY-MM-DD format.
        """
        # Get current time in local timezone (assuming system timezone is correct)
        now = datetime.now()
        
        # If it's before 5 AM, subtract one day to get the "streaming day"
        if now.hour < 5:
            streaming_day = now - timedelta(days=1)
        else:
            streaming_day = now
        
        return streaming_day.strftime("%Y-%m-%d")
    
    def is_game_recent_or_current(self, game_date_str):
        """
        Check if a game is from recent days (more permissive for ticker).
        This allows showing recent final games and current live games.
        Includes yesterday, today, and tomorrow to catch late-night games.
        """
        try:
            now = datetime.now()
            yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            today = now.strftime("%Y-%m-%d")
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            
            # Parse the game date
            if 'T' in game_date_str:
                game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
                game_day = game_date.strftime("%Y-%m-%d")
                return game_day in [yesterday, today, tomorrow]
            else:
                # If no time component, just check date
                return game_date_str in [yesterday, today, tomorrow]
        except Exception:
            return False
    
    def is_game_on_streaming_day(self, game_date_str):
        """
        Check if a game date matches the current streaming day.
        game_date_str should be in ISO format (YYYY-MM-DDTHH:MM:SSZ)
        """
        try:
            current_day = self.get_current_streaming_day()
            
            # Parse the game date
            if 'T' in game_date_str:
                game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00'))
            else:
                game_date = datetime.fromisoformat(game_date_str)
            
            game_day = game_date.strftime("%Y-%m-%d")
            return game_day == current_day
            
        except Exception as e:
            print(f"[SPORTS] Error parsing game date {game_date_str}: {e}")
            return False  # If we can't parse, exclude the game

    def format_game_time(self, clock_seconds):
        """Convert clock seconds to MM:SS format for display"""
        if not clock_seconds or clock_seconds == 0:
            return "0:00"
        
        # Convert seconds to minutes:seconds
        minutes = int(clock_seconds // 60)
        seconds = int(clock_seconds % 60)
        return f"{minutes}:{seconds:02d}"

    async def fetch_nhl_scores(self) -> List[str]:
        """Fetch NHL scores from ESPN API"""
        
        # Check cache first - only fetch once every 5 minutes
        now = time.time()
        if ('nhl_scores' in self.cache and 
            'nhl_scores' in self.last_update and 
            now - self.last_update['nhl_scores'] < self.cache_duration):
            return self.cache['nhl_scores']
        
        print("[SPORTS] Fetching NHL data...")
        messages = []
        try:
            timeout = aiohttp.ClientTimeout(total=8, connect=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.espn_nhl_base}/scoreboard"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        events = data.get('events', [])
                        
                        # Separate games by status for better display order
                        live_games = []
                        final_games = []
                        upcoming_games = []
                        
                        print(f"[SPORTS] NHL: Filtering for recent games (live games always included)")
                        
                        for event in events:
                            competitions = event.get('competitions', [])
                            if not competitions:
                                continue
                                
                            competition = competitions[0]
                            status = competition.get('status', {})
                            status_type = status.get('type', {}).get('name', '')
                            
                            # Always include live/in-progress games regardless of date
                            is_live = 'PROGRESS' in status_type or 'LIVE' in status_type
                            
                            # For non-live games, check if recent
                            if not is_live:
                                event_date = event.get('date')
                                if not event_date or not self.is_game_recent_or_current(event_date):
                                    continue  # Skip non-live games not from recent days
                            competitors = competition.get('competitors', [])

                            # Find home and away entries (ESPN marks homeAway)
                            home = None
                            away = None
                            for comp in competitors:
                                if comp.get('homeAway') == 'home':
                                    home = comp
                                elif comp.get('homeAway') == 'away':
                                    away = comp
                            # Fallback to positional if missing
                            if home is None and len(competitors) >= 1:
                                home = competitors[0]
                            if away is None and len(competitors) >= 2:
                                away = competitors[1]

                            if not home or not away:
                                continue

                            def team_abbr(comp):
                                t = comp.get('team', {})
                                # Prefer 'abbreviation' or 'shortDisplayName' or triCode
                                for key in ('abbreviation', 'triCode', 'shortDisplayName', 'shortName', 'displayName'):
                                    val = t.get(key) if isinstance(t, dict) else None
                                    if val:
                                        return str(val)
                                return 'UNK'

                            home_team = team_abbr(home)
                            away_team = team_abbr(away)
                            home_score = home.get('score', '0')
                            away_score = away.get('score', '0')

                            # Get game status and timing info
                            status_type = status.get('type', {}).get('description', '')
                            status_detail = status.get('type', {}).get('detail', '')
                            status_short_detail = status.get('type', {}).get('shortDetail', '')
                            clock = status.get('clock', 0)
                            period = status.get('period', 0)

                            # Categorize games by status
                            if status_type and 'In Progress' in status_type:
                                time_display = self.format_game_time(clock)
                                period_display = f"P{period}" if period else "P1"
                                msg = f"🏒 {away_team} {away_score}-{home_score} {home_team} ({period_display} {time_display})"
                                live_games.append(msg)
                            elif status_type and ('Final' in status_type or 'Final' == status_type):
                                msg = f"🏒 {away_team} {away_score}-{home_score} {home_team} (F)"
                                final_games.append(msg)
                            elif status_type and ('Scheduled' in status_type or 'Pre-Game' in status_type or 'Preview' in status_type):
                                start_time = status_short_detail if status_short_detail else status_detail
                                if not start_time or start_time == status_type:
                                    # Try extracting a start time from event if available
                                    evt_date = event.get('date')
                                    if evt_date:
                                        try:
                                            dt = datetime.fromisoformat(evt_date.replace('Z', '+00:00'))
                                            start_time = dt.strftime('%I:%M %p').lstrip('0')
                                        except Exception:
                                            start_time = 'TBD'
                                    else:
                                        start_time = 'TBD'
                                msg = f"🏒 {away_team} @ {home_team} ({start_time})"
                                upcoming_games.append(msg)
                            else:
                                # Other statuses: postponed, delayed, etc.
                                if home_score != '0' or away_score != '0':
                                    msg = f"🏒 {away_team} {away_score}-{home_score} {home_team} ({status_type})"
                                else:
                                    msg = f"🏒 {away_team} @ {home_team} ({status_type or 'TBD'})"
                                # classify as upcoming if postponed/delayed, else final
                                if status_type and ('postponed' in status_type.lower() or 'delayed' in status_type.lower()):
                                    upcoming_games.append(msg)
                                else:
                                    final_games.append(msg)
                        
                        # Show ALL games found (prioritize live first)
                        messages.extend(live_games)     # All live games
                        messages.extend(upcoming_games) # All upcoming games  
                        messages.extend(final_games)    # All final games
                        
                        print(f"[SPORTS] NHL: Found {len(live_games)} live, {len(upcoming_games)} upcoming, {len(final_games)} final games")
                        
                    else:
                        print(f"[SPORTS] NHL: ESPN API returned status: {response.status}")
                        return []
        except asyncio.TimeoutError:
            print(f"[SPORTS] NHL: Request timed out")
            return []
        except aiohttp.ClientError as e:
            print(f"[SPORTS] NHL: Network error: {e}")
            return []
        except Exception as e:
            print(f"[SPORTS] NHL: Unexpected error: {e}")
            return []
        
        # Cache the results for 5 minutes
        self.cache['nhl_scores'] = messages
        self.last_update['nhl_scores'] = now
        
        print(f"[SPORTS] Cached {len(messages)} NHL messages")
        return messages

    async def fetch_mlb_scores(self) -> List[str]:
        """Fetch MLB scores from ESPN API"""
        now = time.time()
        if ('mlb_scores' in self.cache and
            'mlb_scores' in self.last_update and
            now - self.last_update['mlb_scores'] < self.cache_duration):
            return self.cache['mlb_scores']

        print("[SPORTS] Fetching MLB data...")
        messages = []
        try:
            timeout = aiohttp.ClientTimeout(total=8, connect=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.espn_mlb_base}/scoreboard"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        events = data.get('events', [])

                        live_games = []
                        final_games = []
                        upcoming_games = []

                        print(f"[SPORTS] MLB: Filtering for recent games (live games always included)")
                      
                        for event in events:
                            competitions = event.get('competitions', [])
                            if not competitions:
                                continue
                                
                            competition = competitions[0]
                            status = competition.get('status', {})
                            status_type = status.get('type', {}).get('name', '')
                            
                            # Always include live/in-progress games regardless of date
                            is_live = 'PROGRESS' in status_type or 'LIVE' in status_type
                            
                            # For non-live games, check if recent
                            if not is_live:
                                event_date = event.get('date')
                                if not event_date or not self.is_game_recent_or_current(event_date):
                                    continue  # Skip non-live games not from recent days
                            competitors = competition.get('competitors', [])
                            status = competition.get('status', {})

                            # Find home and away entries
                            home = None
                            away = None
                            for comp in competitors:
                                if comp.get('homeAway') == 'home':
                                    home = comp
                                elif comp.get('homeAway') == 'away':
                                    away = comp
                            if home is None and len(competitors) >= 1:
                                home = competitors[0]
                            if away is None and len(competitors) >= 2:
                                away = competitors[1]

                            if not home or not away:
                                continue

                            def team_abbr(comp):
                                t = comp.get('team', {})
                                for key in ('abbreviation', 'triCode', 'shortDisplayName', 'shortName', 'displayName'):
                                    val = t.get(key) if isinstance(t, dict) else None
                                    if val:
                                        return str(val)
                                return 'UNK'

                            home_team = team_abbr(home)
                            away_team = team_abbr(away)
                            home_score = home.get('score', '0')
                            away_score = away.get('score', '0')

                            status_type = status.get('type', {}).get('description', '')
                            status_detail = status.get('type', {}).get('detail', '')
                            status_short_detail = status.get('type', {}).get('shortDetail', '')
                            clock = status.get('clock', 0)
                            period = status.get('period', 0)

                            # MLB uses innings rather than periods/clock
                            if status_type and 'In Progress' in status_type:
                                inning = f"I{period}" if period else 'I'
                                # ESPN sometimes provides human-readable inning state (e.g. "Bot 9") in shortDetail
                                time_display = (status_short_detail or status_detail or '').strip()
                                if time_display:
                                    # If shortDetail already contains Top/Bot or similar, prefer it alone (e.g. "Bot 9")
                                    td_lower = time_display.lower()
                                    if any(k in td_lower for k in ('top', 'bot', 'bottom', 'inning')):
                                        msg = f"⚾ {away_team} {away_score}-{home_score} {home_team} ({time_display})"
                                    else:
                                        msg = f"⚾ {away_team} {away_score}-{home_score} {home_team} ({inning} {time_display})"
                                else:
                                    # fallback to a generic 'Live'
                                    msg = f"⚾ {away_team} {away_score}-{home_score} {home_team} ({inning} Live)"
                                live_games.append(msg)
                            elif status_type and ('Final' in status_type or status_type == 'Final'):
                                msg = f"⚾ {away_team} {away_score}-{home_score} {home_team} (F)"
                                final_games.append(msg)
                            elif status_type and ('Scheduled' in status_type or 'Pre-Game' in status_type or 'Preview' in status_type):
                                start_time = status_short_detail if status_short_detail else status_detail
                                if not start_time or start_time == status_type:
                                    evt_date = event.get('date')
                                    if evt_date:
                                        try:
                                            dt = datetime.fromisoformat(evt_date.replace('Z', '+00:00'))
                                            start_time = dt.strftime('%I:%M %p').lstrip('0')
                                        except Exception:
                                            start_time = 'TBD'
                                    else:
                                        start_time = 'TBD'
                                msg = f"⚾ {away_team} @ {home_team} ({start_time})"
                                upcoming_games.append(msg)
                            else:
                                if home_score != '0' or away_score != '0':
                                    msg = f"⚾ {away_team} {away_score}-{home_score} {home_team} ({status_type})"
                                else:
                                    msg = f"⚾ {away_team} @ {home_team} ({status_type or 'TBD'})"
                                if status_type and ('postponed' in status_type.lower() or 'delayed' in status_type.lower()):
                                    upcoming_games.append(msg)
                                else:
                                    final_games.append(msg)

                        messages.extend(live_games)
                        messages.extend(upcoming_games)
                        messages.extend(final_games)
                        print(f"[SPORTS] Found {len(live_games)} live, {len(upcoming_games)} upcoming, {len(final_games)} final MLB games")
                    else:
                        print(f"[SPORTS] ESPN MLB API returned status: {response.status}")
        except Exception as e:
            print(f"[SPORTS] Exception fetching MLB: {e}")
            return []

        self.cache['mlb_scores'] = messages
        self.last_update['mlb_scores'] = now
        print(f"[SPORTS] Cached {len(messages)} MLB messages")
        return messages

    async def fetch_nba_scores(self) -> List[str]:
        """Fetch NBA scores from ESPN API"""
        now = time.time()
        if ('nba_scores' in self.cache and
            'nba_scores' in self.last_update and
            now - self.last_update['nba_scores'] < self.cache_duration):
            return self.cache['nba_scores']

        print("[SPORTS] Fetching NBA data...")
        messages = []
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.espn_nba_base}/scoreboard"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        events = data.get('events', [])

                        live_games = []
                        final_games = []
                        upcoming_games = []

                        print(f"[SPORTS] NBA: Filtering for recent games (live games always included)")
                        
                        for event in events:
                            competitions = event.get('competitions', [])
                            if not competitions:
                                continue
                                
                            competition = competitions[0]
                            status = competition.get('status', {})
                            status_type = status.get('type', {}).get('name', '')
                            
                            # Always include live/in-progress games regardless of date
                            is_live = 'PROGRESS' in status_type or 'LIVE' in status_type
                            
                            # For non-live games, check if recent
                            if not is_live:
                                event_date = event.get('date')
                                if not event_date or not self.is_game_recent_or_current(event_date):
                                    continue  # Skip non-live games not from recent days
                            competitors = competition.get('competitors', [])

                            home = None
                            away = None
                            for comp in competitors:
                                if comp.get('homeAway') == 'home':
                                    home = comp
                                elif comp.get('homeAway') == 'away':
                                    away = comp
                            if home is None and len(competitors) >= 1:
                                home = competitors[0]
                            if away is None and len(competitors) >= 2:
                                away = competitors[1]

                            if not home or not away:
                                continue

                            def team_abbr(comp):
                                t = comp.get('team', {})
                                for key in ('abbreviation', 'triCode', 'shortDisplayName', 'shortName', 'displayName'):
                                    val = t.get(key) if isinstance(t, dict) else None
                                    if val:
                                        return str(val)
                                return 'UNK'

                            home_team = team_abbr(home)
                            away_team = team_abbr(away)
                            home_score = home.get('score', '0')
                            away_score = away.get('score', '0')

                            status_type = status.get('type', {}).get('description', '')
                            status_detail = status.get('type', {}).get('detail', '')
                            status_short_detail = status.get('type', {}).get('shortDetail', '')
                            clock = status.get('clock', 0)
                            period = status.get('period', 0)

                            if status_type and 'In Progress' in status_type:
                                time_display = self.format_game_time(clock)
                                period_display = f"Q{period}" if period else "Q1"
                                msg = f"🏀 {away_team} {away_score}-{home_score} {home_team} ({period_display} {time_display})"
                                live_games.append(msg)
                            elif status_type and ('Final' in status_type or status_type == 'Final'):
                                msg = f"🏀 {away_team} {away_score}-{home_score} {home_team} (F)"
                                final_games.append(msg)
                            elif status_type and ('Scheduled' in status_type or 'Pre-Game' in status_type or 'Preview' in status_type):
                                start_time = status_short_detail if status_short_detail else status_detail
                                if not start_time or start_time == status_type:
                                    evt_date = event.get('date')
                                    if evt_date:
                                        try:
                                            dt = datetime.fromisoformat(evt_date.replace('Z', '+00:00'))
                                            start_time = dt.strftime('%I:%M %p').lstrip('0')
                                        except Exception:
                                            start_time = 'TBD'
                                    else:
                                        start_time = 'TBD'
                                msg = f"🏀 {away_team} @ {home_team} ({start_time})"
                                upcoming_games.append(msg)
                            else:
                                if home_score != '0' or away_score != '0':
                                    msg = f"🏀 {away_team} {away_score}-{home_score} {home_team} ({status_type})"
                                else:
                                    msg = f"🏀 {away_team} @ {home_team} ({status_type or 'TBD'})"
                                if status_type and ('postponed' in status_type.lower() or 'delayed' in status_type.lower()):
                                    upcoming_games.append(msg)
                                else:
                                    final_games.append(msg)

                        messages.extend(live_games)
                        messages.extend(upcoming_games)
                        messages.extend(final_games)
                        print(f"[SPORTS] Found {len(live_games)} live, {len(upcoming_games)} upcoming, {len(final_games)} final NBA games")
                    else:
                        print(f"[SPORTS] ESPN NBA API returned status: {response.status}")
        except Exception as e:
            print(f"[SPORTS] Exception fetching NBA: {e}")
            return []

        self.cache['nba_scores'] = messages
        self.last_update['nba_scores'] = now
        print(f"[SPORTS] Cached {len(messages)} NBA messages")
        return messages

    async def fetch_nfl_scores(self) -> List[str]:
        """Fetch NFL scores from ESPN API"""
        now = time.time()
        if ('nfl_scores' in self.cache and
            'nfl_scores' in self.last_update and
            now - self.last_update['nfl_scores'] < self.cache_duration):
            return self.cache['nfl_scores']

        print("[SPORTS] Fetching NFL data...")
        messages = []
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{self.espn_nfl_base}/scoreboard"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        events = data.get('events', [])

                        live_games = []
                        final_games = []
                        upcoming_games = []

                        print(f"[SPORTS] NFL: Filtering for recent games (live games always included)")
                        
                        for event in events:
                            competitions = event.get('competitions', [])
                            if not competitions:
                                continue
                                
                            competition = competitions[0]
                            status = competition.get('status', {})
                            status_type = status.get('type', {}).get('name', '')
                            
                            # Always include live/in-progress games regardless of date
                            is_live = 'PROGRESS' in status_type or 'LIVE' in status_type
                            
                            # For non-live games, check if recent
                            if not is_live:
                                event_date = event.get('date')
                                if not event_date or not self.is_game_recent_or_current(event_date):
                                    continue  # Skip non-live games not from recent days
                            competitors = competition.get('competitors', [])
                            status = competition.get('status', {})

                            home = None
                            away = None
                            for comp in competitors:
                                if comp.get('homeAway') == 'home':
                                    home = comp
                                elif comp.get('homeAway') == 'away':
                                    away = comp
                            if home is None and len(competitors) >= 1:
                                home = competitors[0]
                            if away is None and len(competitors) >= 2:
                                away = competitors[1]

                            if not home or not away:
                                continue

                            def team_abbr(comp):
                                t = comp.get('team', {})
                                for key in ('abbreviation', 'triCode', 'shortDisplayName', 'shortName', 'displayName'):
                                    val = t.get(key) if isinstance(t, dict) else None
                                    if val:
                                        return str(val)
                                return 'UNK'

                            home_team = team_abbr(home)
                            away_team = team_abbr(away)
                            home_score = home.get('score', '0')
                            away_score = away.get('score', '0')

                            status_type = status.get('type', {}).get('description', '')
                            status_detail = status.get('type', {}).get('detail', '')
                            status_short_detail = status.get('type', {}).get('shortDetail', '')
                            clock = status.get('clock', 0)
                            period = status.get('period', 0)

                            # NFL uses quarters; clock is seconds remaining in quarter
                            if status_type and 'In Progress' in status_type:
                                time_display = self.format_game_time(clock)
                                period_display = f"Q{period}" if period else "Q1"
                                msg = f"🏈 {away_team} {away_score}-{home_score} {home_team} ({period_display} {time_display})"
                                live_games.append(msg)
                            elif status_type and ('Final' in status_type or status_type == 'Final'):
                                msg = f"🏈 {away_team} {away_score}-{home_score} {home_team} (F)"
                                final_games.append(msg)
                            elif status_type and ('Scheduled' in status_type or 'Pre-Game' in status_type or 'Preview' in status_type):
                                start_time = status_short_detail if status_short_detail else status_detail
                                if not start_time or start_time == status_type:
                                    evt_date = event.get('date')
                                    if evt_date:
                                        try:
                                            dt = datetime.fromisoformat(evt_date.replace('Z', '+00:00'))
                                            start_time = dt.strftime('%I:%M %p').lstrip('0')
                                        except Exception:
                                            start_time = 'TBD'
                                    else:
                                        start_time = 'TBD'
                                msg = f"🏈 {away_team} @ {home_team} ({start_time})"
                                upcoming_games.append(msg)
                            else:
                                if home_score != '0' or away_score != '0':
                                    msg = f"🏈 {away_team} {away_score}-{home_score} {home_team} ({status_type})"
                                else:
                                    msg = f"🏈 {away_team} @ {home_team} ({status_type or 'TBD'})"
                                if status_type and ('postponed' in status_type.lower() or 'delayed' in status_type.lower()):
                                    upcoming_games.append(msg)
                                else:
                                    final_games.append(msg)

                        messages.extend(live_games)
                        messages.extend(upcoming_games)
                        messages.extend(final_games)
                        print(f"[SPORTS] Found {len(live_games)} live, {len(upcoming_games)} upcoming, {len(final_games)} final NFL games")
                    else:
                        print(f"[SPORTS] ESPN NFL API returned status: {response.status}")
        except Exception as e:
            print(f"[SPORTS] Exception fetching NFL: {e}")
            return []

        self.cache['nfl_scores'] = messages
        self.last_update['nfl_scores'] = now
        print(f"[SPORTS] Cached {len(messages)} NFL messages")
        return messages

    async def get_sports_messages(self) -> List[str]:
        """Get sports messages for ticker with robust error handling"""
        if not self.enabled:
            print("[SPORTS] Sports API disabled, skipping")
            return []
        
        # Skip sports data during initial startup to prevent blocking
        elapsed_since_startup = time.time() - self.startup_time
        if elapsed_since_startup < self.startup_delay:
            print(f"[SPORTS] Skipping sports fetch during startup ({elapsed_since_startup:.1f}s < {self.startup_delay}s)")
            return []
            
        print("[SPORTS] Starting sports data fetch...")
        combined = []
        
        # Fetch each sport with individual timeouts and error handling
        sports_fetchers = [
            ("NHL", self.fetch_nhl_scores),
            ("NBA", self.fetch_nba_scores),
            ("MLB", self.fetch_mlb_scores),
            ("NFL", self.fetch_nfl_scores)
        ]
        
        for sport_name, fetch_func in sports_fetchers:
            try:
                # Add per-sport timeout to prevent hanging
                messages = await asyncio.wait_for(fetch_func(), timeout=15.0)
                if messages:
                    combined.extend(messages)
                    print(f"[SPORTS] {sport_name}: {len(messages)} messages")
                else:
                    print(f"[SPORTS] {sport_name}: No games found")
            except asyncio.TimeoutError:
                print(f"[SPORTS] {sport_name}: Timeout after 15s, skipping")
                continue
            except Exception as e:
                print(f"[SPORTS] {sport_name}: Error - {e}, skipping")
                continue
        
        print(f"[SPORTS] Total sports messages: {len(combined)}")
        return combined
