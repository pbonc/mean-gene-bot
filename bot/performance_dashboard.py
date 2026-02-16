"""
Stream Performance Dashboard Generator
Analyzes available data sources to create actionable insights for stream growth
"""
import os
import json
import asyncio
from datetime import datetime, timedelta
from bot.streamlabs_api import get_recent_events
from bot.twitch_stats import get_stream_info
from bot.stream_analytics import StreamAnalytics, PerformanceAnalyzer, MILESTONE_VALUES

class StreamDashboard:
    def __init__(self):
        self.analytics = StreamAnalytics()
        self.analyzer = PerformanceAnalyzer(self.analytics)
    
    async def generate_performance_report(self) -> str:
        """Generate a comprehensive performance report"""
        print("🔍 Analyzing Stream Performance...")
        
        # Get current stream data
        stream_info = await get_stream_info()
        recent_events = await get_recent_events()
        daily_data = self.analytics.load_daily_milestones()
        
        report = []
        report.append("=" * 60)
        report.append("📊 STREAM PERFORMANCE ANALYSIS REPORT")
        report.append("=" * 60)
        
        # Current Stream Status
        report.append("\n🎮 CURRENT STREAM STATUS")
        if stream_info:
            report.append(f"  Viewers: {stream_info.get('viewers', 'N/A')}")
            report.append(f"  Title: {stream_info.get('title', 'N/A')}")
            report.append(f"  Game: {stream_info.get('game', 'N/A')}")
            report.append(f"  Uptime: {stream_info.get('uptime', 'N/A')}")
        else:
            report.append("  ⚠️  Stream appears to be offline")
        
        # Today's Milestones
        report.append(f"\n🏆 TODAY'S MILESTONES ({daily_data.get('date', 'N/A')})")
        milestones = daily_data.get('milestones', {})
        
        # Check what milestones have been achieved
        achieved = []
        pending = []
        
        if milestones.get('first_follower'):
            achieved.append(f"✅ First Follower: {milestones['first_follower']} (+${MILESTONE_VALUES['first_follower']:.2f})")
        else:
            pending.append(f"⏳ First Follower (+${MILESTONE_VALUES['first_follower']:.2f})")
            
        if milestones.get('first_subscriber'):
            achieved.append(f"✅ First New Sub: {milestones['first_subscriber']} (+${MILESTONE_VALUES['first_subscriber']:.2f})")
        else:
            pending.append(f"⏳ First New Sub (+${MILESTONE_VALUES['first_subscriber']:.2f})")
            
        if milestones.get('first_resub'):
            achieved.append(f"✅ First Resub: {milestones['first_resub']} (+${MILESTONE_VALUES['first_resub']:.2f})")
        else:
            pending.append(f"⏳ First Resub (+${MILESTONE_VALUES['first_resub']:.2f})")
            
        if milestones.get('first_donation'):
            achieved.append(f"✅ First Donation: {milestones['first_donation']} (+${MILESTONE_VALUES['first_donation']:.2f})")
        else:
            pending.append(f"⏳ First Donation (+${MILESTONE_VALUES['first_donation']:.2f})")
        
        # Viewer milestones
        viewer_milestones_hit = milestones.get('viewer_milestones', [])
        for threshold in [50, 100, 200, 300]:
            if threshold in viewer_milestones_hit:
                achieved.append(f"✅ {threshold} Viewers (+${MILESTONE_VALUES.get(f'{threshold}_viewers', 0):.2f})")
            else:
                pending.append(f"⏳ {threshold} Viewers (+${MILESTONE_VALUES.get(f'{threshold}_viewers', 0):.2f})")
        
        report.append("\n  📈 ACHIEVED TODAY:")
        if achieved:
            for item in achieved:
                report.append(f"    {item}")
        else:
            report.append("    None yet - opportunity awaits!")
        
        report.append("\n  🎯 PENDING OPPORTUNITIES:")
        for item in pending[:6]:  # Show top 6 pending
            report.append(f"    {item}")
        
        # Calculate potential giveaway amount
        total_achieved = sum(MILESTONE_VALUES.get(m.split('(')[0].replace('✅ ', '').replace('First ', 'first_').replace('New ', '').replace(' Viewers', '_viewers').lower().replace(' ', '_'), 0) for m in achieved)
        easy_pending = sum(MILESTONE_VALUES[k] for k in ['first_follower', 'first_subscriber', 'first_donation'] if not milestones.get(k))
        
        report.append(f"\n💰 GIVEAWAY ANALYSIS:")
        report.append(f"  Current earned today: ${total_achieved:.2f}")
        report.append(f"  Easy additions available: ${easy_pending:.2f}")
        report.append(f"  Realistic target: ${total_achieved + easy_pending:.2f}")
        
        # Recent Activity Analysis
        report.append(f"\n📊 RECENT ACTIVITY (Last 50 events)")
        if recent_events:
            event_summary = {}
            for event in recent_events[-50:]:  # Last 50 events
                event_type = event.get('type', 'unknown')
                event_summary[event_type] = event_summary.get(event_type, 0) + 1
            
            for event_type, count in event_summary.items():
                report.append(f"  {event_type.title()}: {count}")
        else:
            report.append("  No recent events found")
        
        # Growth Strategy Recommendations
        report.append(f"\n🚀 GROWTH STRATEGY RECOMMENDATIONS:")
        
        current_viewers = stream_info.get('viewers', 0) if stream_info else 0
        
        if current_viewers < 25:
            report.append("  🎯 Focus on Networking:")
            report.append("    - Raid other streamers in your category")
            report.append("    - Engage in other chats when offline")
            report.append("    - Collaborate with similar-sized streamers")
            
        elif current_viewers < 50:
            report.append("  🎯 Focus on Retention:")
            report.append("    - Implement regular interactive segments")
            report.append("    - Create viewer challenges/games")
            report.append("    - Consistent schedule is key")
            
        else:
            report.append("  🎯 Focus on Community:")
            report.append("    - Discord community building")
            report.append("    - Social media presence")
            report.append("    - Subscriber perks and events")
        
        # Optimal Giveaway Targets
        suggestions = self.analyzer.suggest_giveaway_targets()
        report.append(f"\n💡 GIVEAWAY TARGET SUGGESTIONS:")
        report.append(f"  Conservative (Most days): ${suggestions['conservative_target']:.2f}")
        report.append(f"  Ambitious (Good days): ${suggestions['ambitious_target']:.2f}")
        report.append(f"  Stretch (Great days): ${suggestions['stretch_target']:.2f}")
        
        # Data Sources Available
        report.append(f"\n📚 AVAILABLE DATA SOURCES:")
        report.append("  ✅ Twitch API (viewers, uptime, followers)")
        report.append("  ✅ StreamLabs API (subs, donations, bits)")
        report.append("  ✅ Raffle system (engagement tracking)")
        report.append("  ⚠️  Consider adding: TwitchTracker, StreamElements")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    async def export_data_for_analysis(self) -> str:
        """Export data in formats suitable for external analysis tools"""
        print("📤 Exporting data for external analysis...")
        
        # Create exports directory
        export_dir = os.path.join(self.analytics.data_dir, "exports")
        os.makedirs(export_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export recent StreamLabs data
        try:
            events = await get_recent_events()
            export_file = os.path.join(export_dir, f"streamlabs_events_{timestamp}.json")
            with open(export_file, 'w') as f:
                json.dump(events, f, indent=2)
            print(f"📊 Exported StreamLabs events to: {export_file}")
        except Exception as e:
            print(f"❌ StreamLabs export failed: {e}")
        
        # Export current analytics
        analytics_data = self.analytics.load_analytics_data()
        daily_data = self.analytics.load_daily_milestones()
        
        combined_export = {
            "export_timestamp": timestamp,
            "analytics": analytics_data,
            "daily_milestones": daily_data,
            "milestone_values": MILESTONE_VALUES
        }
        
        export_file = os.path.join(export_dir, f"stream_analytics_{timestamp}.json")
        with open(export_file, 'w') as f:
            json.dump(combined_export, f, indent=2)
        
        return export_dir

# CLI Interface for analysis
async def main():
    """Run the stream performance analysis"""
    dashboard = StreamDashboard()
    
    print("🤖 Mean Gene Bot - Stream Performance Analyzer")
    print("=" * 50)
    
    # Generate and display report
    report = await dashboard.generate_performance_report()
    print(report)
    
    # Ask if user wants to export data
    export = input("\n📤 Export data for external analysis? (y/n): ").lower()
    if export in ['y', 'yes']:
        export_dir = await dashboard.export_data_for_analysis()
        print(f"\n✅ Data exported to: {export_dir}")
        print("\n💡 You can now:")
        print("   - Import JSON files into Excel/Google Sheets")
        print("   - Use data with Grafana/PowerBI")
        print("   - Analyze trends with Python/R")

if __name__ == "__main__":
    asyncio.run(main())