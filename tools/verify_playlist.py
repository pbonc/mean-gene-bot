import asyncio
import json
import os
from typing import Dict, Optional

# Optional dependency for YouTube verification
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PLAYLIST_CACHE_FILE = os.path.join(DATA_DIR, "playlist_cache.json")

class PlaylistVerifier:
    """Utility to verify and update YouTube URLs in playlist"""
    
    def __init__(self):
        self.playlist_cache = self.load_playlist()
    
    def load_playlist(self):
        try:
            if os.path.exists(PLAYLIST_CACHE_FILE):
                with open(PLAYLIST_CACHE_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading playlist: {e}")
        return []
    
    def save_playlist(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(PLAYLIST_CACHE_FILE, 'w') as f:
                json.dump(self.playlist_cache, f, indent=2)
            print(f"✅ Saved playlist with {len(self.playlist_cache)} songs")
        except Exception as e:
            print(f"❌ Error saving playlist: {e}")
    
    async def verify_youtube_url(self, url: str) -> Optional[Dict]:
        """Verify YouTube URL and get metadata"""
        if not YT_DLP_AVAILABLE:
            print("⚠️ yt-dlp not available. Install with: pip install yt-dlp")
            return None
        
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'format': 'bestaudio/best',
                'noplaylist': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                return {
                    'title': info.get('title', 'Unknown Title'),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'view_count': info.get('view_count', 0),
                    'available': True
                }
        except Exception as e:
            print(f"❌ Error verifying {url}: {e}")
            return {'available': False, 'error': str(e)}
    
    async def verify_all_urls(self):
        """Verify all YouTube URLs in playlist"""
        print("🔍 Verifying all YouTube URLs in playlist...")
        
        updated_count = 0
        for song in self.playlist_cache:
            if song.get('youtube_url'):
                print(f"Checking #{song['number']}: {song['title']}...")
                
                result = await self.verify_youtube_url(song['youtube_url'])
                if result:
                    if result.get('available', False):
                        song['duration'] = result['duration']
                        song['verified'] = True
                        updated_count += 1
                        
                        mins = result['duration'] // 60
                        secs = result['duration'] % 60
                        print(f"  ✅ Verified: {result['title']} ({mins}:{secs:02d})")
                    else:
                        song['verified'] = False
                        print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
                
                # Small delay to be nice to YouTube
                await asyncio.sleep(0.5)
        
        print(f"\n📊 Verification complete: {updated_count} URLs verified")
        self.save_playlist()
    
    def show_playlist_stats(self):
        """Show playlist statistics"""
        total_songs = len(self.playlist_cache)
        youtube_songs = len([s for s in self.playlist_cache if s.get('youtube_url')])
        verified_songs = len([s for s in self.playlist_cache if s.get('verified')])
        
        total_duration = sum(s.get('duration', 0) for s in self.playlist_cache if s.get('duration'))
        total_mins = total_duration // 60
        total_hours = total_mins // 60
        remaining_mins = total_mins % 60
        
        print(f"\n📊 Playlist Statistics:")
        print(f"   Total songs: {total_songs}")
        print(f"   With YouTube URLs: {youtube_songs}")
        print(f"   Verified URLs: {verified_songs}")
        print(f"   Total duration: {total_hours}h {remaining_mins}m")
        
        print(f"\n🎵 Song List:")
        for song in sorted(self.playlist_cache, key=lambda x: x['number']):
            youtube_status = ""
            if song.get('youtube_url'):
                if song.get('verified'):
                    youtube_status = "🎬✅"
                else:
                    youtube_status = "🎬❓"
            else:
                youtube_status = "🎵"
            
            duration_str = ""
            if song.get('duration'):
                mins = song['duration'] // 60
                secs = song['duration'] % 60
                duration_str = f" ({mins}:{secs:02d})"
            
            print(f"   #{song['number']:2d}: {song['title']} - {song['artist']}{duration_str} {youtube_status}")

async def main():
    verifier = PlaylistVerifier()
    
    print("🎵 Playlist YouTube Stinger Verifier")
    print("=" * 50)
    
    # Show current stats
    verifier.show_playlist_stats()
    
    if YT_DLP_AVAILABLE:
        print("\n" + "=" * 50)
        response = input("Verify all YouTube URLs? (y/N): ").lower().strip()
        if response == 'y':
            await verifier.verify_all_urls()
            print("\n" + "=" * 50)
            verifier.show_playlist_stats()
    else:
        print("\n⚠️ To verify YouTube URLs, install yt-dlp:")
        print("   pip install yt-dlp")

if __name__ == "__main__":
    asyncio.run(main())