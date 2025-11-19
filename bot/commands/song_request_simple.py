import os
import json
import logging
import asyncio
from twitchio.ext import commands
from typing import Dict, List, Optional
from datetime import datetime

# Import the new music sheets manager
try:
    from bot.music_sheets_sync import music_sheets_manager
    SHEETS_SYNC_AVAILABLE = True
except ImportError:
    music_sheets_manager = None
    SHEETS_SYNC_AVAILABLE = False

# Import global music state manager to prevent overlapping playback
try:
    from bot.music_state import music_state_manager
    MUSIC_STATE_AVAILABLE = True
except ImportError:
    music_state_manager = None
    MUSIC_STATE_AVAILABLE = False

# Optional audio dependencies - wrapped in try/except to prevent import errors
PYGAME_AVAILABLE = False
YT_DLP_AVAILABLE = False

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pass

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
    print("SUCCESS: yt-dlp imported successfully in song_request_simple.py")
except ImportError as e:
    print(f"❌ yt-dlp import failed in song_request_simple.py: {e}")
    pass

# Project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
QUARTERS_FILE = os.path.join(DATA_DIR, "user_quarters.json") 
PLAYLIST_CACHE_FILE = os.path.join(DATA_DIR, "playlist_cache.json")
MUSIC_CACHE_DIR = os.path.join(DATA_DIR, "music_cache")

class SimpleSongManager:
    """Song manager with playback controls and volume normalization"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.user_quarters = self.load_quarters()
        self.playlist_cache = self.load_playlist_cache()
        self.current_queue = []  # [(song_info, username, timestamp)]
        self.quarters_per_youtube_request = 1
        self.max_queue_length = 50
        
        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.current_song = None
        self.current_song_info = None
        self.music_enabled = False
        
        # Synchronization for preventing race conditions between manual commands and auto-play
        self.playback_lock = asyncio.Lock()
        
        # Process tracking for brutal termination
        self.audio_processes = []  # Track spawned audio processes
        self.song_start_time = None
        self.song_duration = None
        
        # Cache operation tracking
        self.is_caching = False  # Flag to prevent conflicts during cache operations
        
        # Volume settings
        self.master_volume = 0.3  # 30% default volume (lowered to balance with SFX)
        
        # Hot queue file tracking for cleanup
        self.current_hot_queue_file = None
        self.normalize_volume = True
        self.target_db = -20  # Target loudness in dB
        
        # Audio synchronization - use asyncio.Lock for async compatibility
        self._audio_lock = asyncio.Lock()
        
        # Song cooldown system (20 minutes)
        self.song_cooldowns = {}  # {song_number: last_played_timestamp}
        self.cooldown_minutes = 20
        
        # Smart pre-caching system
        self.pre_cache_tasks = {}  # {song_identifier: asyncio.Task}
        self.next_random_cached = None  # Pre-cached random song for smooth transitions
        
        # Threading for blocking operations (JSON I/O, yt-dlp, file operations)
        from concurrent.futures import ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="MGB-Worker")
        
        # Audio setup - try multiple audio backends
        self.audio_ready = False
        self.audio_backend = None
        
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
                pygame.mixer.init()
                self.audio_ready = True
                self.audio_backend = "pygame"
                self.logger.info("🎵 Audio system initialized with pygame")
            except Exception as e:
                self.logger.error(f"Pygame audio initialization failed: {e}")
        
        # Fallback to playsound3 if pygame not available
        if not self.audio_ready:
            try:
                import playsound3
                self.audio_ready = True
                self.audio_backend = "playsound3"
                self.logger.info("🎵 Audio system initialized with playsound3")
            except ImportError:
                self.logger.info("🎵 Music system in queue-only mode (no audio libraries available)")
        
        # Ensure cache directory exists
        os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
        
        # Log initial cache status
        self._log_cache_status()
    
    def _log_cache_status(self):
        """Log current cache status on startup"""
        try:
            cache_status = self.get_cache_status()
            completion_percent = round((cache_status['cached_songs'] / cache_status['total_playlist_songs']) * 100, 1) if cache_status['total_playlist_songs'] > 0 else 0
            
            self.logger.info(f"🎵 Music Cache Status: {cache_status['cached_songs']}/{cache_status['total_playlist_songs']} songs ({completion_percent}%) - {cache_status['cache_size_mb']} MB")
            
            if cache_status['missing_songs']:
                self.logger.info(f"📥 {len(cache_status['missing_songs'])} songs not cached - use !cachemissing or !cacheall to download")
            
        except Exception as e:
            self.logger.error(f"Error checking cache status: {e}")

    def _sync_queue_to_sheets(self):
        """Sync current queue to Google Sheets (if configured)"""
        if not SHEETS_SYNC_AVAILABLE or not music_sheets_manager:
            return
            
        # Convert internal queue format to sheets format
        queue_data = []
        for i, (song_info, username, timestamp) in enumerate(self.current_queue, 1):
            # Determine request type and catalog number
            catalog_number = ""
            request_type = "youtube"
            
            # Check if this is a playlist song
            if 'number' in song_info:
                catalog_number = song_info['number']
                request_type = "playlist"
            
            # Format duration
            duration = ""
            if 'duration' in song_info:
                if isinstance(song_info['duration'], (int, float)):
                    minutes = int(song_info['duration']) // 60
                    seconds = int(song_info['duration']) % 60
                    duration = f"{minutes}:{seconds:02d}"
                else:
                    duration = str(song_info['duration'])
            
            queue_item = {
                'position': i,
                'title': song_info.get('title', 'Unknown'),
                'artist': song_info.get('artist', 'Unknown'),
                'duration': duration,
                'requester': username,
                'catalog_number': catalog_number,
                'request_type': request_type,
                'youtube_url': song_info.get('youtube_url', '')
            }
            queue_data.append(queue_item)
        
        # Update sheets
        try:
            music_sheets_manager.update_queue(queue_data)
        except Exception as e:
            self.logger.error(f"Failed to sync queue to sheets: {e}")

    def cleanup_audio_processes(self):
        """Forcefully terminate any running audio processes"""
        try:
            if hasattr(self, 'current_process') and self.current_process:
                try:
                    self.current_process.terminate()
                    print("🔥 Terminated audio subprocess during cleanup")
                except:
                    try:
                        self.current_process.kill()
                        print("🔥 Killed audio subprocess during cleanup")
                    except:
                        pass
                self.current_process = None
            
            # Also try to kill any python processes running playsound3
            import subprocess
            try:
                # On Windows, kill any python processes that might be playing audio
                subprocess.run(['taskkill', '/F', '/IM', 'python.exe'], 
                             capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                print("🔥 Killed any remaining python audio processes")
            except:
                pass
            
            self.is_playing = False
            self.current_song = None
            print("🔥 Audio cleanup completed")
            
        except Exception as e:
            print(f"Error during audio cleanup: {e}")

    def _get_friendly_song_info(self, filename: str) -> Dict[str, str]:
        """Convert a cached filename into friendly display information"""
        import re
        
        # Remove file extension
        clean_name = re.sub(r'\.(webm|mp4|m4a|opus|ogg|mp3)$', '', filename, flags=re.IGNORECASE)
        
        # Replace underscores with spaces
        clean_name = clean_name.replace('_', ' ')
        
        # Try to match with playlist cache to get proper artist/title
        for song in self.playlist_cache:
            song_title = song.get('title', '').lower()
            song_artist = song.get('artist', '').lower()
            
            # Check if the cleaned filename contains the song title
            if song_title and song_title in clean_name.lower():
                return {
                    'title': song['title'],
                    'artist': song['artist']
                }
            
            # Also check if it matches "Artist - Title" pattern
            combined = f"{song_artist} - {song_title}".lower()
            if combined in clean_name.lower() or clean_name.lower() in combined:
                return {
                    'title': song['title'], 
                    'artist': song['artist']
                }
        
        # If no match found, try to parse "Artist - Title" from filename
        if ' - ' in clean_name:
            parts = clean_name.split(' - ', 1)
            if len(parts) == 2:
                return {
                    'title': parts[1].strip().title(),
                    'artist': parts[0].strip().title()
                }
        
        # Fallback: just clean up the filename
        return {
            'title': clean_name.title(),
            'artist': "Unknown Artist"
        }

    def load_quarters(self) -> Dict[str, int]:
        try:
            if os.path.exists(QUARTERS_FILE):
                with open(QUARTERS_FILE, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading quarters: {e}")
        return {}

    def save_quarters(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(QUARTERS_FILE, 'w') as f:
                json.dump(self.user_quarters, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving quarters: {e}")
    
    async def save_quarters_async(self):
        """Save user quarters to file asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._save_quarters_sync)
        except Exception as e:
            self.logger.error(f"Failed to save quarters async: {e}")
    
    def _save_quarters_sync(self):
        """Synchronous quarters saving for executor"""
        import json
        import os
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(QUARTERS_FILE, 'w') as f:
                json.dump(self.user_quarters, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving quarters sync: {e}")

    def load_playlist_cache(self) -> List[Dict]:
        try:
            if os.path.exists(PLAYLIST_CACHE_FILE):
                with open(PLAYLIST_CACHE_FILE, 'r', encoding='utf-8') as f:
                    playlist = json.load(f)
                    self.logger.info(f"Loaded {len(playlist)} songs from playlist cache")
                    return playlist
            else:
                self.logger.error(f"Playlist cache file not found: {PLAYLIST_CACHE_FILE}")
        except Exception as e:
            self.logger.error(f"Error loading playlist cache: {e}")
        return []

    def get_user_quarters(self, username: str) -> int:
        return self.user_quarters.get(username.lower(), 0)

    def spend_quarters(self, username: str, amount: int) -> bool:
        username = username.lower()
        current = self.user_quarters.get(username, 0)
        if current >= amount:
            self.user_quarters[username] = current - amount
            # Use async saving to prevent blocking
            asyncio.create_task(self.save_quarters_async())
            return True
        return False

    def give_quarters(self, username: str, amount: int):
        username = username.lower()
        self.user_quarters[username] = self.user_quarters.get(username, 0) + amount
        # Use async saving to prevent blocking
        asyncio.create_task(self.save_quarters_async())

    def find_playlist_song(self, number: int) -> Optional[Dict]:
        for song in self.playlist_cache:
            if song['number'] == number:
                return song
        return None

    def is_youtube_url(self, text: str) -> bool:
        return 'youtube.com' in text or 'youtu.be' in text

    def is_song_in_queue(self, song_to_check: Dict) -> Optional[Dict]:
        """Check if a song is already in the queue. Returns the matching queue entry if found."""
        for song_info, username, timestamp in self.current_queue:
            # For playlist songs, compare by song number
            if song_to_check.get('number') and song_info.get('number'):
                if song_to_check['number'] == song_info['number']:
                    return {'song': song_info, 'username': username, 'timestamp': timestamp}
            
            # For YouTube songs, compare by URL
            elif song_to_check.get('youtube_url') and song_info.get('youtube_url'):
                if song_to_check['youtube_url'] == song_info['youtube_url']:
                    return {'song': song_info, 'username': username, 'timestamp': timestamp}
            
            # Fallback: compare by title and artist (case insensitive)
            elif (song_to_check.get('title') and song_to_check.get('artist') and 
                  song_info.get('title') and song_info.get('artist')):
                if (song_to_check['title'].lower() == song_info['title'].lower() and
                    song_to_check['artist'].lower() == song_info['artist'].lower()):
                    return {'song': song_info, 'username': username, 'timestamp': timestamp}
        
        return None

    def get_user_queue_limit(self, ctx) -> int:
        """Get the queue limit for a user based on their role"""
        username = ctx.author.name.lower()
        
        # Streamer (you) gets unlimited
        if username == ctx.channel.name.lower():  # Channel owner
            return float('inf')  # Unlimited
            
        # Moderators get 25
        if ctx.author.is_mod:
            return 25
            
        # VIPs get 25 (check if user has VIP badge)
        if hasattr(ctx.author, 'badges') and 'vip' in ctx.author.badges:
            return 25
            
        # Subscribers get 10 (check if user has subscriber badge)
        if ctx.author.is_subscriber:
            return 10
            
        # Non-subscribers get 1
        return 1

    def is_youtube_playlist_url(self, url: str) -> bool:
        """Check if URL is a YouTube playlist"""
        playlist_indicators = [
            'list=',
            'playlist?list=',
            '&list=',
            'youtube.com/playlist',
        ]
        return any(indicator in url.lower() for indicator in playlist_indicators)

    def is_song_on_cooldown(self, song) -> bool:
        """Check if a song is still on cooldown (20 minutes)"""
        from datetime import datetime, timedelta
        
        song_number = song.get('number') if isinstance(song, dict) else song
        if song_number not in self.song_cooldowns:
            return False
            
        last_played = self.song_cooldowns[song_number]
        cooldown_end = last_played + timedelta(minutes=self.cooldown_minutes)
        
        return datetime.now() < cooldown_end

    def get_cooldown_remaining(self, song) -> int:
        """Get remaining cooldown time in minutes"""
        from datetime import datetime, timedelta
        
        song_number = song.get('number') if isinstance(song, dict) else song
        if song_number not in self.song_cooldowns:
            return 0
            
        last_played = self.song_cooldowns[song_number]
        cooldown_end = last_played + timedelta(minutes=self.cooldown_minutes)
        now = datetime.now()
        
        if now >= cooldown_end:
            return 0
            
        remaining = cooldown_end - now
        return max(0, int(remaining.total_seconds() / 60))

    def add_song_cooldown(self, song):
        """Add a song to cooldown (called when song is played)"""
        from datetime import datetime
        song_number = song.get('number') if isinstance(song, dict) else song
        self.song_cooldowns[song_number] = datetime.now()
    
    async def start_smart_pre_cache(self, song_info):
        """Start caching a song immediately when requested to reduce playback gaps"""
        try:
            import os
            import asyncio
            if not song_info or self.is_caching:
                return
            
            song_identifier = None
            
            # Handle playlist songs
            if song_info.get('number'):
                song_identifier = f"playlist_{song_info['number']}"
                
                # Check if already cached
                cache_file = self._get_cache_filename(song_info)
                if os.path.exists(cache_file):
                    self.logger.info(f"Song #{song_info['number']} already cached: {song_info['title']}")
                    return
                    
            # Handle YouTube requests
            elif song_info.get('youtube_url') and not song_info.get('number'):
                song_identifier = f"youtube_{hash(song_info['youtube_url'])}"
            else:
                return
                
            # Cancel any existing pre-cache task for this song
            if song_identifier in self.pre_cache_tasks:
                self.pre_cache_tasks[song_identifier].cancel()
                
            # Start background caching task
            task = asyncio.create_task(self._background_cache_song(song_info, song_identifier))
            self.pre_cache_tasks[song_identifier] = task
            
            self.logger.info(f"Started pre-caching: {song_info.get('title', 'Unknown')} (ID: {song_identifier})")
            
        except Exception as e:
            self.logger.error(f"Error starting pre-cache: {e}")
    
    async def _background_cache_song(self, song_info, identifier):
        """Background task to cache a single song"""
        try:
            import yt_dlp
            import os
            
            # Determine the URL to download
            if song_info.get('youtube_url'):
                url = song_info['youtube_url']
            else:
                self.logger.warning(f"No YouTube URL for song: {song_info}")
                return
                
            cache_file = self._get_cache_filename(song_info)
            
            # Skip if already exists
            if os.path.exists(cache_file):
                return
                
            self.logger.info(f"Background caching: {song_info.get('title', 'Unknown')}")
            
            # Download with yt-dlp
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'outtmpl': cache_file,
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            self.logger.info(f"✅ Pre-cached: {song_info.get('title', 'Unknown')}")
            
        except asyncio.CancelledError:
            self.logger.info(f"Pre-cache cancelled: {identifier}")
        except Exception as e:
            self.logger.error(f"Error in background cache: {e}")
        finally:
            # Clean up task reference
            if identifier in self.pre_cache_tasks:
                del self.pre_cache_tasks[identifier]
    
    async def pre_cache_next_random(self):
        """Pre-cache the next likely random song for smooth auto-playlist"""
        try:
            if self.is_caching or not self.playlist_cache:
                return
                
            # Get next random song (same logic as get_random_playlist_song)
            random_song = self.get_random_playlist_song()
            if not random_song or not random_song.get('youtube_url'):
                return
                
            # Check if already cached
            cache_file = self._get_cache_filename(random_song)
            if os.path.exists(cache_file):
                self.next_random_cached = random_song
                return
                
            # Start caching this random song
            await self.start_smart_pre_cache(random_song)
            self.next_random_cached = random_song
            
            self.logger.info(f"Pre-caching next random song: {random_song['title']} by {random_song['artist']}")
            
        except Exception as e:
            self.logger.error(f"Error pre-caching next random: {e}")

    def find_lowest_available_number(self) -> int:
        """Find the lowest available number in the catalog (for gap filling)"""
        if not self.playlist_cache:
            return 1
            
        # Get all existing numbers, sorted
        existing_numbers = sorted([song['number'] for song in self.playlist_cache])
        
        # Find first gap
        for i, num in enumerate(existing_numbers, 1):
            if i != num:
                return i
                
        # No gaps found, return next highest number
        return max(existing_numbers) + 1
    
    def _get_cache_filename(self, song_info):
        """Get consistent cache filename for a song"""
        import os
        
        if song_info.get('number'):
            # Playlist song - use number and sanitized title
            title = song_info.get('title', 'Unknown')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            filename = f"{song_info['number']:03d}_{safe_title}.m4a"
        else:
            # YouTube request - use hash of URL
            url_hash = abs(hash(song_info.get('youtube_url', '')))
            title = song_info.get('title', 'YouTube_Song')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            filename = f"yt_{url_hash}_{safe_title}.m4a"
            
        return os.path.join(MUSIC_CACHE_DIR, filename)

    def delete_song_from_catalog(self, song_number: int) -> bool:
        """Delete a song from the catalog by number"""
        original_count = len(self.playlist_cache)
        self.playlist_cache = [song for song in self.playlist_cache if song['number'] != song_number]
        
        if len(self.playlist_cache) < original_count:
            # Save the updated playlist
            try:
                with open(PLAYLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.playlist_cache, f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                self.logger.error(f"Error saving playlist after deletion: {e}")
                return False
        return False

    def get_cache_status(self) -> Dict:
        """Get comprehensive cache status and statistics"""
        cache_info = {
            'total_playlist_songs': len(self.playlist_cache),
            'cached_songs': 0,
            'missing_songs': [],
            'cache_size_mb': 0,
            'cached_files': [],
            'orphaned_files': []
        }
        
        if not os.path.exists(MUSIC_CACHE_DIR):
            return cache_info
        
        # Get all cached files
        cached_filenames = set()
        for filename in os.listdir(MUSIC_CACHE_DIR):
            if filename.lower().endswith(('.webm', '.m4a', '.mp3', '.mp4', '.opus')):
                file_path = os.path.join(MUSIC_CACHE_DIR, filename)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                cache_info['cache_size_mb'] += file_size
                cache_info['cached_files'].append({
                    'filename': filename,
                    'size_mb': round(file_size, 2)
                })
                
                # Extract the base name (remove extension and normalize)
                base_name = os.path.splitext(filename)[0]
                cached_filenames.add(base_name.lower())
        
        # Check which playlist songs are cached vs missing
        for song in self.playlist_cache:
            # Create expected filename (same logic as download function)
            safe_title = "".join(c for c in song['title'] if c.isalnum() or c in (' ', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            
            if safe_title.lower() in cached_filenames:
                cache_info['cached_songs'] += 1
            else:
                cache_info['missing_songs'].append({
                    'number': song['number'],
                    'title': song['title'],
                    'artist': song['artist'],
                    'youtube_url': song.get('youtube_url', '')
                })
        
        # Find orphaned files (cached but not in playlist)
        playlist_safe_names = set()
        for song in self.playlist_cache:
            safe_title = "".join(c for c in song['title'] if c.isalnum() or c in (' ', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            playlist_safe_names.add(safe_title.lower())
        
        for cached_file in cache_info['cached_files']:
            base_name = os.path.splitext(cached_file['filename'])[0].lower()
            if base_name not in playlist_safe_names:
                cache_info['orphaned_files'].append(cached_file)
        
        cache_info['cache_size_mb'] = round(cache_info['cache_size_mb'], 2)
        return cache_info

    async def cache_missing_songs(self, max_downloads: int = 10, chat_channel=None) -> Dict:
        """Download missing songs from the playlist to cache"""
        # Set caching flag to prevent conflicts
        self.is_caching = True
        
        try:
            cache_status = self.get_cache_status()
            missing_songs = cache_status['missing_songs']
            
            if not missing_songs:
                return {
                    'success': True,
                    'message': 'All playlist songs are already cached!',
                    'downloaded': 0,
                    'failed': 0,
                    'total_missing': 0
                }
            
            # Limit downloads to prevent overwhelming
            songs_to_download = missing_songs[:max_downloads]
            
            self.logger.info(f"Starting cache operation: {len(songs_to_download)} songs to download")
            if chat_channel:
                await chat_channel.send(f"🔄 Starting cache download: {len(songs_to_download)} songs (max {max_downloads})")
            
            # Start background music during caching if not already playing
            if not self.is_playing and not self.is_paused:
                try:
                    self.logger.info("🎵 Starting background music during cache operation...")
                    background_result = await self.simple_play_cached_file(chat_channel)
                    if background_result and chat_channel:
                        await chat_channel.send("🎵 Playing background music while caching...")
                except Exception as bg_error:
                    self.logger.error(f"Failed to start background music: {bg_error}")
            
            downloaded = 0
            failed = 0
            
            for i, song_info in enumerate(songs_to_download, 1):
                if not song_info.get('youtube_url'):
                    self.logger.warning(f"No YouTube URL for song #{song_info['number']}: {song_info['title']}")
                    failed += 1
                    continue
                
                try:
                    self.logger.info(f"Caching [{i}/{len(songs_to_download)}]: {song_info['title']}")
                    if chat_channel and i % 5 == 0:  # Update every 5 songs
                        await chat_channel.send(f"📥 Progress: {i}/{len(songs_to_download)} cached...")
                    
                    # Download the song
                    audio_file = await self.download_and_normalize_audio(
                        song_info['youtube_url'], 
                        song_info['title']
                    )
                    
                    if audio_file and os.path.exists(audio_file):
                        downloaded += 1
                        self.logger.info(f"✅ Cached: {song_info['title']}")
                    else:
                        failed += 1
                        self.logger.error(f"❌ Failed to cache: {song_info['title']}")
                    
                    # Small delay to prevent rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    failed += 1
                    self.logger.error(f"❌ Error caching {song_info['title']}: {e}")
            
            # Get updated cache status to show accurate remaining count
            updated_cache_status = self.get_cache_status()
            remaining_missing = len(updated_cache_status['missing_songs'])
            
            result = {
                'success': True,
                'message': f'Cache operation complete: {downloaded} downloaded, {failed} failed',
                'downloaded': downloaded,
                'failed': failed,
                'total_missing': len(missing_songs),
                'remaining_missing': remaining_missing
            }
            
            if chat_channel:
                await chat_channel.send(f"✅ Cache complete: {downloaded} downloaded, {failed} failed. {remaining_missing} remaining of {len(self.playlist_cache)} total.")
            
            return result
            
        finally:
            # Always clear the caching flag
            self.is_caching = False

    async def cache_all_playlist_songs(self, batch_size: int = 20, chat_channel=None) -> Dict:
        """Cache the entire playlist in batches"""
        # Set caching flag to prevent conflicts
        self.is_caching = True
        
        try:
            cache_status = self.get_cache_status()
            missing_songs = cache_status['missing_songs']
            
            if not missing_songs:
                return {
                    'success': True,
                    'message': 'All playlist songs already cached!',
                    'total_downloaded': 0,
                    'total_failed': 0
                }
            
            total_downloaded = 0
            total_failed = 0
            
            self.logger.info(f"Starting full playlist cache: {len(missing_songs)} songs in batches of {batch_size}")
            if chat_channel:
                await chat_channel.send(f"🚀 Starting full playlist cache: {len(missing_songs)} missing songs")
            
            # Start background music during full cache if not already playing
            if not self.is_playing and not self.is_paused:
                try:
                    self.logger.info("🎵 Starting background music during full cache operation...")
                    background_result = await self.simple_play_cached_file(chat_channel)
                    if background_result and chat_channel:
                        await chat_channel.send("🎵 Background music started while caching continues...")
                except Exception as bg_error:
                    self.logger.error(f"Failed to start background music during cache: {bg_error}")
            
            # Process in batches
            for batch_num in range(0, len(missing_songs), batch_size):
                batch = missing_songs[batch_num:batch_num + batch_size]
                batch_number = (batch_num // batch_size) + 1
                total_batches = (len(missing_songs) + batch_size - 1) // batch_size
                
                self.logger.info(f"Processing batch {batch_number}/{total_batches} ({len(batch)} songs)")
                if chat_channel:
                    await chat_channel.send(f"📦 Batch {batch_number}/{total_batches}: Caching {len(batch)} songs...")
                
                result = await self.cache_missing_songs(len(batch), chat_channel)
                total_downloaded += result['downloaded']
                total_failed += result['failed']
                
                # Longer delay between batches
                if batch_num + batch_size < len(missing_songs):
                    await asyncio.sleep(3)
            
            final_result = {
                'success': True,
                'message': f'Full cache complete: {total_downloaded} downloaded, {total_failed} failed',
                'total_downloaded': total_downloaded,
                'total_failed': total_failed,
                'cache_completion_percent': round((cache_status['cached_songs'] + total_downloaded) / len(self.playlist_cache) * 100, 1)
            }
            
            if chat_channel:
                await chat_channel.send(f"🎉 Full cache complete! {total_downloaded} downloaded, {total_failed} failed. Cache {final_result['cache_completion_percent']}% complete.")
            
            return final_result
            
        finally:
            # Always clear the caching flag
            self.is_caching = False

    async def download_hot_queue_audio(self, youtube_url: str, song_title: str, chat_channel=None) -> Optional[str]:
        """Download YouTube audio to temporary file for hot queue (auto-delete after play)"""
        if not YT_DLP_AVAILABLE:
            self.logger.error(f"yt-dlp not available for hot queue download: {song_title}")
            return None
        
        self.logger.info(f"Starting hot queue download for: {song_title} from {youtube_url}")
        
        try:
            import tempfile
            import uuid
            
            # Create temporary filename with random ID
            temp_id = str(uuid.uuid4())[:8]
            temp_filename = f"hotqueue_{temp_id}"
            temp_dir = os.path.join(MUSIC_CACHE_DIR, "temp")
            os.makedirs(temp_dir, exist_ok=True)
            
            output_template = os.path.join(temp_dir, f"{temp_filename}.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
            }
            
            # Download with timeout
            def download_with_timeout():
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([youtube_url])
                    return True
                except Exception as e:
                    self.logger.error(f"Hot queue download failed for {song_title}: {e}")
                    return False
            
            loop = asyncio.get_event_loop()
            try:
                success = await asyncio.wait_for(
                    loop.run_in_executor(None, download_with_timeout), 
                    timeout=30.0
                )
                
                if success:
                    # Find the downloaded temporary file
                    for ext in ['m4a', 'webm', 'mp4', 'opus', 'ogg']:
                        test_file = os.path.join(temp_dir, f"{temp_filename}.{ext}")
                        if os.path.exists(test_file):
                            self.logger.info(f"Successfully downloaded hot queue: {test_file}")
                            return test_file
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"Hot queue download timeout for {song_title}")
                if chat_channel:
                    await chat_channel.send("⏰ Hot queue download timed out")
            except Exception as e:
                self.logger.error(f"Hot queue download error for {song_title}: {e}")
                
        except Exception as e:
            self.logger.error(f"Error in hot queue download: {e}")
            
        return None

    async def download_and_normalize_audio(self, youtube_url: str, song_title: str, chat_channel=None) -> Optional[str]:
        """Download YouTube audio (no FFmpeg required)"""
        if not YT_DLP_AVAILABLE:
            self.logger.error(f"yt-dlp not available for download: {song_title}")
            return None
        
        self.logger.info(f"Starting download for: {song_title} from {youtube_url}")
        
        try:
            # Create safe filename
            safe_title = "".join(c for c in song_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            
            # Try multiple audio extensions
            for ext in ['m4a', 'webm', 'mp4', 'mp3']:
                audio_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                if os.path.exists(audio_file):
                    self.logger.info(f"Using cached audio: {audio_file}")
                    return audio_file
            
            # Download best audio format available (no conversion)
            output_template = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.%(ext)s")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                # No postprocessors - avoid FFmpeg dependency
            }
            
            # Check if file already exists first
            for ext in ['m4a', 'webm', 'mp4', 'opus', 'ogg']:
                test_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                if os.path.exists(test_file):
                    self.logger.info(f"Using existing cached audio: {test_file}")
                    return test_file
            
            # Attempt actual download with timeout protection
            self.logger.info(f"Attempting download for {song_title} from {youtube_url}")
            
            def download_with_timeout():
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([youtube_url])
                    return True
                except Exception as e:
                    self.logger.error(f"Download failed for {song_title}: {e}")
                    return False
            
            # Run download in executor with timeout
            loop = asyncio.get_event_loop()
            try:
                # 30 second timeout for downloads
                success = await asyncio.wait_for(
                    loop.run_in_executor(None, download_with_timeout), 
                    timeout=30.0
                )
                
                if success:
                    # Find the downloaded file
                    for ext in ['m4a', 'webm', 'mp4', 'opus', 'ogg']:
                        test_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                        if os.path.exists(test_file):
                            self.logger.info(f"Successfully downloaded: {test_file}")
                            return test_file
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"Download timeout for {song_title}")
            except Exception as e:
                self.logger.error(f"Download error for {song_title}: {e}")
            
            # Check all files in cache directory for our title
            if os.path.exists(MUSIC_CACHE_DIR):
                for filename in os.listdir(MUSIC_CACHE_DIR):
                    if safe_title.lower() in filename.lower():
                        full_path = os.path.join(MUSIC_CACHE_DIR, filename)
                        self.logger.info(f"Found cached file: {full_path}")
                        return full_path
                
                # If no specific match, return ANY cached file to get music playing
                cached_files = [f for f in os.listdir(MUSIC_CACHE_DIR) 
                              if f.lower().endswith(('.m4a', '.webm', '.mp4', '.opus', '.ogg', '.mp3'))]
                if cached_files:
                    fallback_file = os.path.join(MUSIC_CACHE_DIR, cached_files[0])
                    self.logger.info(f"Using fallback cached file: {fallback_file}")
                    if chat_channel:
                        await chat_channel.send(f"🎵 Playing cached song instead (downloads temporarily disabled)")
                    return fallback_file
            
        except Exception as e:
            self.logger.error(f"Error downloading audio: {e}")
            
            # Report broken song to chat if we have a channel
            if chat_channel:
                # Find the song number for easier fixing
                song_number = None
                for song in self.playlist_cache:
                    if (song.get('youtube_url') == youtube_url or 
                        song.get('title') == song_title):
                        song_number = song.get('number', '?')
                        break
                
                error_msg = f"🚨 BROKEN SONG: #{song_number} - {song_title}"
                if "Video unavailable" in str(e):
                    error_msg += " (Video unavailable)"
                elif "Private video" in str(e):
                    error_msg += " (Private video)"
                else:
                    error_msg += f" (Error: {str(e)[:50]})"
                
                error_msg += f" | Use !music fix {song_number} to auto-repair"
                
                try:
                    asyncio.create_task(chat_channel.send(error_msg))
                except Exception as chat_error:
                    self.logger.error(f"Failed to send error to chat: {chat_error}")
        
        return None

    async def play_song(self, song_info: dict, username: str, chat_channel=None) -> bool:
        """Play a song with global music state manager to prevent overlapping playback"""
        if not self.audio_ready:
            self.logger.warning("Audio system not available")
            return False
        
        # Check global music state manager for overlap prevention
        if MUSIC_STATE_AVAILABLE and music_state_manager:
            # Try to start playback - will fail if music already playing
            if not music_state_manager.start_playback(song_info):
                self.logger.warning(f"Music overlap prevented: {music_state_manager.get_current_song().get('title', 'Unknown')} is already playing")
                if chat_channel:
                    await chat_channel.send(f"⏸️ Music already playing: {music_state_manager.get_current_song().get('title', 'Unknown')}")
                return False
        
        try:
            # Stop any existing local music (pygame, etc) since state manager only handles ffmpeg
            await self.stop_music()
            await asyncio.sleep(0.2)  # Brief pause for cleanup
            
            youtube_url = song_info.get('youtube_url')
            if not youtube_url:
                self.logger.warning("No YouTube URL for song")
                if MUSIC_STATE_AVAILABLE and music_state_manager:
                    music_state_manager.stop_playback()
                return False
            
            # Check if this is a hot queue item
            is_hot_queue = song_info.get('hot_queue', False)
            
            # Try to get audio file (download if needed)
            if is_hot_queue:
                audio_file = await self.download_hot_queue_audio(youtube_url, song_info['title'], chat_channel)
            else:
                audio_file = await self.download_and_normalize_audio(youtube_url, song_info['title'], chat_channel)
            
            if not audio_file:
                self.logger.warning(f"Could not download audio for: {song_info['title']}")
                if MUSIC_STATE_AVAILABLE and music_state_manager:
                    music_state_manager.stop_playback()
                return False
            
            # Verify file exists and is not empty
            if not os.path.exists(audio_file) or os.path.getsize(audio_file) == 0:
                self.logger.error(f"Audio file invalid: {audio_file}")
                if MUSIC_STATE_AVAILABLE and music_state_manager:
                    music_state_manager.stop_playback()
                return False
            
            # Play using available backend
            if self.audio_backend == "pygame":
                self.logger.info(f"🎵 Starting pygame playback: {song_info['title']}")
                
                # Load and play new track
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.set_volume(self.master_volume)
                pygame.mixer.music.play()
                
            elif self.audio_backend == "playsound3":
                self.logger.info(f"🎵 Starting playsound3 playback: {song_info['title']}")
                
                import playsound3
                import threading
                import subprocess
                
                def play_async():
                    try:
                        # Use subprocess to avoid blocking and allow termination
                        cmd = ['python', '-c', f'import playsound3; playsound3.playsound(r"{audio_file}")']
                        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        # Register process with music state manager
                        if MUSIC_STATE_AVAILABLE and music_state_manager:
                            music_state_manager.set_current_process(process)
                        
                        process.wait()
                        
                        # Clean up hot queue files after playback
                        if is_hot_queue and os.path.exists(audio_file):
                            try:
                                os.remove(audio_file)
                                self.logger.info(f"🗑️ Cleaned up hot queue file: {audio_file}")
                            except Exception as e:
                                self.logger.warning(f"Could not delete hot queue file: {e}")
                        
                        # Clear state when done
                        if MUSIC_STATE_AVAILABLE and music_state_manager:
                            music_state_manager.stop_playback()
                        
                        self.is_playing = False
                        self.logger.info("✅ Playsound3 playback completed")
                        
                    except Exception as e:
                        self.logger.error(f"❌ Playsound3 error: {e}")
                        if MUSIC_STATE_AVAILABLE and music_state_manager:
                            music_state_manager.stop_playback()
                        self.is_playing = False
                
                # Play in background thread
                play_thread = threading.Thread(target=play_async, daemon=True)
                play_thread.start()
            
            # Update local state
            self.is_playing = True
            self.is_paused = False
            self.current_song = audio_file
            self.current_song_info = (song_info, username)
            self.current_hot_queue_file = audio_file if is_hot_queue else None  # Track for cleanup
            
            # Track song timing
            import time
            self.song_start_time = time.time()
            self.song_duration = song_info.get('duration', 300)  # Default 5 minutes if no duration
            
            self.logger.info(f"🎵 Playing: {song_info['title']} (requested by {username}) via {self.audio_backend}")
            
            # Increment play count for playlist songs (not user requests)
            if username == "AutoPlaylist":
                self.increment_play_count(song_info)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error playing song: {e}")
            if MUSIC_STATE_AVAILABLE and music_state_manager:
                music_state_manager.stop_playback()
            return False

    async def stop_music(self):
        """Stop current music using global music state manager"""
        self.logger.info("🛑 Stopping music with global state manager")
        
        # Use global music state manager to stop
        if MUSIC_STATE_AVAILABLE and music_state_manager:
            music_state_manager.stop_playback()
        
        # Also handle local audio backend cleanup
        if self.audio_ready and self.audio_backend == "pygame":
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(0.0)
                
                # Brief pause
                await asyncio.sleep(0.1)
                
                # Restore volume for next song
                pygame.mixer.music.set_volume(self.master_volume)
                
                self.logger.info("✅ Pygame stop completed")
                
            except Exception as e:
                self.logger.error(f"❌ Error during pygame stop: {e}")
                # Fallback: try to reinit
                try:
                    pygame.mixer.quit()
                    pygame.mixer.init()
                    pygame.mixer.music.set_volume(self.master_volume)
                    self.logger.info("🔄 Pygame reinitialized after error")
                except Exception as reinit_error:
                    self.logger.error(f"❌ Failed to reinitialize pygame: {reinit_error}")
        
        elif self.audio_backend == "playsound3":
            # For playsound3, use global music state manager's force stop
            if MUSIC_STATE_AVAILABLE and music_state_manager:
                music_state_manager.force_stop_playback()
        
        # Clean up hot queue files if needed
        if hasattr(self, 'current_hot_queue_file') and self.current_hot_queue_file and os.path.exists(self.current_hot_queue_file):
            try:
                os.remove(self.current_hot_queue_file)
                self.logger.info(f"🗑️ Cleaned up hot queue file: {self.current_hot_queue_file}")
            except Exception as e:
                self.logger.warning(f"Could not delete hot queue file: {e}")
            finally:
                self.current_hot_queue_file = None
        
        # Clear local state
        self.is_playing = False
        self.is_paused = False
        self.current_song = None
        self.current_song_info = None
        self.song_start_time = None
        self.song_duration = None
        
        self.logger.info("🔄 Music state cleared")

    def pause_music(self):
        """Pause current music playback"""
        if self.audio_ready and self.is_playing:
            if self.audio_backend == "pygame" and pygame.mixer.get_init():
                pygame.mixer.music.pause()
                self.is_paused = True
            elif self.audio_backend == "playsound3":
                # playsound3 doesn't support pause/resume
                return False
        return True

    def resume_music(self):
        """Resume paused music playback"""
        if self.audio_ready and self.is_paused:
            if self.audio_backend == "pygame" and pygame.mixer.get_init():
                pygame.mixer.music.unpause()
                self.is_paused = False
                return True
            elif self.audio_backend == "playsound3":
                # playsound3 doesn't support pause/resume
                return False
        return True

    def set_volume(self, volume: float):
        """Set master volume (0.0 to 1.0)"""
        self.master_volume = max(0.0, min(1.0, volume))
        if self.audio_ready:
            if self.audio_backend == "pygame" and pygame.mixer.get_init():
                pygame.mixer.music.set_volume(self.master_volume)
            elif self.audio_backend == "playsound3":
                # playsound3 doesn't support volume control
                pass

    def get_playback_status(self) -> str:
        """Get current playback status"""
        if not self.music_enabled:
            return "🔇 Music disabled"
        if not self.audio_ready:
            return "❌ Audio system unavailable"
        
        backend_info = f" ({self.audio_backend})" if self.audio_backend else ""
        
        if self.is_paused:
            return f"⏸️ Paused{backend_info}"
        if self.is_playing:
            return f"▶️ Playing{backend_info}"
        return f"⏹️ Stopped{backend_info}"

    def get_random_playlist_song(self):
        """Get a song from the curated playlist with improved play count balancing"""
        if not self.playlist_cache:
            return None
        
        import random
        
        # Sort songs by play count (least played first)
        sorted_songs = sorted(self.playlist_cache, key=lambda x: x.get('play_count', 0))
        
        # Find the minimum and maximum play counts
        min_play_count = sorted_songs[0].get('play_count', 0)
        max_play_count = sorted_songs[-1].get('play_count', 0)
        
        # If all songs have the same play count, pick randomly
        if min_play_count == max_play_count:
            selected_song = random.choice(self.playlist_cache)
            self.logger.info(f"Selected random song (all equal play_count {min_play_count}): {selected_song['title']} by {selected_song['artist']}")
            return selected_song
        
        # Create weighted selection pool based on inverse play count
        weighted_songs = []
        for song in self.playlist_cache:
            play_count = song.get('play_count', 0)
            
            # Calculate weight: songs with lower play counts get exponentially higher weights
            # Formula gives much higher weight to less played songs
            weight = max_play_count - play_count + 1
            
            # Extra boost for completely unplayed songs
            if play_count == 0:
                weight *= 5  # 5x weight for unplayed songs
            elif play_count <= min_play_count + 1:
                weight *= 3  # 3x weight for songs played once or twice
            
            # Add song multiple times based on weight
            weighted_songs.extend([song] * weight)
        
        # Select from weighted pool
        selected_song = random.choice(weighted_songs)
        play_count = selected_song.get('play_count', 0)
        self.logger.info(f"Selected weighted random song (play_count {play_count}): {selected_song['title']} by {selected_song['artist']}")
        
        return selected_song

    def increment_play_count(self, song_info):
        """Increment the play count for a song and save to file"""
        try:
            # Find the song in the playlist cache
            for song in self.playlist_cache:
                if (song.get('youtube_url') == song_info.get('youtube_url') or 
                    (song.get('title') == song_info.get('title') and 
                     song.get('artist') == song_info.get('artist'))):
                    
                    # Increment play count
                    current_count = song.get('play_count', 0)
                    song['play_count'] = current_count + 1
                    
                    # Add song to cooldown to prevent immediate re-requests
                    self.add_song_cooldown(song)
                    
                    self.logger.info(f"Incremented play count for '{song['title']}' by {song['artist']}: {current_count} -> {song['play_count']} (added to {self.cooldown_minutes}-minute cooldown)")
                    
                    # Save the updated playlist asynchronously
                    asyncio.create_task(self._save_playlist_async())
                    
                    break
        except Exception as e:
            self.logger.error(f"Failed to increment play count: {e}")
    
    async def _save_playlist_async(self):
        """Save playlist cache asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._save_playlist_sync)
        except Exception as e:
            self.logger.error(f"Failed to save playlist async: {e}")
    
    def _save_playlist_sync(self):
        """Synchronous playlist saving for executor"""
        import json
        with open(PLAYLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.playlist_cache, f, indent=2, ensure_ascii=False)
    
    def _extract_video_info_sync(self, youtube_url):
        """Synchronous video info extraction for executor"""
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'no_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(youtube_url, download=False)

    async def simple_play_cached_file(self, chat_channel=None):
        """Simple method to play any cached file without complex logic"""
        try:
            # Allow music playback during caching (from already cached files)
            # Only downloads are blocked, not playback from existing cache
            if self.is_caching:
                self.logger.info("🎵 Playing cached music during cache operation...")
            
            self.logger.info("simple_play_cached_file: Starting...")
            import os
            import random
            cache_dir = MUSIC_CACHE_DIR
            
            self.logger.info(f"simple_play_cached_file: Checking cache directory: {cache_dir}")
            
            if not os.path.exists(cache_dir):
                self.logger.warning("simple_play_cached_file: Cache directory does not exist")
                if chat_channel:
                    await chat_channel.send("❌ No cached music files found")
                return None
            
            # Find any cached audio file
            cached_files = []
            self.logger.info("simple_play_cached_file: Scanning for audio files...")
            
            try:
                for file in os.listdir(cache_dir):
                    if file.lower().endswith(('.m4a', '.webm', '.mp4', '.opus', '.ogg', '.mp3')):
                        cached_files.append(file)
                        
                self.logger.info(f"simple_play_cached_file: Found {len(cached_files)} audio files")
                
            except Exception as scan_error:
                self.logger.error(f"simple_play_cached_file: Error scanning directory: {scan_error}")
                if chat_channel:
                    await chat_channel.send(f"❌ Error scanning audio cache: {scan_error}")
                return None
            
            if not cached_files:
                self.logger.warning("simple_play_cached_file: No audio files found in cache")
                if chat_channel:
                    await chat_channel.send("❌ No audio files in cache")
                return None
            
            # Check global music state manager first
            if MUSIC_STATE_AVAILABLE and music_state_manager:
                if music_state_manager.is_music_playing():
                    current_song = music_state_manager.get_current_song()
                    self.logger.warning(f"🚫 Music overlap prevented: {current_song.get('title', 'Unknown')} is already playing")
                    if chat_channel:
                        await chat_channel.send(f"⏸️ Music already playing: {current_song.get('title', 'Unknown')}")
                    return None
            
            # Brief pause to ensure old audio stops
            self.logger.info("simple_play_cached_file: Brief pause for cleanup...")
            await asyncio.sleep(0.3)  # Quick pause for cleanup
            # Instead of random file, pick from properly matched playlist songs
            matched_songs = []
            
            # Find playlist songs that have corresponding cached files
            for song in self.playlist_cache:
                if song.get('title') and song.get('artist'):
                    # Create expected filename patterns
                    safe_title = "".join(c for c in song['title'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    safe_title = safe_title.replace(' ', '_')
                    
                    # Check if we have a cached file for this song
                    for cached_file in cached_files:
                        if safe_title.lower() in cached_file.lower():
                            matched_songs.append({
                                'file': cached_file,
                                'info': {
                                    'title': song['title'],
                                    'artist': song['artist'],
                                    'number': song.get('number', '?')
                                }
                            })
                            break
            
            # If we found matched songs, pick from those. Otherwise fall back to random
            if matched_songs:
                selected = random.choice(matched_songs)
                selected_file = selected['file']
                display_info = selected['info']
            else:
                # Fallback to old method if no matches
                selected_file = random.choice(cached_files)
                display_info = self._get_friendly_song_info(selected_file)
            
            audio_file = os.path.join(cache_dir, selected_file)
            
            # Use global music state manager to start playback
            if MUSIC_STATE_AVAILABLE and music_state_manager:
                if not music_state_manager.start_playback(display_info):
                    self.logger.warning("🚫 Failed to start playback - music state manager blocked it")
                    if chat_channel:
                        await chat_channel.send("⏸️ Cannot start playback - music already playing")
                    return None
            
            self.logger.info(f"🎵 Playing cached file: {selected_file}")
            
            # Play with current audio backend
            if self.audio_backend == "playsound3":
                import subprocess
                import threading
                
                def play_subprocess():
                    try:
                        self.logger.info(f"▶️ Starting playsound3 playback: {audio_file}")
                        cmd = ['python', '-c', f'import playsound3; playsound3.playsound(r"{audio_file}")']
                        
                        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        
                        # Register with music state manager
                        if MUSIC_STATE_AVAILABLE and music_state_manager:
                            music_state_manager.set_current_process(process)
                        
                        process.wait()
                        
                        # Clear state when done
                        if MUSIC_STATE_AVAILABLE and music_state_manager:
                            music_state_manager.stop_playback()
                        
                        self.is_playing = False
                        self.logger.info("✅ Playsound3 playback completed")
                        
                    except Exception as e:
                        self.logger.error(f"❌ Playsound3 error: {e}")
                        if MUSIC_STATE_AVAILABLE and music_state_manager:
                            music_state_manager.stop_playback()
                        self.is_playing = False
                
                # Start playback in thread
                play_thread = threading.Thread(target=play_subprocess, daemon=True)
                play_thread.start()
                
            elif self.audio_backend == "pygame":
                self.logger.info(f"▶️ Starting pygame playback: {audio_file}")
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.set_volume(self.master_volume)
                pygame.mixer.music.play()
            
            # Update local state
            self.is_playing = True
            self.current_song = audio_file
            self.current_song_info = (display_info, "System")
            
            # Send chat message
            if chat_channel:
                if display_info['artist'] and display_info['artist'] != "Unknown Artist":
                    await chat_channel.send(f"🎵 {display_info['title']} - {display_info['artist']}")
                else:
                    await chat_channel.send(f"🎵 {display_info['title']}")
            
            return (display_info, "System")
            
        except Exception as e:
            self.logger.error(f"❌ Error in simple_play_cached_file: {e}", exc_info=True)
            if chat_channel:
                await chat_channel.send(f"❌ Error playing cached file: {e}")
            
            # Clear music state on error
            if MUSIC_STATE_AVAILABLE and music_state_manager:
                music_state_manager.stop_playback()
        
        return None

    async def process_queue(self, chat_channel=None):
        """Process next song in queue, or play random playlist song if queue is empty"""
        if not self.music_enabled:
            return None
        
        # If there's a song in queue, play it
        if self.current_queue:
            song_info, username, timestamp = self.current_queue.pop(0)
            # Sync to Google Sheets after removing from queue
            self._sync_queue_to_sheets()
            
            # Important: Song is ALWAYS removed from queue regardless of success/failure
            # This prevents YouTube songs from getting stuck in a loop
            is_youtube_request = song_info.get('youtube_url') and not song_info.get('number')
            
            success = await self.play_song(song_info, username, chat_channel)
            if success:
                return song_info, username
            else:
                # If it's a YouTube request that failed, report it but don't retry
                if is_youtube_request:
                    self.logger.warning(f"YouTube request failed for {username}: {song_info.get('youtube_url', 'Unknown URL')}")
                    if chat_channel:
                        await chat_channel.send(f"❌ YouTube song failed to play for {username}. Moving to next song...")
                # For playlist songs that fail, we'll try the next queue item or random playlist
                return None
        
        # If queue is empty but music is enabled, play random playlist song with low play count
        elif self.playlist_cache:
            import os
            # Use pre-cached random song if available and cached
            random_song = None
            if (self.next_random_cached and 
                self.next_random_cached.get('youtube_url') and
                os.path.exists(self._get_cache_filename(self.next_random_cached))):
                random_song = self.next_random_cached
                self.next_random_cached = None  # Reset for next time
                self.logger.info(f"Using pre-cached random song: {random_song['title']}")
            else:
                random_song = self.get_random_playlist_song()
                
            if random_song:
                # Start pre-caching the next random song while this one plays
                asyncio.create_task(self.pre_cache_next_random())
                
                success = await self.play_song(random_song, "AutoPlaylist", chat_channel)
                if success:
                    return random_song, "AutoPlaylist"
        
        return None

# Initialize manager
song_manager = SimpleSongManager()

class SongRequestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = song_manager
        self.chat_channel = None  # Store channel for error reporting
        self.logger = logging.getLogger(__name__)

    @commands.command(name="srx")
    async def song_request(self, ctx, action_or_request: str = None, *, url: str = None):
        """Song request system: !srx [number] (FREE) | !srx [youtube_url] (1 quarter) | !srx add [url] (mod) | !srx hot [url] (mod) | !srx del [number] (mod)"""
        if not action_or_request:
            await ctx.send("🎵 **Song Requests:** `!srx 42` (playlist, FREE) | `!srx [youtube_url]` (1 quarter) | `!srx add [url]` (mod) | `!srx hot [url]` (mod) | `!srx del [number]` (mod)")
            return

        username = ctx.author.name
        action_or_request = action_or_request.strip()

        # Check for subcommands first
        if action_or_request.lower() == "add":
            # Mod-only: Add to catalog
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can add songs to the catalog.")
                return
            
            # If url is provided, use it; otherwise treat action_or_request as the URL
            target_url = url if url else None
            if not target_url and self.manager.is_youtube_url(action_or_request):
                # Handle case where URL is in the first argument: !srx add https://youtube.com/...
                await ctx.send("❌ Usage: `!srx add [youtube_url]` - put the URL after 'add'")
                return
            elif not target_url:
                await ctx.send("❌ Please provide a valid YouTube URL. Usage: `!srx add [youtube_url]`")
                return
            
            if not self.manager.is_youtube_url(target_url):
                await ctx.send("❌ Please provide a valid YouTube URL. Usage: `!srx add [youtube_url]`")
                return
                
            # Check for playlist URLs and reject them
            if self.manager.is_youtube_playlist_url(target_url):
                await ctx.send("❌ Playlist URLs are not supported. Please add individual songs one at a time.")
                return
            
            await self._handle_add_song_from_url(ctx, target_url)
            return

        elif action_or_request.lower() == "hot":
            # Mod-only: Hot queue
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can hot queue songs.")
                return
            
            # If url is provided, use it; otherwise handle direct URL format
            target_url = url if url else None
            if not target_url:
                await ctx.send("❌ Please provide a valid YouTube URL. Usage: `!srx hot [youtube_url]`")
                return
                
            if not self.manager.is_youtube_url(target_url):
                await ctx.send("❌ Please provide a valid YouTube URL. Usage: `!srx hot [youtube_url]`")
                return
                
            # Check for playlist URLs and reject them
            if self.manager.is_youtube_playlist_url(target_url):
                await ctx.send("❌ Playlist URLs are not supported. Please use individual song URLs.")
                return
            
            await self._handle_hot_queue(ctx, target_url)
            return

        elif action_or_request.lower() == "del":
            # Mod-only: Delete song from catalog
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can delete songs from the catalog.")
                return
            
            # url parameter should contain the song number
            if not url or not url.strip().isdigit():
                await ctx.send("❌ Please provide a song number to delete. Usage: `!srx del [number]`")
                return
            
            song_number = int(url.strip())
            await self._handle_delete_song(ctx, song_number)
            return

        # Handle regular requests (existing logic)
        # Check if it's a number (playlist request)
        if action_or_request.isdigit():
            await self._handle_playlist_request(ctx, int(action_or_request), username)
        elif self.manager.is_youtube_url(action_or_request):
            await self._handle_youtube_request(ctx, action_or_request, username)
        else:
            await ctx.send("❌ Invalid request. Use `!srx 42` for playlist songs, `!srx [youtube_url]` for YouTube requests, or `!srx add/hot [url]` for mod commands.")

    async def _handle_playlist_request(self, ctx, number: int, username: str):
        """Handle playlist song request (FREE for everyone)"""
        song = self.manager.find_playlist_song(number)
        if not song:
            await ctx.send(f"❌ Song #{number} not found in playlist.")
            return

        # Check if song is on cooldown
        if self.manager.is_song_on_cooldown(song):
            remaining_minutes = self.manager.get_cooldown_remaining(song)
            await ctx.send(f"❌ Song #{number} \"{song['title']}\" by {song['artist']} is on cooldown for {remaining_minutes} more minutes to prevent overplay.")
            return

        if len(self.manager.current_queue) >= self.manager.max_queue_length:
            await ctx.send("❌ Queue is full! Try again later.")
            return

        # Check if song is already in queue
        existing_entry = self.manager.is_song_in_queue(song)
        if existing_entry:
            await ctx.send(f"❌ Song #{number} \"{song['title']}\" by {song['artist']} is already in the queue (requested by {existing_entry['username']})!")
            return

        # Check per-user queue limit based on user role
        user_limit = self.manager.get_user_queue_limit(ctx)
        user_songs_in_queue = sum(1 for song_info, queue_username, timestamp in self.manager.current_queue 
                                 if queue_username.lower() == username.lower())
        
        if user_songs_in_queue >= user_limit:
            if user_limit == float('inf'):
                pass  # Streamer has unlimited access
            else:
                await ctx.send(f"❌ You already have {user_songs_in_queue} songs in the queue (max {user_limit} per person). Wait for some to play!")
                return

        # Start pre-caching this song immediately to reduce gaps
        if song.get('youtube_url'):
            await self.manager.start_smart_pre_cache(song)
        
        # Add to queue (playlist requests are FREE)
        queue_item = (song, username, datetime.now())
        self.manager.current_queue.append(queue_item)
        
        # Sync to Google Sheets
        self.manager._sync_queue_to_sheets()
        
        # Pre-cache next random song for smooth auto-playlist after queue
        asyncio.create_task(self.manager.pre_cache_next_random())
        
        position = len(self.manager.current_queue)
        
        # Show duration if available and indicate it's a YouTube stinger
        duration_str = ""
        if song.get('duration'):
            mins = song['duration'] // 60
            secs = song['duration'] % 60
            duration_str = f" ({mins}:{secs:02d})"
        
        youtube_indicator = "🎬" if song.get('youtube_url') else "🎵"
        
        await ctx.send(f"{youtube_indicator} Added #{number}: {song['title']} by {song['artist']}{duration_str} to queue (Position {position})")

    async def _handle_youtube_request(self, ctx, url: str, username: str):
        """Handle YouTube song request (costs 1 quarter)"""
        # Check for playlist URLs and reject them
        if self.manager.is_youtube_playlist_url(url):
            await ctx.send("❌ Playlist URLs are not supported for quarter requests. Please use individual song URLs.")
            return
            
        # Check if user has quarters
        quarters = self.manager.get_user_quarters(username)
        if quarters < self.manager.quarters_per_youtube_request:
            needed = self.manager.quarters_per_youtube_request - quarters
            await ctx.send(f"❌ YouTube requests cost {self.manager.quarters_per_youtube_request} quarter. You need {needed} more (you have {quarters}). Playlist requests are FREE!")
            return

        if len(self.manager.current_queue) >= self.manager.max_queue_length:
            await ctx.send("❌ Queue is full! Try again later.")
            return

        # Create temporary song info for duplicate checking
        temp_song_info = {'youtube_url': url}
        existing_entry = self.manager.is_song_in_queue(temp_song_info)
        if existing_entry:
            await ctx.send(f"❌ This YouTube video is already in the queue (requested by {existing_entry['username']})!")
            return

        # Check per-user queue limit based on user role
        user_limit = self.manager.get_user_queue_limit(ctx)
        user_songs_in_queue = sum(1 for song_info, queue_username, timestamp in self.manager.current_queue 
                                 if queue_username.lower() == username.lower())
        
        if user_songs_in_queue >= user_limit:
            if user_limit == float('inf'):
                pass  # Streamer has unlimited access
            else:
                await ctx.send(f"❌ You already have {user_songs_in_queue} songs in the queue (max {user_limit} per person). Wait for some to play!")
                return

        # Spend quarters
        if not self.manager.spend_quarters(username, self.manager.quarters_per_youtube_request):
            await ctx.send("❌ Error spending quarters. Try again.")
            return

        # Start pre-caching immediately to reduce gap
        temp_song_for_cache = {
            'youtube_url': url,
            'title': 'YouTube Request',  # Will be updated below
            'artist': 'YouTube'
        }
        await self.manager.start_smart_pre_cache(temp_song_for_cache)
        
        # Get actual video information to avoid caching conflicts
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'no_download': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'YouTube Song')
                artist = info.get('uploader', 'YouTube')
        except Exception as e:
            # Fallback if yt-dlp fails
            self.logger.warning(f"Failed to get YouTube info for quarter song: {e}")
            title = f'YouTube Song ({url[-8:]})'  # Use last 8 chars of URL for uniqueness
            artist = 'YouTube'
        
        song_info = {
            'title': title,
            'artist': artist,
            'youtube_url': url
        }

        # Add to queue
        queue_item = (song_info, username, datetime.now())
        self.manager.current_queue.append(queue_item)
        
        # Sync to Google Sheets
        self.manager._sync_queue_to_sheets()
        
        position = len(self.manager.current_queue)
        await ctx.send(f"🎵 Added YouTube song to queue (Position {position}) [-{self.manager.quarters_per_youtube_request} quarter]")

    @commands.command(name="queue")
    async def show_queue(self, ctx):
        """Show current song queue and request info"""
        # Show help message first
        await ctx.send("💡 **How to request:** `!srx 42` (playlist song, FREE) or `!srx [youtube_url]` (costs 1 quarter). Max 3 songs per person in queue.")
        
        if not self.manager.current_queue:
            await ctx.send("🎵 Queue is empty.")
            return

        queue_text = "🎵 **Current Queue:**\n"
        for i, (song, username, timestamp) in enumerate(self.manager.current_queue[:5], 1):
            title = song.get('title', 'Unknown')
            queue_text += f"{i}. {title} (requested by {username})\n"
        
        if len(self.manager.current_queue) > 5:
            queue_text += f"... and {len(self.manager.current_queue) - 5} more songs"
        
        await ctx.send(queue_text)

    @commands.command(name="sr")
    async def song_request_info(self, ctx):
        """Show song request info (alias for queue command)"""
        await self.show_queue(ctx)

    @commands.command(name="quarters")
    async def check_quarters(self, ctx):
        """Check user's quarters"""
        username = ctx.author.name
        quarters = self.manager.get_user_quarters(username)
        await ctx.send(f"💰 {username}, you have {quarters} quarter(s).")

    async def _handle_add_song_from_url(self, ctx, youtube_url: str):
        """Handle !srx add [url] - Add song to catalog from YouTube URL"""
        try:
            # Get video information using yt-dlp
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'no_download': True,
            }
            
            await ctx.send("🔍 Getting video information...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                title = info.get('title', 'Unknown Title')
                uploader = info.get('uploader', 'Unknown Artist')
                duration = info.get('duration', 0)
            
            # Find lowest available number (fills gaps first)
            next_number = self.manager.find_lowest_available_number()
            
            # Create song entry
            new_song = {
                "number": next_number,
                "title": title,
                "artist": uploader,
                "youtube_url": youtube_url,
                "duration": duration,
                "verified": True,
                "play_count": 0
            }
            
            # Add to playlist
            self.manager.playlist_cache.append(new_song)
            self.manager.playlist_cache.sort(key=lambda x: x['number'])
            
            # Save to file
            with open(PLAYLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.manager.playlist_cache, f, indent=2, ensure_ascii=False)
            
            # Format duration
            duration_str = ""
            if duration:
                mins = duration // 60
                secs = duration % 60
                duration_str = f" ({mins}:{secs:02d})"
            
            # Sync catalog to Google Sheets
            if SHEETS_SYNC_AVAILABLE and music_sheets_manager:
                try:
                    music_sheets_manager.force_sync_catalog()
                    self.manager.logger.info("Synced catalog to Google Sheets after adding song")
                except Exception as e:
                    self.manager.logger.error(f"Failed to sync catalog to sheets: {e}")
            
            await ctx.send(f"✅ Added #{next_number}: {title} by {uploader}{duration_str} 🎬")
            
        except Exception as e:
            await ctx.send(f"❌ Error adding song: {str(e)[:100]}")

    async def _handle_hot_queue(self, ctx, youtube_url: str):
        """Handle !srx hot [url] - Hot queue a YouTube song"""
        try:
            # Get actual video information for unique caching
            try:
                import yt_dlp
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'no_download': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    title = info.get('title', 'Hot Queue Song')
                    artist = info.get('uploader', 'YouTube')
            except Exception as e:
                # Fallback if yt-dlp fails
                title = f'Hot Queue ({youtube_url[-8:]})'  # Use last 8 chars for uniqueness
                artist = 'YouTube'
            
            # Create temporary song info for hot queue
            temp_song = {
                'title': title,
                'artist': artist,
                'youtube_url': youtube_url,
                'hot_queue': True  # Flag for temporary download
            }
            
            # Add to front of queue for immediate play
            from datetime import datetime
            queue_item = (temp_song, f"{ctx.author.name} (Hot)", datetime.now())
            self.manager.current_queue.insert(0, queue_item)  # Insert at front
            
            # Sync to sheets
            self.manager._sync_queue_to_sheets()
            
            await ctx.send(f"🔥 Hot queued YouTube song (will play next and auto-delete after)")
            
        except Exception as e:
            await ctx.send(f"❌ Error hot queueing: {str(e)[:100]}")

    async def _handle_delete_song(self, ctx, number: int):
        """Handle !srx del [number] - Delete song from catalog (mod only)"""
        try:
            # Find the song to get its details before deletion
            song = self.manager.find_playlist_song(number)
            if not song:
                await ctx.send(f"❌ Song #{number} not found in catalog.")
                return
            
            # Check if song is currently in the queue or playing
            if self.manager.is_song_in_queue(song):
                await ctx.send(f"❌ Cannot delete song #{number} \"{song['title']}\" by {song['artist']} - it's currently in the queue! Wait for it to play or clear the queue first.")
                return
            
            # Store song info for confirmation message
            title = song.get('title', 'Unknown')
            artist = song.get('artist', 'Unknown')
            
            # Delete the song using the manager method
            success = self.manager.delete_song_from_catalog(number)
            
            if success:
                # Remove from cooldown if present
                if number in self.manager.song_cooldowns:
                    del self.manager.song_cooldowns[number]
                
                await ctx.send(f"✅ Deleted song #{number}: \"{title}\" by {artist} from catalog.")
                
                # Log the deletion
                self.logger.info(f"Mod {ctx.author.name} deleted song #{number}: '{title}' by {artist}")
            else:
                await ctx.send(f"❌ Failed to delete song #{number}. Please try again.")
                
        except Exception as e:
            await ctx.send(f"❌ Error deleting song: {str(e)[:100]}")
            self.logger.error(f"Error in _handle_delete_song: {e}")

    @commands.command(name="givequarter")
    async def give_quarter(self, ctx, target_user: str = None, amount: int = 1):
        """Give quarters to a user (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can give quarters.")
            return

        if not target_user:
            await ctx.send("Usage: !givequarter [username] [amount]")
            return

        self.manager.give_quarters(target_user, amount)
        await ctx.send(f"💰 Gave {amount} quarter(s) to {target_user}.")

    @commands.command(name="clearqueue")
    async def clear_queue(self, ctx):
        """Clear song queue (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can clear the queue.")
            return

        self.manager.current_queue.clear()
        # Sync to Google Sheets after clearing queue
        self.manager._sync_queue_to_sheets()
        await ctx.send("🗑️ Queue cleared!")

    @commands.command(name="playlistinfo", aliases=["playlist"])
    async def playlist_info(self, ctx, number: int = None):
        """Show playlist info or specific song details"""
        if number:
            # Show specific song
            song = self.manager.find_playlist_song(number)
            if not song:
                await ctx.send(f"❌ Song #{number} not found in playlist.")
                return
            
            duration_str = ""
            if song.get('duration'):
                mins = song['duration'] // 60
                secs = song['duration'] % 60
                duration_str = f" ({mins}:{secs:02d})"
            
            youtube_indicator = "🎬 YouTube Stinger" if song.get('youtube_url') else "🎵 Audio Only"
            
            await ctx.send(f"#{number}: {song['title']} by {song['artist']}{duration_str} [{youtube_indicator}]")
        else:
            # Show playlist stats
            total_songs = len(self.manager.playlist_cache)
            youtube_songs = len([s for s in self.manager.playlist_cache if s.get('youtube_url')])
            
            await ctx.send(f"🎵 Playlist: {total_songs} total songs, {youtube_songs} with YouTube stingers. Use !playlistinfo [number] for details.")

    @commands.command(name="addurl", aliases=["addsongurl"])
    async def add_song_from_url(self, ctx, youtube_url: str = None):
        """Add song to catalog from YouTube URL (Mod only). Automatically gets title and artist."""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can manage the playlist.")
            return
        
        if not youtube_url or not self.manager.is_youtube_url(youtube_url):
            await ctx.send("❌ Please provide a valid YouTube URL. Usage: !addurl [youtube_url]")
            return
        
        try:
            # Get video information using yt-dlp
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'no_download': True,
            }
            
            await ctx.send("🔍 Getting video information...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                
                title = info.get('title', 'Unknown Title')
                uploader = info.get('uploader', 'Unknown Artist')
                duration = info.get('duration', 0)
            
            # Find lowest available number (fills gaps first)
            next_number = self.manager.find_lowest_available_number()
            
            # Create song entry
            new_song = {
                "number": next_number,
                "title": title,
                "artist": uploader,
                "youtube_url": youtube_url,
                "duration": duration,
                "verified": True,
                "play_count": 0
            }
            
            # Add to playlist
            self.manager.playlist_cache.append(new_song)
            self.manager.playlist_cache.sort(key=lambda x: x['number'])
            
            # Save to file
            with open(PLAYLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.manager.playlist_cache, f, indent=2, ensure_ascii=False)
            
            # Format duration
            duration_str = ""
            if duration:
                mins = duration // 60
                secs = duration % 60
                duration_str = f" ({mins}:{secs:02d})"
            
            await ctx.send(f"✅ Added #{next_number}: {title} by {uploader}{duration_str} 🎬")
            
        except Exception as e:
            await ctx.send(f"❌ Error adding song: {str(e)[:100]}")

    @commands.command(name="hotqueue", aliases=["hq"])
    async def hot_queue_song(self, ctx, youtube_url: str = None):
        """Hot queue a YouTube song (download, play once, then delete) - Mod only"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can hot queue songs.")
            return
        
        if not youtube_url or not self.manager.is_youtube_url(youtube_url):
            await ctx.send("❌ Please provide a valid YouTube URL. Usage: !hotqueue [youtube_url]")
            return
            
        # Check for playlist URLs and reject them
        if self.manager.is_youtube_playlist_url(youtube_url):
            await ctx.send("❌ Playlist URLs are not supported. Please use individual song URLs.")
            return
        
        try:
            # Get actual video information for unique caching
            try:
                import yt_dlp
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'no_download': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    title = info.get('title', 'Hot Queue Song')
                    artist = info.get('uploader', 'YouTube')
            except Exception as e:
                # Fallback if yt-dlp fails
                title = f'Hot Queue ({youtube_url[-8:]})'  # Use last 8 chars for uniqueness
                artist = 'YouTube'
            
            # Create temporary song info for hot queue
            temp_song = {
                'title': title,
                'artist': artist,
                'youtube_url': youtube_url,
                'hot_queue': True  # Flag for temporary download
            }
            
            # Add to front of queue for immediate play
            from datetime import datetime
            queue_item = (temp_song, f"{ctx.author.name} (Hot)", datetime.now())
            self.manager.current_queue.insert(0, queue_item)  # Insert at front
            
            # Sync to sheets
            self.manager._sync_queue_to_sheets()
            
            await ctx.send(f"🔥 Hot queued YouTube song (will play next and auto-delete after)")
            
        except Exception as e:
            await ctx.send(f"❌ Error hot queueing: {str(e)[:100]}")

    @commands.command(name="cleantemp", aliases=["cleanhot"])
    async def clean_temp_files(self, ctx):
        """Clean up temporary hot queue files (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can clean temporary files.")
            return
        
        try:
            temp_dir = os.path.join(MUSIC_CACHE_DIR, "temp")
            if not os.path.exists(temp_dir):
                await ctx.send("📁 No temporary files directory found.")
                return
            
            temp_files = [f for f in os.listdir(temp_dir) if f.startswith("hotqueue_")]
            if not temp_files:
                await ctx.send("🧹 No temporary hot queue files to clean.")
                return
            
            cleaned_count = 0
            total_size = 0
            
            for filename in temp_files:
                file_path = os.path.join(temp_dir, filename)
                try:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    total_size += file_size
                    cleaned_count += 1
                except Exception as e:
                    self.logger.warning(f"Could not delete {filename}: {e}")
            
            size_mb = total_size / (1024 * 1024)
            await ctx.send(f"🗑️ Cleaned {cleaned_count} temporary files ({size_mb:.1f} MB freed)")
            
        except Exception as e:
            await ctx.send(f"❌ Error cleaning temporary files: {str(e)[:100]}")

    @commands.command(name="modmusic", aliases=["modcommands", "musicmod"])
    async def mod_music_help(self, ctx):
        """Show mod-only music commands"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can view mod commands.")
            return
        
        help_text = """🎵 **Mod Music Commands:**
        
**Quick Add (Recommended):**
• `!addurl [youtube_url]` - Add song to catalog (auto-gets title/artist)
• `!addsong [youtube_url]` - Same as addurl (detects URLs automatically)

**Hot Queue:**
• `!hotqueue [youtube_url]` - Download, play once, then auto-delete
• `!cleantemp` - Clean up leftover temporary files

**Advanced Catalog:**
• `!addsong [number] Title | Artist | YouTube_URL` - Full manual entry
• `!playlistinfo [number]` - Check song details

**System:**
• `!music start/stop/next` - Control playback
• `!nowplaying` - Show current song

💡 **Tip:** Use `!addurl` or `!addsong [url]` for easiest song adding!"""
        
        await ctx.send(help_text)

    @commands.command(name="addsong")
    async def add_song(self, ctx, number_or_url: str = None, *, song_details: str = None):
        """Add/update song in playlist (Mod only). Format: !addsong [number] Title | Artist | YouTube_URL OR !addsong [youtube_url]"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can manage the playlist.")
            return
        
        if not number_or_url:
            await ctx.send("Usage: !addsong [number] Title | Artist | YouTube_URL OR !addurl [youtube_url] (easier)")
            return
        
        # Check if first argument is a YouTube URL - redirect to addurl functionality
        if self.manager.is_youtube_url(number_or_url):
            await ctx.send("💡 Detected YouTube URL! Using quick add feature...")
            # Call the addurl functionality directly
            return await self.add_song_from_url(ctx, number_or_url)
        
        # Try to convert to number for traditional addsong functionality
        try:
            number = int(number_or_url)
        except ValueError:
            await ctx.send("❌ First argument must be a number or YouTube URL. Use `!addurl [url]` for quick add.")
            return
        
        if not song_details:
            await ctx.send("Usage: !addsong [number] Title | Artist | YouTube_URL")
            return
        
        # Parse song details
        parts = [part.strip() for part in song_details.split('|')]
        if len(parts) < 2:
            await ctx.send("❌ Format: Title | Artist | YouTube_URL (URL optional)")
            return
        
        title = parts[0]
        artist = parts[1]
        youtube_url = parts[2] if len(parts) > 2 and parts[2] else None
        
        # Determine number (use provided number or assign next available)
        if number is None:
            existing_numbers = [song['number'] for song in self.manager.playlist_cache]
            number = max(existing_numbers) + 1 if existing_numbers else 1
        
        # Create song entry
        new_song = {
            "number": number,
            "title": title,
            "artist": artist,
            "youtube_url": youtube_url,
            "duration": None,
            "verified": False
        }
        
        # Update or add to playlist
        found = False
        for i, song in enumerate(self.manager.playlist_cache):
            if song['number'] == number:
                self.manager.playlist_cache[i] = new_song
                found = True
                break
        
        if not found:
            self.manager.playlist_cache.append(new_song)
            # Sort by number
            self.manager.playlist_cache.sort(key=lambda x: x['number'])
        
        # Save to file
        try:
            with open(PLAYLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.manager.playlist_cache, f, indent=2, ensure_ascii=False)
            
            youtube_indicator = "🎬" if youtube_url else "🎵"
            action = "Updated" if found else "Added"
            await ctx.send(f"✅ {action} #{number}: {title} by {artist} {youtube_indicator}")
            
        except Exception as e:
            await ctx.send(f"❌ Error saving playlist: {e}")

    async def music_control_handler(self, ctx, action: str = None):
        """Music playbook control (Mod only). Actions: start, stop, pause, resume, next, status"""
        print(f"EMERGENCY DEBUG: music_control_handler entry point with action: {action}")
        try:
            print(f"EMERGENCY DEBUG: About to log in music_control_handler")
            self.logger.info(f"music_control_handler called with action: {action} by {ctx.author.name}")
            print(f"EMERGENCY DEBUG: Logger succeeded in music_control_handler")
            
            print(f"EMERGENCY DEBUG: About to check is_mod")
            if not ctx.author.is_mod:
                print(f"EMERGENCY DEBUG: User is not mod, sending error")
                await ctx.send("❌ Only mods can control music playback.")
                return

            print(f"EMERGENCY DEBUG: User is mod, continuing")
            
            # Allow music playback during caching (only block new song requests/queue operations)
            # Caching runs in parallel with music playback from already cached songs
            if self.manager.is_caching and action in ['request', 'queue', 'add']:
                await ctx.send("⏳ Cache operation in progress. New song requests disabled until caching completes.")
                return
            
            if not action:
                print(f"EMERGENCY DEBUG: No action provided, getting status")
                status = self.manager.get_playback_status()
                await ctx.send(f"🎵 Music Control - {status}. Use: !music [start|stop|pause|resume|next|status]")
                return

            print(f"EMERGENCY DEBUG: Action provided: {action}")
            action = action.lower()
            print(f"EMERGENCY DEBUG: Action lowercased: {action}")
            print(f"EMERGENCY DEBUG: About to log processing music action")
            self.logger.info(f"Processing music action: {action}")
            print(f"EMERGENCY DEBUG: Successfully logged processing music action")
            
        except Exception as e:
            self.logger.error(f"Error in music_control_handler initialization: {e}", exc_info=True)
            await ctx.send(f"❌ Music control error: {e}")
            return

        if action == "start":
            try:
                # Use lock to prevent race conditions with auto-play
                async with self.manager.playback_lock:
                    # Enable music and clear old state
                    self.manager.music_enabled = True
                    self.manager.is_playing = False
                    
                    # Process queue first (includes quarter-based songs), then fallback to random
                    result = await self.manager.process_queue(ctx.channel)
                    if not result:
                        # No queue items, fallback to random cached file
                        result = await self.manager.simple_play_cached_file(ctx.channel)
                
                if result:
                    try:
                        song_info, username = result
                        self.logger.info(f"MUSIC START: Playing song: {song_info.get('title', 'Unknown')}")
                        
                        # Music started message already sent by simple_play_cached_file
                        self.logger.info("MUSIC START: Success message sent")
                        
                        # Start background auto-play task
                        try:
                            self.logger.info("MUSIC START: Starting auto-play task...")
                            if not hasattr(self, 'auto_play_task') or (hasattr(self, 'auto_play_task') and self.auto_play_task.done()):
                                self.auto_play_task = asyncio.create_task(self._auto_play_loop())
                                self.logger.info("MUSIC START: Auto-play task created successfully")
                            else:
                                self.logger.info("MUSIC START: Auto-play task already running")
                        except Exception as auto_error:
                            self.logger.error(f"MUSIC START: Error starting auto-play task: {auto_error}", exc_info=True)
                            await ctx.send(f"⚠️ Music started but auto-play disabled: {auto_error}")
                    except Exception as result_error:
                        self.logger.error(f"MUSIC START: Error processing result: {result_error}", exc_info=True)
                        await ctx.send(f"❌ Music started but error in result processing: {result_error}")
                else:
                    self.logger.warning("MUSIC START: No result from simple_play_cached_file")
                    await ctx.send("❌ Failed to start music playback. Check logs for details or try again.")
                
                self.logger.info("MUSIC START: Command completed successfully")
                    
            except Exception as e:
                self.logger.error(f"MUSIC START: Top-level error in music start command: {e}", exc_info=True)
                try:
                    await ctx.send(f"❌ Critical error starting music: {str(e)[:100]}")
                except Exception as send_error:
                    self.logger.error(f"MUSIC START: Error sending error message: {send_error}")
                # Don't re-raise, let the command handler continue

        elif action == "stop":
            self.manager.music_enabled = False
            await self.manager.stop_music()
            # Cancel auto-play task
            if hasattr(self, 'auto_play_task'):
                try:
                    if not self.auto_play_task.done():
                        self.auto_play_task.cancel()
                except Exception as task_error:
                    self.logger.warning(f"Error canceling auto-play task: {task_error}")
            await ctx.send("⏹️ Music stopped.")

        elif action == "pause":
            if self.manager.is_playing and not self.manager.is_paused:
                self.manager.pause_music()
                await ctx.send("⏸️ Music paused.")
            else:
                await ctx.send("❌ No music currently playing to pause.")

        elif action == "resume":
            if self.manager.is_paused:
                self.manager.resume_music()
                await ctx.send("▶️ Music resumed.")
            else:
                await ctx.send("❌ No paused music to resume.")

        elif action == "next":
            await ctx.send("⏭️ Skipping to next song...")
            
            try:
                # Use lock to prevent race conditions with auto-play
                async with self.manager.playback_lock:
                    # Stop current music first
                    await self.manager.stop_music()
                    
                    # Check if there are songs in queue first
                    if self.manager.current_queue:
                        self.logger.info(f"Playing next song from queue ({len(self.manager.current_queue)} songs queued)")
                        song_info, username, timestamp = self.manager.current_queue.pop(0)
                        
                        # Sync queue to sheets after removing song
                        self.manager._sync_queue_to_sheets()
                        
                        success = await self.manager.play_song(song_info, username, ctx.channel)
                        if success:
                            if song_info.get('artist') and song_info['artist'] != "Unknown Artist":
                                await ctx.send(f"⏭️ Now playing: {song_info['title']} by {song_info['artist']} (requested by {username})")
                            else:
                                await ctx.send(f"⏭️ Now playing: {song_info['title']} (requested by {username})")
                            return
                        else:
                            await ctx.send(f"❌ Failed to play queued song: {song_info['title']}")
                    
                    # If no queue or queue song failed, play random cached file
                    self.logger.info("No queue or queue failed, playing random cached file")
                result = await self.manager.simple_play_cached_file(ctx.channel)
                if not result:
                    await ctx.send("❌ No songs available")
                    
            except Exception as e:
                self.logger.error(f"Error in next action: {e}", exc_info=True)
                await ctx.send(f"❌ Error playing next song: {e}")

        elif action == "status":
            status = self.manager.get_playback_status()
            queue_size = len(self.manager.current_queue)
            
            current_info = ""
            if self.manager.current_song_info:
                song_info, username = self.manager.current_song_info
                current_info = f"\nNow: {song_info['title']} (by {username})"
            
            await ctx.send(f"🎵 {status} | Queue: {queue_size} songs{current_info}")

        else:
            await ctx.send("❌ Invalid action. Use: start, stop, pause, resume, next, or status")

    @commands.command(name="volume")
    async def set_volume(self, ctx, level: int = None):
        """Set music volume 0-100 (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can control volume.")
            return

        if level is None:
            current = int(self.manager.master_volume * 100)
            await ctx.send(f"🔊 Current volume: {current}%. Use !volume [0-100] to change.")
            return

        if not 0 <= level <= 100:
            await ctx.send("❌ Volume must be between 0-100.")
            return

        self.manager.set_volume(level / 100.0)
        await ctx.send(f"🔊 Volume set to {level}%.")

    @commands.command(name="normalize")
    async def toggle_normalize(self, ctx):
        """Toggle volume normalization (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can toggle normalization.")
            return

        self.manager.normalize_volume = not self.manager.normalize_volume
        status = "enabled" if self.manager.normalize_volume else "disabled"
        await ctx.send(f"🎚️ Volume normalization {status}. (Affects new downloads)")

    @commands.command(name="volumes")
    async def volumes_status(self, ctx):
        """Show both music and SFX volume levels. Mod-only."""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can check volume levels.")
            return
        
        music_vol = int(self.manager.master_volume * 100)
        
        # Try to get SFX volume from the media overlay module
        try:
            from bot.commands.media_overlay import SFX_VOLUME
            sfx_vol = int(SFX_VOLUME * 100)
            await ctx.send(f"🎵 Music: {music_vol}% | 🔊 SFX: {sfx_vol}% | Use !volume or !sfxvolume to adjust")
        except ImportError:
            await ctx.send(f"🎵 Music: {music_vol}% | 🔊 SFX: Unknown | Use !volume to adjust music")

    @commands.command(name="music")
    async def music_command(self, ctx, action: str = None, parameter: str = None):
        """Music commands. Usage: !music [start|stop|next|fix|test] [number]"""
        print(f"EMERGENCY DEBUG: Music command entry point reached with action: {action}")
        try:
            self.logger.info(f"EMERGENCY DEBUG: Music command called by {ctx.author.name} with action: {action}, parameter: {parameter}")
            print(f"EMERGENCY DEBUG: Logger call succeeded")
            
            if action == "fix":
                # Convert parameter to int for fix command
                try:
                    song_number = int(parameter) if parameter else None
                    await self.fix_broken_song(ctx, song_number)
                except ValueError:
                    await ctx.send("❌ Invalid song number for fix command")
            elif action == "test":
                # Convert parameter to int for test command  
                try:
                    song_number = int(parameter) if parameter else None
                    await self.test_song_url(ctx, song_number)
                except ValueError:
                    await ctx.send("❌ Invalid song number for test command")
            else:
                # This is the main music control - delegate to the control method
                self.logger.info(f"Delegating to music_control_handler with action: {action}")
                await self.music_control_handler(ctx, action)
                
        except Exception as e:
            self.logger.error(f"CRITICAL ERROR in music_command: {e}", exc_info=True)
            await ctx.send(f"❌ Critical music error: {str(e)[:200]}")
            # Try to recover
            try:
                self.manager.music_enabled = False
                self.manager.is_playing = False
                self.logger.info("Attempted recovery by disabling music system")
            except Exception as recovery_error:
                self.logger.error(f"Recovery attempt failed: {recovery_error}")

    async def fix_broken_song(self, ctx, song_number: int = None):
        """Auto-fix broken YouTube URLs in playlist (Mod only). Usage: !music fix [song_number]"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can fix playlist songs.")
            return

        if song_number is None:
            await ctx.send("🔧 Usage: !music fix [song_number] - Fix a specific broken song URL")
            return

        try:
            # Find the song in the playlist
            target_song = None
            for song in self.manager.playlist_cache:
                if song.get('number') == song_number:
                    target_song = song
                    break
            
            if not target_song:
                await ctx.send(f"❌ Song #{song_number} not found in playlist.")
                return

            title = target_song.get('title', '')
            artist = target_song.get('artist', '')
            current_url = target_song.get('youtube_url', '')
            
            await ctx.send(f"🔧 Attempting to fix: #{song_number} - {title} by {artist}")
            
            # Try to find a working YouTube URL
            if YT_DLP_AVAILABLE:
                search_query = f"{artist} {title}".strip()
                
                # Use yt-dlp to search for the song
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    try:
                        # Search YouTube for the song
                        search_results = ydl.extract_info(
                            f"ytsearch3:{search_query}",
                            download=False
                        )
                        
                        if search_results and 'entries' in search_results:
                            # Try each result until we find a working one
                            for entry in search_results['entries']:
                                video_id = entry.get('id')
                                video_title = entry.get('title', '')
                                new_url = f"https://www.youtube.com/watch?v={video_id}"
                                
                                # Test if this URL works
                                test_ydl_opts = {
                                    'quiet': True,
                                    'no_warnings': True,
                                }
                                
                                try:
                                    with yt_dlp.YoutubeDL(test_ydl_opts) as test_ydl:
                                        test_ydl.extract_info(new_url, download=False)
                                    
                                    # If we get here, the URL works!
                                    target_song['youtube_url'] = new_url
                                    target_song['verified'] = True
                                    
                                    # Save the updated playlist
                                    import json
                                    with open(PLAYLIST_CACHE_FILE, 'w', encoding='utf-8') as f:
                                        json.dump(self.manager.playlist_cache, f, indent=2, ensure_ascii=False)
                                    
                                    await ctx.send(f"✅ Fixed! #{song_number}: {title} by {artist}")
                                    await ctx.send(f"🔗 New URL: {new_url}")
                                    await ctx.send(f"📺 Video: {video_title}")
                                    return
                                    
                                except Exception as e:
                                    # This URL doesn't work, try the next one
                                    continue
                            
                            await ctx.send(f"❌ Could not find a working replacement for #{song_number}")
                        else:
                            await ctx.send(f"❌ No search results found for: {search_query}")
                            
                    except Exception as e:
                        await ctx.send(f"❌ Search failed: {str(e)}")
                        
            else:
                await ctx.send("❌ Auto-fix requires yt-dlp to be installed.")
                
        except Exception as e:
            await ctx.send(f"❌ Fix failed: {str(e)}")

    async def test_song_url(self, ctx, song_number: int = None):
        """Test if a song URL works (Mod only). Usage: !music test [song_number]"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can test song URLs.")
            return

        if song_number is None:
            await ctx.send("🧪 Usage: !music test [song_number] - Test if a song URL works")
            return

        try:
            # Find the song in the playlist
            target_song = None
            for song in self.manager.playlist_cache:
                if song.get('number') == song_number:
                    target_song = song
                    break
            
            if not target_song:
                await ctx.send(f"❌ Song #{song_number} not found in playlist.")
                return

            title = target_song.get('title', '')
            artist = target_song.get('artist', '')
            youtube_url = target_song.get('youtube_url', '')
            
            await ctx.send(f"🧪 Testing: #{song_number} - {title} by {artist}")
            
            if YT_DLP_AVAILABLE and youtube_url:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                }
                
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(youtube_url, download=False)
                        
                    if info:
                        duration = info.get('duration', 0)
                        uploader = info.get('uploader', 'Unknown')
                        await ctx.send(f"✅ URL works! Duration: {duration}s, Uploader: {uploader}")
                    else:
                        await ctx.send(f"⚠️ URL accessible but no info extracted")
                        
                except Exception as e:
                    await ctx.send(f"❌ URL broken: {str(e)}")
                    await ctx.send(f"💡 Use !music fix {song_number} to auto-repair")
            else:
                await ctx.send("❌ No URL to test or yt-dlp not available.")
                
        except Exception as e:
            await ctx.send(f"❌ Test failed: {str(e)}")

    @commands.command(name="playstats")
    async def show_play_stats(self, ctx):
        """Show playlist play statistics"""
        try:
            # Calculate play count statistics
            play_counts = [song.get('play_count', 0) for song in self.manager.playlist_cache]
            
            if not play_counts:
                await ctx.send("📊 No playlist data available.")
                return
            
            total_songs = len(play_counts)
            total_plays = sum(play_counts)
            min_plays = min(play_counts)
            max_plays = max(play_counts)
            avg_plays = total_plays / total_songs if total_songs > 0 else 0
            
            # Find most and least played songs
            most_played = [song for song in self.manager.playlist_cache 
                          if song.get('play_count', 0) == max_plays]
            least_played_count = len([song for song in self.manager.playlist_cache 
                                    if song.get('play_count', 0) == min_plays])
            
            stats_text = f"📊 **Playlist Statistics:**\n"
            stats_text += f"🎵 Total Songs: {total_songs}\n"
            stats_text += f"▶️ Total Plays: {total_plays}\n"
            stats_text += f"📈 Average: {avg_plays:.1f} plays per song\n"
            stats_text += f"🔥 Most Played: {max_plays} plays\n"
            stats_text += f"🆕 Least Played: {min_plays} plays ({least_played_count} songs)\n"
            
            if most_played:
                top_song = most_played[0]
                stats_text += f"🏆 Top Song: {top_song['title']} by {top_song['artist']} ({max_plays} plays)"
            
            await ctx.send(stats_text)
            
        except Exception as e:
            await ctx.send(f"❌ Error getting play stats: {str(e)}")

    @commands.command(name="playlist", aliases=["catalog", "songs", "list"])
    async def show_playlist_link(self, ctx):
        """Show link to the Google Sheets playlist"""
        try:
            import os
            spreadsheet_id = os.getenv('PLAYLIST_SPREADSHEET_ID')
            
            if not spreadsheet_id:
                await ctx.send("❌ Playlist spreadsheet not configured. Ask the streamer to set PLAYLIST_SPREADSHEET_ID.")
                return
            
            # Build Google Sheets URL
            sheets_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid=0"
            
            # Get basic playlist info
            total_songs = len(self.manager.playlist_cache)
            
            await ctx.send(f"🎵 **Song Catalog:** {sheets_url} | {total_songs} songs available | Use `!srx [number]` to request!")
            
        except Exception as e:
            await ctx.send(f"❌ Error getting playlist link: {str(e)}")

    async def _auto_play_loop(self):
        """Background task to automatically play next song when current one finishes"""
        try:
            self.logger.info("AUTO-PLAY: Starting auto-play loop")
            while self.manager.music_enabled:
                if not self.manager.is_playing and not self.manager.is_paused:
                    # Music stopped, play next song (but wait a moment to avoid conflicts)
                    await asyncio.sleep(1)  # Brief delay to avoid racing with manual commands
                    
                    # Use lock to prevent race conditions with manual commands
                    try:
                        async with self.manager.playback_lock:
                            # Double-check we're still stopped after acquiring the lock
                            if not self.manager.is_playing and not self.manager.is_paused and self.manager.music_enabled:
                                # Process queue first (includes quarter-based songs), then fallback to playlist
                                try:
                                    result = await self.manager.process_queue(self.chat_channel)
                                    if result:
                                        song_info, username = result
                                        self.logger.info(f"Auto-playing: {song_info['title']} by {song_info.get('artist', 'Unknown')} (requested by {username})")
                                    else:
                                        # No songs in queue, play random cached file as fallback
                                        result = await self.manager.simple_play_cached_file(self.chat_channel)
                                        if result:
                                            song_info, username = result
                                            self.logger.info(f"Auto-playing random: {song_info['title']} by {song_info.get('artist', 'Unknown')}")
                                        else:
                                            # No songs available at all, wait a bit
                                            await asyncio.sleep(10)
                                except Exception as e:
                                    self.logger.error(f"Error in auto-play: {e}")
                                    await asyncio.sleep(10)
                    except Exception as lock_error:
                        self.logger.error(f"Error acquiring auto-play lock: {lock_error}")
                        await asyncio.sleep(5)
                
                elif self.manager.is_playing and self.manager.song_start_time and self.manager.song_duration:
                    # Check if song should be finished based on duration
                    import time
                    elapsed = time.time() - self.manager.song_start_time
                    if elapsed >= self.manager.song_duration:
                        # Song finished by duration - use lock to prevent race conditions
                        try:
                            async with self.manager.playback_lock:
                                # Double-check the song is still marked as playing (in case manual command already handled it)
                                if self.manager.is_playing:
                                    self.logger.info(f"Song duration exceeded ({elapsed:.1f}s >= {self.manager.song_duration}s), stopping music")
                                    await self.manager.stop_music()
                                    # The next iteration will start a new song
                        except Exception as duration_error:
                            self.logger.error(f"Error handling song duration completion: {duration_error}")
                        continue  # Will trigger next song on next loop
                    
                    # Song still playing, check again in a few seconds
                    remaining = self.manager.song_duration - elapsed
                    check_interval = min(5, max(1, remaining - 5))  # Check more frequently near the end
                    await asyncio.sleep(check_interval)
                else:
                    # Default wait
                    await asyncio.sleep(3)
                    
        except asyncio.CancelledError:
            self.logger.info("Auto-play loop cancelled")
        except Exception as e:
            self.logger.error(f"Auto-play loop error: {e}")

def prepare(bot):
    bot.add_cog(SongRequestCog(bot))