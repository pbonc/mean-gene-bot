import aiohttp
import asyncio
import time
from datetime import datetime, timedelta
from typing import List
import pytz

class SportsAPIManager:
    def __init__(self):
        self.cache = {}
        self.cache_duration = 300  # 5 minutes
        self.last_update = {}
        
        # API endpoints for multiple sports
        self.espn_nhl_base = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
        self.espn_nba_base = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
        self.espn_mlb_base = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb"
        self.espn_nfl_base = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
        
        # Set up timezone
        self.central_tz = pytz.timezone('America/Chicago')

    def get_team_abbreviation(self, league_name, team_name):
        """Get 3-letter team abbreviation if available, otherwise return full team name"""
        try:
            # Direct mapping from full team names to abbreviations
            team_abbreviations = {
                # NFL teams
                'Arizona Cardinals': 'ARI',
                'Atlanta Falcons': 'ATL',
                'Baltimore Ravens': 'BAL',
                'Buffalo Bills': 'BUF',
                'Carolina Panthers': 'CAR',
                'Chicago Bears': 'CHI',
                'Cincinnati Bengals': 'CIN',
                'Cleveland Browns': 'CLE',
                'Dallas Cowboys': 'DAL',
                'Denver Broncos': 'DEN',
                'Detroit Lions': 'DET',
                'Green Bay Packers': 'GB',
                'Houston Texans': 'HOU',
                'Indianapolis Colts': 'IND',
                'Jacksonville Jaguars': 'JAX',
                'Kansas City Chiefs': 'KC',
                'Las Vegas Raiders': 'LV',
                'Los Angeles Chargers': 'LAC',
                'Los Angeles Rams': 'LAR',
                'Miami Dolphins': 'MIA',
                'Minnesota Vikings': 'MIN',
                'New England Patriots': 'NE',
                'New Orleans Saints': 'NO',
                'New York Giants': 'NYG',
                'New York Jets': 'NYJ',
                'Philadelphia Eagles': 'PHI',
                'Pittsburgh Steelers': 'PIT',
                'San Francisco 49ers': 'SF',
                'Seattle Seahawks': 'SEA',
                'Tampa Bay Buccaneers': 'TB',
                'Tennessee Titans': 'TEN',
                'Washington Commanders': 'WAS',
                
                # NBA teams
                'Atlanta Hawks': 'ATL',
                'Boston Celtics': 'BOS',
                'Brooklyn Nets': 'BKN',
                'Charlotte Hornets': 'CHA',
                'Chicago Bulls': 'CHI',
                'Cleveland Cavaliers': 'CLE',
                'Dallas Mavericks': 'DAL',
                'Denver Nuggets': 'DEN',
                'Detroit Pistons': 'DET',
                'Golden State Warriors': 'GSW',
                'Houston Rockets': 'HOU',
                'Indiana Pacers': 'IND',
                'Los Angeles Clippers': 'LAC',
                'Los Angeles Lakers': 'LAL',
                'Memphis Grizzlies': 'MEM',
                'Miami Heat': 'MIA',
                'Milwaukee Bucks': 'MIL',
                'Minnesota Timberwolves': 'MIN',
                'New Orleans Pelicans': 'NOP',
                'New York Knicks': 'NYK',
                'Oklahoma City Thunder': 'OKC',
                'Orlando Magic': 'ORL',
                'Philadelphia 76ers': 'PHI',
                'Phoenix Suns': 'PHX',
                'Portland Trail Blazers': 'POR',
                'Sacramento Kings': 'SAC',
                'San Antonio Spurs': 'SAS',
                'Toronto Raptors': 'TOR',
                'Utah Jazz': 'UTA',
                'Washington Wizards': 'WAS',
                
                # NHL teams
                'Anaheim Ducks': 'ANA',
                'Boston Bruins': 'BOS',
                'Buffalo Sabres': 'BUF',
                'Calgary Flames': 'CGY',
                'Carolina Hurricanes': 'CAR',
                'Chicago Blackhawks': 'CHI',
                'Colorado Avalanche': 'COL',
                'Columbus Blue Jackets': 'CBJ',
                'Dallas Stars': 'DAL',
                'Detroit Red Wings': 'DET',
                'Edmonton Oilers': 'EDM',
                'Florida Panthers': 'FLA',
                'Los Angeles Kings': 'LAK',
                'Minnesota Wild': 'MIN',
                'Montreal Canadiens': 'MTL',
                'Nashville Predators': 'NSH',
                'New Jersey Devils': 'NJD',
                'New York Islanders': 'NYI',
                'New York Rangers': 'NYR',
                'Ottawa Senators': 'OTT',
                'Philadelphia Flyers': 'PHI',
                'Pittsburgh Penguins': 'PIT',
                'San Jose Sharks': 'SJS',
                'St. Louis Blues': 'STL',
                'Tampa Bay Lightning': 'TBL',
                'Toronto Maple Leafs': 'TOR',
                'Vancouver Canucks': 'VAN',
                'Vegas Golden Knights': 'VGK',
                'Washington Capitals': 'WSH',
                'Winnipeg Jets': 'WPG',
                'Seattle Kraken': 'SEA',
                'Utah Hockey Club': 'UTA',  # Utah NHL team abbreviation
                # Some data sources may call the Utah team "Utah Mammoth" or similar;
                # include common variants so the ticker shows the desired 3-letter code.
                'Utah Mammoth': 'UTA',
                'Utah Mammoths': 'UTA',
                'Mammoth': 'UTA',
                
                # MLB teams
                'Arizona Diamondbacks': 'ARI',
                'Atlanta Braves': 'ATL',
                'Baltimore Orioles': 'BAL',
                'Boston Red Sox': 'BOS',
                'Chicago Cubs': 'CHC',
                'Chicago White Sox': 'CWS',
                'Cincinnati Reds': 'CIN',
                'Cleveland Guardians': 'CLE',
                'Colorado Rockies': 'COL',
                'Detroit Tigers': 'DET',
                'Houston Astros': 'HOU',
                'Kansas City Royals': 'KC',
                'Los Angeles Angels': 'LAA',
                'Los Angeles Dodgers': 'LAD',
                'Miami Marlins': 'MIA',
                'Milwaukee Brewers': 'MIL',
                'Minnesota Twins': 'MIN',
                'New York Mets': 'NYM',
                'New York Yankees': 'NYY',
                'Oakland Athletics': 'OAK',
                'Philadelphia Phillies': 'PHI',
                'Pittsburgh Pirates': 'PIT',
                'San Diego Padres': 'SD',
                'San Francisco Giants': 'SF',
                'Seattle Mariners': 'SEA',
                'St. Louis Cardinals': 'STL',
                'Tampa Bay Rays': 'TB',
                'Texas Rangers': 'TEX',
                'Toronto Blue Jays': 'TOR',
                'Washington Nationals': 'WSH'
            }
            
            # Return abbreviation if found, otherwise return full team name
            return team_abbreviations.get(team_name, team_name)
                
        except Exception as e:
            print(f"[SPORTS] Error getting team abbreviation for {team_name}: {e}")
            return team_name

    def convert_to_central_time(self, time_str):
        """Convert ESPN time string to Central Time format"""
        try:
            # ESPN usually provides times in format like "7:00 PM ET" or "10/7 - 10:30 PM EDT"
            if ' - ' in time_str:
                # Format like "10/7 - 10:30 PM EDT"
                date_part, time_part = time_str.split(' - ', 1)
                time_to_convert = time_part
            else:
                # Format like "7:00 PM ET"
                time_to_convert = time_str
                date_part = ""
            
            # Parse different time zone abbreviations
            if any(tz in time_to_convert for tz in ['ET', 'EDT', 'EST']):
                # Eastern Time - subtract 1 hour for Central
                time_clean = time_to_convert
                for tz in [' ET', ' EDT', ' EST']:
                    time_clean = time_clean.replace(tz, '')
                
                # Parse time
                time_obj = datetime.strptime(time_clean.strip(), '%I:%M %p').time()
                # Convert to Central (ET - 1 hour)
                dt = datetime.combine(datetime.today(), time_obj)
                dt_central = dt - timedelta(hours=1)
                result = dt_central.strftime('%I:%M %p CT').lstrip('0')
                
            elif any(tz in time_to_convert for tz in ['PT', 'PDT', 'PST']):
                # Pacific Time - add 2 hours for Central
                time_clean = time_to_convert
                for tz in [' PT', ' PDT', ' PST']:
                    time_clean = time_clean.replace(tz, '')
                
                time_obj = datetime.strptime(time_clean.strip(), '%I:%M %p').time()
                # Convert to Central (PT + 2 hours)
                dt = datetime.combine(datetime.today(), time_obj)
                dt_central = dt + timedelta(hours=2)
                result = dt_central.strftime('%I:%M %p CT').lstrip('0')
                
            elif any(tz in time_to_convert for tz in ['MT', 'MDT', 'MST']):
                # Mountain Time - add 1 hour for Central
                time_clean = time_to_convert
                for tz in [' MT', ' MDT', ' MST']:
                    time_clean = time_clean.replace(tz, '')
                
                time_obj = datetime.strptime(time_clean.strip(), '%I:%M %p').time()
                # Convert to Central (MT + 1 hour)
                dt = datetime.combine(datetime.today(), time_obj)
                dt_central = dt + timedelta(hours=1)
                result = dt_central.strftime('%I:%M %p CT').lstrip('0')
                
            elif any(tz in time_to_convert for tz in ['CT', 'CDT', 'CST']):
                # Already Central Time
                result = time_to_convert.replace(' CDT', ' CT').replace(' CST', ' CT')
                
            else:
                # No timezone specified, assume it's already in desired format
                result = f"{time_to_convert.strip()} CT"
            
            # If we had a date part, add it back
            if date_part:
                return f"{date_part} - {result}"
            else:
                return result
                
        except Exception as e:
            print(f"[SPORTS] Error converting time '{time_str}': {e}")
            return f"{time_str} CT"  # Fallback

    def get_streaming_date(self):
        """Get the 'streaming date' - if it's before 6 AM, consider it the previous day"""
        try:
            now = datetime.now(self.central_tz)  # Use Central time for streaming date
            if now.hour < 6:  # Before 6 AM = still "yesterday" for streaming purposes
                streaming_date = now.date() - timedelta(days=1)
            else:
                streaming_date = now.date()
            return streaming_date
        except Exception as e:
            print(f"[SPORTS] Error getting streaming date: {e}")
            return datetime.now().date()

    def is_game_today(self, game_date_str):
        """Check if a game is on the current 'streaming day'"""
        try:
            # Parse the game date from ESPN API
            game_date = datetime.fromisoformat(game_date_str.replace('Z', '+00:00')).date()
            streaming_date = self.get_streaming_date()
            
            # Game is "today" if it's on the streaming date or the next calendar day
            # (to handle games that start late and go past midnight)
            return game_date in [streaming_date, streaming_date + timedelta(days=1)]
        except Exception as e:
            print(f"[SPORTS] Error parsing game date {game_date_str}: {e}")
            return True  # Default to showing the game if we can't parse the date

    def format_game_time(self, clock_seconds):
        """Convert clock seconds to MM:SS format for display"""
        if not clock_seconds or clock_seconds == 0:
            return "0:00"
        
        # Convert seconds to minutes:seconds
        minutes = int(clock_seconds // 60)
        seconds = int(clock_seconds % 60)
        return f"{minutes}:{seconds:02d}"

    def get_cache_status(self):
        """Get cache status for debugging"""
        now = time.time()
        status = {}
        for key, timestamp in self.last_update.items():
            age = int(now - timestamp)
            cached_count = len(self.cache.get(key, []))
            status[key] = {'age_seconds': age, 'message_count': cached_count}
        return status

    async def fetch_league_scores(self, league_name, api_url, sport_emoji, filter_today=False) -> List[str]:
        """Generic function to fetch scores from any ESPN league API"""
        
        cache_key = f"{league_name}_scores"
        
        # Check cache first - only fetch once every 5 minutes
        now = time.time()
        if (cache_key in self.cache and 
            cache_key in self.last_update and 
            now - self.last_update[cache_key] < self.cache_duration):
            print(f"[SPORTS] Using cached {league_name} data (age: {int(now - self.last_update[cache_key])}s)")
            return self.cache[cache_key]
        
        print(f"[SPORTS] Fetching {league_name} data...")
        messages = []
        try:
            timeout = aiohttp.ClientTimeout(total=15)  # Increased timeout
            async with aiohttp.ClientSession(timeout=timeout) as session:
                url = f"{api_url}/scoreboard"
                print(f"[SPORTS] Requesting {url}")
                
                async with session.get(url) as response:
                    print(f"[SPORTS] {league_name} API response status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        events = data.get('events', [])
                        print(f"[SPORTS] {league_name} found {len(events)} events")
                        
                        # Separate games by status for better display order
                        live_games = []
                        final_games = []
                        upcoming_games = []
                        filtered_out = 0
                        
                        for event in events:
                            # Filter for today's games if requested (NFL only)
                            if filter_today:
                                game_date = event.get('date', '')
                                if not self.is_game_today(game_date):
                                    filtered_out += 1
                                    continue
                            
                            competitions = event.get('competitions', [])
                            if competitions:
                                competition = competitions[0]
                                competitors = competition.get('competitors', [])
                                status = competition.get('status', {})
                                
                                if len(competitors) >= 2:
                                    home_team = competitors[0].get('team', {}).get('displayName', 'Unknown')
                                    away_team = competitors[1].get('team', {}).get('displayName', 'Unknown')
                                    home_score = competitors[0].get('score', '0')
                                    away_score = competitors[1].get('score', '0')
                                    
                                    # Get team abbreviations for all leagues
                                    home_display = self.get_team_abbreviation(league_name, home_team)
                                    away_display = self.get_team_abbreviation(league_name, away_team)
                                    
                                    # Get game status and timing info
                                    status_type = status.get('type', {}).get('description', 'Unknown')
                                    status_detail = status.get('type', {}).get('detail', '')
                                    status_short_detail = status.get('type', {}).get('shortDetail', '')
                                    clock = status.get('clock', 0)
                                    period = status.get('period', 0)
                                    
                                    # Handle different sports timing formats
                                    if status_type == "In Progress":
                                        if league_name == "NHL":
                                            # Hockey: Show period and time
                                            time_display = self.format_game_time(clock)
                                            period_display = f"P{period}" if period else "P1"
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} ({period_display} {time_display})"
                                        elif league_name == "NBA":
                                            # Basketball: Show quarter and time
                                            time_display = self.format_game_time(clock) if clock else status_detail
                                            quarter_display = f"Q{period}" if period else "Q1"
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} ({quarter_display} {time_display})"
                                        elif league_name == "NFL":
                                            # Football: Show quarter and time
                                            time_display = self.format_game_time(clock) if clock else status_detail
                                            if period == 5:
                                                quarter_display = "OT"
                                            else:
                                                quarter_display = f"Q{period}" if period else "Q1"
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} ({quarter_display} {time_display})"
                                        elif league_name == "MLB":
                                            # Baseball: Show inning
                                            inning_display = status_detail if status_detail else f"Inning {period}"
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} ({inning_display})"
                                        else:
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} (Live)"
                                        live_games.append(msg)
                                    elif status_type == "Final":
                                        # Show final score with just "F"
                                        msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} (F)"
                                        final_games.append(msg)
                                    elif status_type in ["Scheduled", "Pre-Game"]:
                                        # Show upcoming game with start time (converted to Central)
                                        start_time = status_short_detail if status_short_detail else status_detail
                                        if not start_time or start_time == status_type:
                                            start_time = "TBD"
                                        else:
                                            start_time = self.convert_to_central_time(start_time)
                                        msg = f"{sport_emoji} {away_display} @ {home_display} ({start_time})"
                                        upcoming_games.append(msg)
                                    elif status_type == "Halftime":
                                        # Special handling for halftime in football
                                        if league_name == "NFL":
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} (Halftime)"
                                            live_games.append(msg)
                                        else:
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} ({status_type})"
                                            live_games.append(msg)
                                    else:
                                        # Handle other statuses (Postponed, Delayed, etc.)
                                        if home_score != '0' or away_score != '0':
                                            msg = f"{sport_emoji} {away_display} {away_score} - {home_score} {home_display} ({status_type})"
                                        else:
                                            msg = f"{sport_emoji} {away_display} @ {home_display} ({status_type})"
                                        # Add to appropriate category based on status
                                        if "postponed" in status_type.lower() or "delayed" in status_type.lower():
                                            upcoming_games.append(msg)
                                        else:
                                            final_games.append(msg)
                        
                        # Show ALL games found (prioritize live first)
                        messages.extend(live_games)     # All live games
                        messages.extend(upcoming_games) # All upcoming games  
                        messages.extend(final_games)    # All final games
                        
                        filter_msg = f" (filtered out {filtered_out} non-today games)" if filter_today and filtered_out > 0 else ""
                        print(f"[SPORTS] {league_name}: {len(live_games)} live, {len(upcoming_games)} upcoming, {len(final_games)} final → showing ALL {len(messages)}{filter_msg}")
                        
                    else:
                        print(f"[SPORTS] {league_name} API returned status: {response.status}")
                        # Try to read response text for debugging
                        try:
                            error_text = await response.text()
                            print(f"[SPORTS] {league_name} error response: {error_text[:200]}")
                        except:
                            pass
                            
        except asyncio.TimeoutError:
            print(f"[SPORTS] {league_name} API timeout - using cached data if available")
            if cache_key in self.cache:
                return self.cache[cache_key]
            return []
        except aiohttp.ClientError as e:
            print(f"[SPORTS] {league_name} client error: {e}")
            if cache_key in self.cache:
                return self.cache[cache_key]
            return []
        except Exception as e:
            print(f"[SPORTS] {league_name} unexpected exception: {type(e).__name__}: {e}")
            if cache_key in self.cache:
                print(f"[SPORTS] Returning cached {league_name} data due to error")
                return self.cache[cache_key]
            return []
        
        # Cache the results for 5 minutes
        self.cache[cache_key] = messages
        self.last_update[cache_key] = now
        
        print(f"[SPORTS] Cached {len(messages)} {league_name} messages")
        return messages

    async def fetch_nhl_scores(self) -> List[str]:
        """Fetch NHL scores from ESPN API"""
        return await self.fetch_league_scores("NHL", self.espn_nhl_base, "🏒", filter_today=False)

    async def fetch_nba_scores(self) -> List[str]:
        """Fetch NBA scores from ESPN API"""
        return await self.fetch_league_scores("NBA", self.espn_nba_base, "🏀", filter_today=False)

    async def fetch_mlb_scores(self) -> List[str]:
        """Fetch MLB scores from ESPN API"""
        return await self.fetch_league_scores("MLB", self.espn_mlb_base, "⚾", filter_today=False)

    async def fetch_nfl_scores(self) -> List[str]:
        """Fetch NFL scores from ESPN API - ONLY TODAY'S GAMES"""
        return await self.fetch_league_scores("NFL", self.espn_nfl_base, "🏈", filter_today=True)

    async def get_sports_messages(self) -> List[str]:
        """Get sports messages for ticker from all leagues in order: NFL, NBA, NHL, MLB"""
        all_messages = []
        
        try:
            # Fetch from all leagues in desired order: NFL, NBA, NHL, MLB
            nfl_messages = await self.fetch_nfl_scores()      # Only today's games
            nba_messages = await self.fetch_nba_scores()      # All games
            nhl_messages = await self.fetch_nhl_scores()      # All games
            mlb_messages = await self.fetch_mlb_scores()      # All games
            
            # Add all messages in order - NO LIMITS (except NFL is pre-filtered)
            all_messages.extend(nfl_messages)  # NFL first (today only)
            all_messages.extend(nba_messages)  # NBA second (all games)
            all_messages.extend(nhl_messages)  # NHL third (all games)
            all_messages.extend(mlb_messages)  # MLB fourth (all games)
            
            streaming_date = self.get_streaming_date()
            print(f"[SPORTS] Streaming date: {streaming_date}")
            print(f"[SPORTS] Total messages: NFL({len(nfl_messages)}) + NBA({len(nba_messages)}) + NHL({len(nhl_messages)}) + MLB({len(mlb_messages)}) = {len(all_messages)} total")
            
        except Exception as e:
            print(f"[SPORTS] Error getting sports messages: {e}")
            return []
        
        return all_messages