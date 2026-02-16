"""
Stream Performance Analytics & Dynamic Giveaway System
Tracks daily milestones and adjusts giveaway amounts based on engagement
"""
import os
import json
import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional
from bot.streamlabs_api import get_recent_events
from bot.twitch_stats import get_stream_info, get_recent_follower, get_recent_subscriber

class StreamAnalytics:
    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.analytics_file = os.path.join(self.data_dir, "stream_analytics.json")
        self.daily_file = os.path.join(self.data_dir, "daily_milestones.json")
        os.makedirs(self.data_dir, exist_ok=True)
        
    def load_analytics_data(self) -> dict:
        """Load historical analytics data"""
        if os.path.exists(self.analytics_file):
            with open(self.analytics_file, 'r') as f:
                return json.load(f)
        return {"streams": {}, "totals": {}}
    
    def save_analytics_data(self, data: dict):
        """Save analytics data"""
        with open(self.analytics_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load_daily_milestones(self) -> dict:
        """Load today's milestone tracking"""
        today = date.today().isoformat()
        if os.path.exists(self.daily_file):
            with open(self.daily_file, 'r') as f:
                data = json.load(f)
                if data.get("date") == today:
                    return data
        
        # Reset for new day
        return {
            "date": today,
            "milestones": {
                "first_follower": None,
                "first_subscriber": None,
                "first_resub": None,
                "first_gifted_sub": None,
                "first_donation": None,
                "first_bits": None,
                "viewer_milestones": [],  # 50, 100, 200, etc.
                "follower_milestones": []  # every 10, 25, 50, 100
            },
            "giveaway_boosts": []
        }
    
    def save_daily_milestones(self, data: dict):
        """Save today's milestone data"""
        with open(self.daily_file, 'w') as f:
            json.dump(data, f, indent=2)

# Dynamic Giveaway Amount System
MILESTONE_VALUES = {
    # Daily Firsts (reset each stream day)
    "first_follower": 1.00,
    "first_subscriber": 1.00,
    "first_resub": 1.00,
    "first_gifted_sub": 1.00,
    "first_donation": 1.00,
    "first_bits": 1.00,
    
    # Viewer Milestones
    "50_viewers": 1.00,
    "100_viewers": 1.00,
    "200_viewers": 1.00,
    "300_viewers": 1.00,
    
    # Follower Growth Milestones (during stream)
    "10_new_followers": 1.00,
    "25_new_followers": 1.00,
    "50_new_followers": 1.00,
    "100_new_followers": 1.00,
    
    # Engagement Milestones
    "5_subs_in_hour": 1.00,
    "10_gifted_in_hour": 1.00,
    "raid_incoming_50plus": 1.00,
    "raid_incoming_100plus": 1.00,
    
    # Special Events
    "weekend_bonus": 1.00,
    "holiday_bonus": 1.00,
    "stream_anniversary": 1.00
}

class DynamicGiveaway:
    def __init__(self, analytics: StreamAnalytics):
        self.analytics = analytics
        
    async def check_and_update_giveaway(self) -> dict:
        """Check for new milestones and update giveaway amount"""
        daily_data = self.analytics.load_daily_milestones()
        current_amount = self.get_current_giveaway_amount()
        boosts_added = []
        
        # Check Twitch API for current stats
        stream_info = await get_stream_info()
        recent_events = await get_recent_events()
        
        # Process potential milestones
        if stream_info:
            boosts_added.extend(await self._check_viewer_milestones(
                stream_info.get('viewers', 0), daily_data
            ))
        
        boosts_added.extend(await self._check_engagement_milestones(
            recent_events, daily_data
        ))
        
        # Apply boosts to giveaway
        total_boost = sum(boost['amount'] for boost in boosts_added)
        if total_boost > 0:
            new_amount = current_amount + total_boost
            await self._update_giveaway_amount(new_amount)
            
            # Log the boosts
            daily_data['giveaway_boosts'].extend(boosts_added)
            self.analytics.save_daily_milestones(daily_data)
        
        return {
            "previous_amount": current_amount,
            "new_amount": current_amount + total_boost,
            "boosts_added": boosts_added,
            "total_boost": total_boost
        }
    
    async def _check_viewer_milestones(self, current_viewers: int, daily_data: dict) -> list:
        """Check if we hit viewer count milestones"""
        boosts = []
        milestones_hit = daily_data['milestones']['viewer_milestones']
        
        for threshold in [50, 100, 200, 300]:
            if current_viewers >= threshold and threshold not in milestones_hit:
                boosts.append({
                    "type": "viewer_milestone",
                    "milestone": f"{threshold}_viewers",
                    "amount": MILESTONE_VALUES.get(f"{threshold}_viewers", 0),
                    "timestamp": datetime.now().isoformat(),
                    "description": f"Hit {threshold} concurrent viewers!"
                })
                milestones_hit.append(threshold)
        
        return boosts
    
    async def _check_engagement_milestones(self, recent_events: list, daily_data: dict) -> list:
        """Check Streamlabs events for daily firsts and engagement"""
        boosts = []
        milestones = daily_data['milestones']
        
        # Process recent events for daily firsts
        for event in recent_events:
            event_type = event.get('type')
            
            # First follower of the day
            if event_type == 'follow' and not milestones['first_follower']:
                boosts.append({
                    "type": "daily_first",
                    "milestone": "first_follower",
                    "amount": MILESTONE_VALUES['first_follower'],
                    "timestamp": datetime.now().isoformat(),
                    "description": f"First follower: {event.get('name', 'Unknown')}!",
                    "user": event.get('name')
                })
                milestones['first_follower'] = event.get('name')
            
            # First subscription of the day
            elif event_type == 'subscription' and not milestones['first_subscriber']:
                is_resub = event.get('months', 0) > 1
                milestone_key = 'first_resub' if is_resub else 'first_subscriber'
                
                if not milestones[milestone_key]:
                    boosts.append({
                        "type": "daily_first",
                        "milestone": milestone_key,
                        "amount": MILESTONE_VALUES[milestone_key],
                        "timestamp": datetime.now().isoformat(),
                        "description": f"First {'resub' if is_resub else 'new sub'}: {event.get('name', 'Unknown')}!",
                        "user": event.get('name')
                    })
                    milestones[milestone_key] = event.get('name')
            
            # First donation of the day
            elif event_type == 'donation' and not milestones['first_donation']:
                boosts.append({
                    "type": "daily_first",
                    "milestone": "first_donation",
                    "amount": MILESTONE_VALUES['first_donation'],
                    "timestamp": datetime.now().isoformat(),
                    "description": f"First donation: ${event.get('amount', 0)} from {event.get('name', 'Unknown')}!",
                    "user": event.get('name'),
                    "donation_amount": event.get('amount')
                })
                milestones['first_donation'] = event.get('name')
            
            # First bits cheer of the day (100+ bits required)
            elif event_type == 'bits' and not milestones['first_bits']:
                bits_amount = event.get('amount', 0)
                if bits_amount >= 100:
                    boosts.append({
                        "type": "daily_first",
                        "milestone": "first_bits",
                        "amount": MILESTONE_VALUES['first_bits'],
                        "timestamp": datetime.now().isoformat(),
                        "description": f"First 100+ bits cheer: {bits_amount} bits from {event.get('name', 'Unknown')}!",
                        "user": event.get('name'),
                        "bits_amount": bits_amount
                    })
                    milestones['first_bits'] = event.get('name')
        
        return boosts
    
    def get_current_giveaway_amount(self) -> float:
        """Get current giveaway amount from raffle state"""
        try:
            from bot.commands.raffle_cog import SimpleRaffleState
            raffle_file = os.path.join(self.analytics.data_dir, "raffle_state.json")
            if os.path.exists(raffle_file):
                state = SimpleRaffleState(raffle_file)
                return state.get_giveaway_amount()
        except Exception:
            pass
        return 0.0
    
    async def _update_giveaway_amount(self, new_amount: float):
        """Update the raffle giveaway amount"""
        try:
            from bot.commands.raffle_cog import SimpleRaffleState
            raffle_file = os.path.join(self.analytics.data_dir, "raffle_state.json")
            if os.path.exists(raffle_file):
                state = SimpleRaffleState(raffle_file)
                state.set_giveaway_amount(new_amount)
        except Exception as e:
            print(f"Error updating giveaway amount: {e}")

# Historical Performance Analysis
class PerformanceAnalyzer:
    def __init__(self, analytics: StreamAnalytics):
        self.analytics = analytics
    
    def analyze_growth_trends(self) -> dict:
        """Analyze historical growth patterns"""
        data = self.analytics.load_analytics_data()
        
        # Calculate averages, trends, best performing days
        analysis = {
            "average_viewers": 0,
            "peak_viewers": 0,
            "growth_rate": 0,
            "best_day_of_week": None,
            "engagement_trends": {},
            "milestone_frequency": {}
        }
        
        # Process historical data
        streams = data.get("streams", {})
        if streams:
            viewer_counts = [s.get("peak_viewers", 0) for s in streams.values()]
            analysis["average_viewers"] = sum(viewer_counts) / len(viewer_counts)
            analysis["peak_viewers"] = max(viewer_counts)
        
        return analysis
    
    def suggest_giveaway_targets(self) -> dict:
        """Suggest realistic giveaway amount targets based on historical data"""
        analysis = self.analyze_growth_trends()
        
        suggestions = {
            "conservative_target": 50.00,  # Achievable most streams
            "ambitious_target": 100.00,    # Good engagement day
            "stretch_target": 200.00,      # Exceptional day
            "reasoning": {
                "conservative": "Based on typical daily firsts (follower + sub + donation)",
                "ambitious": "Adding viewer milestones and engagement bonuses",
                "stretch": "Multiple viewer milestones + high engagement"
            }
        }
        
        return suggestions

# Usage Example & Integration
async def initialize_stream_analytics():
    """Initialize the analytics system for the current stream"""
    analytics = StreamAnalytics()
    giveaway = DynamicGiveaway(analytics)
    analyzer = PerformanceAnalyzer(analytics)
    
    return analytics, giveaway, analyzer

# Chat command integration
async def handle_giveaway_boost_notification(ctx, boost_info):
    """Notify chat when giveaway amount increases"""
    if boost_info['total_boost'] > 0:
        message = f"🎉 Giveaway increased by ${boost_info['total_boost']:.2f}! "
        message += f"New total: ${boost_info['new_amount']:.2f} "
        
        reasons = [boost['description'] for boost in boost_info['boosts_added']]
        if reasons:
            message += f"Reason: {', '.join(reasons[:2])}"  # Show first 2 reasons
        
        await ctx.send(message)