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
        
        # API endpoints - switch to ESPN for current data
        self.espn_nhl_base = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
        self.sportsdb_base = "https://www.thesportsdb.com/api/v1/json/3"

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
            timeout = aiohttp.ClientTimeout(total=10)
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
                        
                        for event in events:
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
                                    
                                    # Get game status and timing info
                                    status_type = status.get('type', {}).get('description', 'Unknown')
                                    status_detail = status.get('type', {}).get('detail', '')
                                    status_short_detail = status.get('type', {}).get('shortDetail', '')
                                    clock = status.get('clock', 0)
                                    period = status.get('period', 0)
                                    
                                    # Categorize games by status
                                    if status_type == "In Progress":
                                        # Show live game with period and time
                                        time_display = self.format_game_time(clock)
                                        period_display = f"P{period}" if period else "P1"
                                        msg = f"🏒 {away_team} {away_score} - {home_score} {home_team} ({period_display} {time_display})"
                                        live_games.append(msg)
                                    elif status_type == "Final":
                                        # Show final score with just "F"
                                        msg = f"🏒 {away_team} {away_score} - {home_score} {home_team} (F)"
                                        final_games.append(msg)
                                    elif status_type in ["Scheduled", "Pre-Game"]:
                                        # Show upcoming game with start time
                                        start_time = status_short_detail if status_short_detail else status_detail
                                        if not start_time or start_time == status_type:
                                            start_time = "TBD"
                                        msg = f"🏒 {away_team} @ {home_team} ({start_time})"
                                        upcoming_games.append(msg)
                                    else:
                                        # Handle other statuses (Postponed, Delayed, etc.)
                                        if home_score != '0' or away_score != '0':
                                            msg = f"🏒 {away_team} {away_score} - {home_score} {home_team} ({status_type})"
                                        else:
                                            msg = f"🏒 {away_team} @ {home_team} ({status_type})"
                                        # Add to appropriate category based on status
                                        if "postponed" in status_type.lower() or "delayed" in status_type.lower():
                                            upcoming_games.append(msg)
                                        else:
                                            final_games.append(msg)
                        
                        # Show ALL games found (prioritize live first)
                        messages.extend(live_games)     # All live games
                        messages.extend(upcoming_games) # All upcoming games  
                        messages.extend(final_games)    # All final games
                        
                        print(f"[SPORTS] Found {len(live_games)} live, {len(upcoming_games)} upcoming, {len(final_games)} final games")
                        
                    else:
                        print(f"[SPORTS] ESPN API returned status: {response.status}")
        except Exception as e:
            print(f"[SPORTS] Exception: {e}")
            return []
        
        # Cache the results for 5 minutes
        self.cache['nhl_scores'] = messages
        self.last_update['nhl_scores'] = now
        
        print(f"[SPORTS] Cached {len(messages)} NHL messages")
        return messages

    async def get_sports_messages(self) -> List[str]:
        """Get sports messages for ticker"""
        all_messages = []
        nhl_messages = await self.fetch_nhl_scores()
        all_messages.extend(nhl_messages)
        return all_messages  # Return all messages, let ticker decide how many to show
