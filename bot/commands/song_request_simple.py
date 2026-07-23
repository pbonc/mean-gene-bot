import os
import json
import logging
import asyncio
import difflib
from collections import deque
from twitchio.ext import commands
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

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
LOCAL_SRX_FOLDER = os.path.join(DATA_DIR, "srx_local")
COOKIES_FILE = os.path.join(PROJECT_ROOT, "cookies.txt")

def get_ydl_opts(output_template=None, download=True, quiet=True, use_android_client=False):
    """
    Get standardized yt-dlp options with cookie support to prevent 403 errors.
    
    Args:
        output_template: Output file path template
        download: Whether to download or just extract info
        quiet: Whether to suppress yt-dlp output
        use_android_client: Use Android client (bypasses some restrictions but doesn't support cookies)
    
    Returns:
        dict: yt-dlp options dictionary
    """
    opts = {
        'quiet': quiet,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-us,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        },
    }
    
    # Android client bypasses signature challenges but doesn't support cookies
    if use_android_client:
        opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android'],
                'player_skip': ['configs'],
            }
        }
        logging.getLogger(__name__).info("Using Android client (no cookies, bypasses signature challenges)")
    else:
        # Web client with cookies for normal operation
        if os.path.exists(COOKIES_FILE):
            opts['cookiefile'] = COOKIES_FILE
            logging.getLogger(__name__).debug(f"Using cookies from {COOKIES_FILE}")
    
    if not download:
        opts['no_download'] = True
    
    if output_template:
        # Remove .mp3 extension from output template since FFmpeg postprocessor will add it
        if output_template.endswith('.mp3'):
            output_template_base = output_template[:-4]
        else:
            output_template_base = output_template
        opts['outtmpl'] = output_template_base
        
        # Get FFmpeg location from imageio-ffmpeg or fallback to system
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            # Fallback to common paths
            ffmpeg_exe = r'C:\ffmpeg\bin\ffmpeg.exe'
        opts['ffmpeg_location'] = ffmpeg_exe
        opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        # Use bestaudio format instead of 'best' to avoid issues with restricted videos
        opts['format'] = 'bestaudio/best'
    
    return opts

class DownloadQueue:
    """Serialized download queue to prevent concurrent YouTube requests and 403 errors"""
    
    # Priority levels
    PRIORITY_URGENT = 0   # Currently playing song
    PRIORITY_HIGH = 1     # Songs in user queue
    PRIORITY_NORMAL = 2   # Next random song
    PRIORITY_LOW = 3      # Background pre-cache
    
    def __init__(self, logger):
        self.logger = logger
        self.queue = []  # [(priority, timestamp, song_info, callback, error_callback)]
        self.worker_task = None
        self.downloading = None  # Current download in progress
        self.is_running = False
        self.download_lock = asyncio.Lock()
        self.stats = {
            'total_queued': 0,
            'total_completed': 0,
            'total_failed': 0,
            'total_skipped': 0
        }
    
    def start_worker(self):
        """Start the download worker task"""
        if not self.worker_task or self.worker_task.done():
            self.is_running = True
            self.worker_task = asyncio.create_task(self._worker_loop())
            self.logger.info("📥 Download queue worker started")
    
    def stop_worker(self):
        """Stop the download worker task"""
        self.is_running = False
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            self.logger.info("🛑 Download queue worker stopped")
    
    def add(self, song_info: dict, priority: int, callback=None, error_callback=None):
        """Add a download to the queue"""
        import time
        
        # Check if already in queue or downloading
        youtube_url = song_info.get('youtube_url')
        if not youtube_url:
            return False
        
        # Check if already queued
        for _, _, queued_song, _, _ in self.queue:
            if queued_song.get('youtube_url') == youtube_url:
                self.logger.debug(f"Song already in download queue: {song_info.get('title', 'Unknown')}")
                return False
        
        # Check if currently downloading
        if self.downloading and self.downloading.get('youtube_url') == youtube_url:
            self.logger.debug(f"Song already downloading: {song_info.get('title', 'Unknown')}")
            return False
        
        # Add to queue
        timestamp = time.time()
        self.queue.append((priority, timestamp, song_info, callback, error_callback))
        self.queue.sort(key=lambda x: (x[0], x[1]))  # Sort by priority, then timestamp
        self.stats['total_queued'] += 1
        
        priority_name = ['URGENT', 'HIGH', 'NORMAL', 'LOW'][priority] if priority < 4 else 'UNKNOWN'
        self.logger.info(f"📥 Added to download queue [{priority_name}]: {song_info.get('title', 'Unknown')} (queue size: {len(self.queue)})")
        return True
    
    def get_status(self) -> dict:
        """Get current download queue status"""
        return {
            'queue_size': len(self.queue),
            'downloading': self.downloading.get('title', 'None') if self.downloading else None,
            'is_running': self.is_running,
            'stats': self.stats.copy()
        }
    
    async def _worker_loop(self):
        """Main worker loop - processes downloads one at a time"""
        self.logger.info("🔄 Download worker loop started")
        
        while self.is_running:
            try:
                if self.queue:
                    priority, timestamp, song_info, callback, error_callback = self.queue.pop(0)
                    self.downloading = song_info
                    
                    priority_name = ['URGENT', 'HIGH', 'NORMAL', 'LOW'][priority] if priority < 4 else 'UNKNOWN'
                    self.logger.info(f"⬇️ Downloading [{priority_name}]: {song_info.get('title', 'Unknown')} ({len(self.queue)} remaining)")
                    
                    try:
                        # Perform the actual download
                        success = await self._download_song(song_info)
                        
                        if success:
                            self.stats['total_completed'] += 1
                            self.logger.info(f"✅ Download complete: {song_info.get('title', 'Unknown')}")
                            if callback:
                                try:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback(song_info, success=True)
                                    else:
                                        callback(song_info, success=True)
                                except Exception as cb_err:
                                    self.logger.error(f"Callback error: {cb_err}")
                        else:
                            self.stats['total_failed'] += 1
                            self.logger.warning(f"❌ Download failed: {song_info.get('title', 'Unknown')}")
                            if error_callback:
                                try:
                                    if asyncio.iscoroutinefunction(error_callback):
                                        await error_callback(song_info, error="Download failed")
                                    else:
                                        error_callback(song_info, error="Download failed")
                                except Exception as cb_err:
                                    self.logger.error(f"Error callback error: {cb_err}")
                        
                        self.downloading = None
                        
                        # Rate limit: 5 second delay between downloads
                        await asyncio.sleep(5)
                        
                    except Exception as e:
                        self.stats['total_failed'] += 1
                        self.logger.error(f"❌ Download error for {song_info.get('title', 'Unknown')}: {e}")
                        self.downloading = None
                        if error_callback:
                            try:
                                if asyncio.iscoroutinefunction(error_callback):
                                    await error_callback(song_info, error=str(e))
                                else:
                                    error_callback(song_info, error=str(e))
                            except Exception as cb_err:
                                self.logger.error(f"Error callback error: {cb_err}")
                        await asyncio.sleep(5)
                else:
                    # Queue empty, wait a bit
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                self.logger.info("Download worker cancelled")
                break
            except Exception as e:
                self.logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)
        
        self.logger.info("🛑 Download worker loop stopped")
    
    async def _download_song(self, song_info: dict) -> bool:
        """Download a single song - to be implemented by SimpleSongManager"""
        # This will be set by SimpleSongManager
        if hasattr(self, '_download_func'):
            return await self._download_func(song_info)
        return False

class SimpleSongManager:
    """Song manager with playback controls and volume normalization"""
    
    # Class-level variables for global 403 rate limiting
    _last_403_time = None
    _403_cooldown_until = None
    _consecutive_403_count = 0
    _youtube_download_lock = asyncio.Lock()
    _youtube_url_cooldowns = {}  # {youtube_url: cooldown_until_ts}
    
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
        from bot.main import audio_manager
        self.audio_manager = audio_manager
        
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

        # Download behavior
        self.enable_preflight_check = False  # Disabled to reduce extra yt-dlp calls
        self.prefer_android_client = True  # Use Android client as primary download path
        
        # Audio synchronization - use asyncio.Lock for async compatibility
        self._audio_lock = asyncio.Lock()
        
        # Song cooldown system (20 minutes)
        self.song_cooldowns = {}  # {song_number: last_played_timestamp}
        self.cooldown_minutes = 20

        # High-variety autoplay controls (auto mode only)
        self.autoplay_recent_max = 60
        self.autoplay_artist_spacing = 4
        self.autoplay_recent_ids = deque(maxlen=self.autoplay_recent_max)
        self.autoplay_recent_artists = deque(maxlen=max(20, self.autoplay_artist_spacing * 5))
        self.autoplay_shuffle_bag = []
        self.autoplay_state_file = os.path.join(DATA_DIR, "autoplay_state.json")
        self._load_autoplay_state()
        
        # Download Queue System (replaces concurrent pre-cache tasks)
        self.download_queue = DownloadQueue(self.logger)
        self.download_queue._download_func = self._queue_download_song  # Bind download function
        self.download_queue.start_worker()
        
        # Legacy cache tracking (for compatibility)
        self.pre_cache_tasks = {}  # Deprecated - now using download_queue
        self.next_random_cached = None  # Pre-cached random song for smooth transitions

        # Fallback cached playback tracking (avoid repeats + fix display info)
        self.last_fallback_audio_file = None
        self.last_fallback_song_info = None
        
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

    def _get_song_artist_key(self, song_info: Optional[Dict]) -> Optional[str]:
        """Build a normalized artist token for spacing in autoplay mode."""
        if not isinstance(song_info, dict):
            return None
        artist = (song_info.get('artist') or '').strip().lower()
        return artist or None

    def _load_autoplay_state(self):
        """Load persisted autoplay history/cooldowns to preserve variety across restarts."""
        try:
            if not os.path.exists(self.autoplay_state_file):
                return

            with open(self.autoplay_state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            recent_ids = data.get('recent_ids', [])
            if isinstance(recent_ids, list):
                cleaned_ids = [str(x) for x in recent_ids if x]
                self.autoplay_recent_ids = deque(cleaned_ids[-self.autoplay_recent_max:], maxlen=self.autoplay_recent_max)

            recent_artists = data.get('recent_artists', [])
            if isinstance(recent_artists, list):
                cleaned_artists = [str(x).strip().lower() for x in recent_artists if str(x).strip()]
                max_artists = max(20, self.autoplay_artist_spacing * 5)
                self.autoplay_recent_artists = deque(cleaned_artists[-max_artists:], maxlen=max_artists)

            cooldowns_raw = data.get('song_cooldowns', {})
            now = datetime.now()
            rebuilt_cooldowns = {}
            if isinstance(cooldowns_raw, dict):
                for song_num, dt_str in cooldowns_raw.items():
                    try:
                        ts = datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
                        if ts.tzinfo is not None:
                            ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
                        if ts + timedelta(minutes=self.cooldown_minutes) > now:
                            rebuilt_cooldowns[int(song_num)] = ts
                    except Exception:
                        continue
            self.song_cooldowns = rebuilt_cooldowns

            bag = data.get('shuffle_bag', [])
            if isinstance(bag, list):
                self.autoplay_shuffle_bag = [str(x) for x in bag if x]

            self.logger.info(
                f"Loaded autoplay state: recent={len(self.autoplay_recent_ids)}, "
                f"artist_recent={len(self.autoplay_recent_artists)}, cooldowns={len(self.song_cooldowns)}, "
                f"bag={len(self.autoplay_shuffle_bag)}"
            )
        except Exception as e:
            self.logger.error(f"Failed to load autoplay state: {e}")

    def _save_autoplay_state(self):
        """Persist autoplay state asynchronously to keep stream behavior stable across restarts."""
        try:
            asyncio.create_task(self._save_autoplay_state_async())
        except Exception:
            pass

    async def _save_autoplay_state_async(self):
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._save_autoplay_state_sync)
        except Exception as e:
            self.logger.error(f"Failed to save autoplay state async: {e}")

    def _save_autoplay_state_sync(self):
        try:
            payload = {
                'recent_ids': list(self.autoplay_recent_ids),
                'recent_artists': list(self.autoplay_recent_artists),
                'song_cooldowns': {str(num): ts.isoformat() for num, ts in self.song_cooldowns.items()},
                'shuffle_bag': list(self.autoplay_shuffle_bag),
            }
            with open(self.autoplay_state_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to save autoplay state sync: {e}")

    def _rebuild_autoplay_shuffle_bag(self):
        """Rebuild shuffled autoplay candidates for high-variety playback."""
        import random

        song_ids = []
        for song in self.playlist_cache:
            song_id = self._get_song_identity(song)
            if song_id:
                song_ids.append(song_id)

        random.shuffle(song_ids)
        self.autoplay_shuffle_bag = song_ids
        self._save_autoplay_state()
        self.logger.info(f"Rebuilt autoplay shuffle bag with {len(song_ids)} songs")

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

    async def _async_sync_queue_to_sheets(self):
        """Async wrapper for queue sync to prevent blocking playback transitions"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._sync_queue_to_sheets)
        except Exception as e:
            self.logger.error(f"Failed to async sync queue: {e}")

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
                    'artist': song['artist'],
                    'number': song.get('number', '?'),
                    'duration': song.get('duration'),
                    'youtube_url': song.get('youtube_url')
                }
            
            # Also check if it matches "Artist - Title" pattern
            combined = f"{song_artist} - {song_title}".lower()
            if combined in clean_name.lower() or clean_name.lower() in combined:
                return {
                    'title': song['title'], 
                    'artist': song['artist'],
                    'number': song.get('number', '?'),
                    'duration': song.get('duration'),
                    'youtube_url': song.get('youtube_url')
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

    def normalize_audio_file(self, audio_file: str) -> bool:
        """Normalize audio file using FFmpeg loudnorm filter to -16 LUFS"""
        import subprocess
        import os
        
        if not os.path.exists(audio_file):
            self.logger.error(f"Audio file not found for normalization: {audio_file}")
            return False
        
        try:
            # Get file extension
            file_ext = os.path.splitext(audio_file)[1].lower()
            if file_ext not in ['.mp3', '.m4a', '.webm', '.mp4', '.opus', '.ogg']:
                self.logger.warning(f"Unsupported audio format for normalization: {file_ext}")
                return False
            
            # Create temporary output file
            base_name = os.path.splitext(audio_file)[0]
            temp_output = base_name + '.normalized.mp3'
            
            # FFmpeg loudnorm filter: normalize to -16 LUFS (broadcast standard)
            # loudnorm parameters:
            # I (integrated loudness target): -16 LUFS
            # TP (true peak limit): -1.0 dB
            # LRA (loudness range): 11.0 dB
            ffmpeg_cmd = [
                r'C:\ffmpeg\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe',
                '-i', audio_file,
                '-af', 'loudnorm=I=-16:TP=-1.0:LRA=11.0',
                '-q:a', '0',  # Highest quality MP3 encoding
                '-y',  # Overwrite output file
                temp_output
            ]
            
            self.logger.info(f"Normalizing audio: {audio_file}")
            
            # Run FFmpeg synchronously (subprocess is blocking)
            result = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 and os.path.exists(temp_output):
                # Replace original with normalized version
                os.replace(temp_output, audio_file)
                self.logger.info(f"✅ Normalized: {audio_file}")
                return True
            else:
                if os.path.exists(temp_output):
                    os.remove(temp_output)
                self.logger.error(f"FFmpeg normalization failed for: {audio_file}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error normalizing audio file {audio_file}: {e}")
            return False

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
    
    def record_403_error(self):
        """Record a 403 error and activate cooldown if needed"""
        import time
        now = time.time()
        
        SimpleSongManager._consecutive_403_count += 1
        SimpleSongManager._last_403_time = now
        
        # Exponential cooldown based on consecutive 403s
        # 1st: 60s, 2nd: 120s, 3rd: 240s, 4th+: 480s (8 minutes)
        cooldown_duration = min(60 * (2 ** (SimpleSongManager._consecutive_403_count - 1)), 480)
        SimpleSongManager._403_cooldown_until = now + cooldown_duration
        
        self.logger.warning(f"⚠️ YouTube 403 Error #{SimpleSongManager._consecutive_403_count} detected. Cooldown: {cooldown_duration}s")

    def _record_url_cooldown(self, youtube_url: str, cooldown_seconds: int, reason: str):
        """Record a per-URL cooldown to avoid repeated failed attempts"""
        import time
        if not youtube_url:
            return
        cooldown_until = time.time() + cooldown_seconds
        SimpleSongManager._youtube_url_cooldowns[youtube_url] = cooldown_until
        self.logger.warning(f"⏳ URL cooldown ({cooldown_seconds}s) for {youtube_url[:50]} | reason={reason}")

    def _is_url_in_cooldown(self, youtube_url: str) -> tuple[bool, int]:
        """Check if a specific YouTube URL is in cooldown"""
        import time
        if not youtube_url:
            return (False, 0)
        cooldown_until = SimpleSongManager._youtube_url_cooldowns.get(youtube_url)
        if not cooldown_until:
            return (False, 0)
        now = time.time()
        if now < cooldown_until:
            return (True, int(cooldown_until - now))
        # Cooldown expired
        try:
            del SimpleSongManager._youtube_url_cooldowns[youtube_url]
        except KeyError:
            pass
        return (False, 0)

    def _is_403_error(self, error_str: str) -> bool:
        if not error_str:
            return False
        lower = error_str.lower()
        return "403" in lower or "forbidden" in lower or "http error 403" in lower

    async def _preflight_youtube_check(self, youtube_url: str, song_title: str, chat_channel=None) -> bool:
        """Preflight check to avoid repeated 403s and broken links before downloading"""
        if not YT_DLP_AVAILABLE:
            return False

        # Global 403 cooldown
        in_cooldown, remaining = self.is_in_403_cooldown()
        if in_cooldown:
            self.logger.warning(f"Preflight skipped due to global 403 cooldown ({remaining}s): {song_title}")
            return False

        # Per-URL cooldown
        url_in_cooldown, url_remaining = self._is_url_in_cooldown(youtube_url)
        if url_in_cooldown:
            self.logger.warning(f"Preflight skipped due to URL cooldown ({url_remaining}s): {song_title}")
            return False

        # Try to extract info without downloading (fast check)
        try:
            import yt_dlp

            ydl_opts = get_ydl_opts(download=False, quiet=True)
            ydl_opts['socket_timeout'] = 15
            ydl_opts['retries'] = 3
            ydl_opts['fragment_retries'] = 3

            def _extract(opts):
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(youtube_url, download=False)

            loop = asyncio.get_event_loop()
            
            try:
                # First try with cookies
                await asyncio.wait_for(loop.run_in_executor(self.executor, _extract, ydl_opts), timeout=15.0)
                return True
            except Exception as first_error:
                error_str = str(first_error)
                
                # Retry with Android client if format/signature error
                if any(x in error_str for x in [
                    "Requested format is not available",
                    "Signature solving failed",
                    "n challenge solving failed",
                    "Only images are available"
                ]):
                    try:
                        ydl_opts_android = get_ydl_opts(download=False, quiet=True, use_android_client=True)
                        ydl_opts_android['socket_timeout'] = 15
                        ydl_opts_android['retries'] = 3
                        ydl_opts_android['fragment_retries'] = 3
                        await asyncio.wait_for(loop.run_in_executor(self.executor, _extract, ydl_opts_android), timeout=15.0)
                        return True
                    except Exception as android_error:
                        # Android client also failed, treat as original error
                        pass
                
                # Re-raise to be handled below
                raise first_error

        except asyncio.TimeoutError:
            self._record_url_cooldown(youtube_url, 600, "preflight timeout")
        except Exception as e:
            error_str = str(e)
            if self._is_403_error(error_str):
                self.record_403_error()
                self._record_url_cooldown(youtube_url, 3600, "403 preflight")
                if chat_channel:
                    in_cooldown, remaining = self.is_in_403_cooldown()
                    await chat_channel.send(f"⚠️ YouTube rate limit detected. Cooldown active for {remaining}s.")
            else:
                # Temporary cooldown for other failures
                self._record_url_cooldown(youtube_url, 1200, f"preflight error: {error_str[:60]}")
        return False
    
    def is_in_403_cooldown(self) -> tuple[bool, int]:
        """Check if we're in 403 cooldown. Returns (is_cooldown, seconds_remaining)"""
        import time
        if SimpleSongManager._403_cooldown_until is None:
            return (False, 0)
        
        now = time.time()
        if now < SimpleSongManager._403_cooldown_until:
            remaining = int(SimpleSongManager._403_cooldown_until - now)
            return (True, remaining)
        else:
            # Cooldown expired - reset counter if it's been a while
            if SimpleSongManager._last_403_time and (now - SimpleSongManager._last_403_time) > 300:
                SimpleSongManager._consecutive_403_count = 0
            return (False, 0)

    def find_playlist_song(self, number: int) -> Optional[Dict]:
        for song in self.playlist_cache:
            if song['number'] == number:
                return song
        return None

    def search_playlist(self, query: str, limit: int = 5) -> List[Dict]:
        """Return up to `limit` songs that best match the query (title/artist/number)."""
        if not query:
            return []

        needle = query.strip().lower()
        results = []

        for song in self.playlist_cache:
            title = song.get('title', '')
            artist = song.get('artist', '')
            number = str(song.get('number', ''))

            # Exact substring hits get full weight; otherwise fall back to a fuzzy ratio.
            haystack = f"{title} {artist}".lower()
            if needle in haystack or needle in number:
                score = 1.0
            else:
                score = difflib.SequenceMatcher(None, needle, haystack).ratio()

            # Keep only reasonable matches; tweakable threshold.
            if score >= 0.35:
                results.append((score, song))

        results.sort(key=lambda x: x[0], reverse=True)
        return [song for score, song in results[:limit]]

    def is_youtube_url(self, text: str) -> bool:
        """
        Accepts:
        - Full YouTube URLs (youtube.com, youtu.be)
        - Raw YouTube video IDs (11 chars, letters/numbers/_/-)
        """
        if not text:
            return False
        text = text.strip()
        # Check for full URLs
        if 'youtube.com' in text or 'youtu.be' in text:
            return True
        # Check for raw video ID (YouTube video IDs are 11 chars, letters/numbers/_/-)
        import re
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', text):
            return True
        return False

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

    def extract_video_from_playlist_url(self, url: str) -> str:
        """
        Extract individual video URL from playlist links.
        Handles: https://www.youtube.com/watch?v=VIDEO_ID&list=PLAYLIST_ID&index=1
        Returns: https://youtu.be/VIDEO_ID
        """
        import re
        from urllib.parse import urlparse, parse_qs
        
        if not url or 'youtube.com' not in url.lower():
            return url
        
        # Parse the URL
        parsed = urlparse(url)
        
        # Extract video ID from query parameters
        if 'v=' in url or 'watch' in parsed.path:
            params = parse_qs(parsed.query)
            video_id = params.get('v', [None])[0]
            if video_id:
                # Return clean youtu.be URL
                return f"https://youtu.be/{video_id}"
        
        # If no video ID found, return original
        return url

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
        self._save_autoplay_state()

    def get_autoplay_variety_status(self) -> Dict:
        """Return lightweight autoplay variety diagnostics for moderator visibility."""
        now = datetime.now()
        expired = []
        for song_number, last_played in self.song_cooldowns.items():
            if last_played + timedelta(minutes=self.cooldown_minutes) <= now:
                expired.append(song_number)

        for song_number in expired:
            self.song_cooldowns.pop(song_number, None)

        if expired:
            self._save_autoplay_state()

        artist_window = list(self.autoplay_recent_artists)[-self.autoplay_artist_spacing:]
        bag_total = len(self.autoplay_shuffle_bag)
        playlist_total = len(self.playlist_cache)

        return {
            'playlist_total': playlist_total,
            'bag_remaining': bag_total,
            'bag_fill_percent': round((bag_total / playlist_total) * 100, 1) if playlist_total else 0.0,
            'recent_tracks': len(self.autoplay_recent_ids),
            'recent_tracks_max': self.autoplay_recent_max,
            'artist_spacing': self.autoplay_artist_spacing,
            'artist_window': artist_window,
            'active_cooldowns': len(self.song_cooldowns),
        }
    
    async def start_smart_pre_cache(self, song_info, priority=None):
        """Queue a song for download (replaces old concurrent pre-cache system)"""
        try:
            import os
            if not song_info:
                return
            
            # Check if already cached
            cache_file = self._get_cache_filename(song_info)
            if os.path.exists(cache_file):
                self.logger.debug(f"Song already cached: {song_info.get('title', 'Unknown')}")
                return
            
            # Determine priority if not specified
            if priority is None:
                if song_info.get('number'):
                    priority = DownloadQueue.PRIORITY_NORMAL
                else:
                    priority = DownloadQueue.PRIORITY_LOW
            
            # Add to download queue
            self.download_queue.add(song_info, priority)
            
        except Exception as e:
            self.logger.error(f"Error queuing download: {e}")
    
    async def _queue_download_song(self, song_info: dict) -> bool:
        """Download a single song - called by DownloadQueue worker"""
        try:
            import yt_dlp
            import os
            
            # Determine the URL to download
            url = song_info.get('youtube_url')
            if not url:
                self.logger.warning(f"No YouTube URL for song: {song_info}")
                return False
                
            cache_file = self._get_cache_filename(song_info)
            video_id = url.split('v=')[-1].split('&')[0] if 'youtube.com' in url else url
            
            # Skip if already exists
            if os.path.exists(cache_file):
                print(f"[DOWNLOAD] File already cached: {video_id} - {song_info.get('title', 'Unknown')}")
                self.logger.debug(f"Song already cached: {song_info.get('title', 'Unknown')}")
                return True

            # Preflight check removed to simplify downloads
                
            self.logger.info(f"Downloading: {song_info.get('title', 'Unknown')} from {url}")
            
            # Use preferred client first, then fallback
            use_android_first = self.prefer_android_client
            ydl_opts = get_ydl_opts(
                output_template=cache_file,
                download=True,
                quiet=True,
                use_android_client=use_android_first
            )
            ydl_opts_fallback = get_ydl_opts(
                output_template=cache_file,
                download=True,
                quiet=True,
                use_android_client=not use_android_first
            )

            def _download_sync(opts):
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])

            loop = asyncio.get_event_loop()
            
            client_label = "Android" if use_android_first else "Web"
            print(f"[DOWNLOAD] [{video_id}] Attempting {client_label} client for: {song_info.get('title', 'Unknown')}")
            
            try:
                # First attempt with preferred client
                await loop.run_in_executor(self.executor, _download_sync, ydl_opts)
                print(f"[DOWNLOAD] [{video_id}] SUCCESS: {client_label} client succeeded")
            except (Exception, yt_dlp.utils.DownloadError) as first_error:
                error_str = str(first_error)
                
                # If format error or signature error, retry with Android client
                if any(x in error_str for x in [
                    "Requested format is not available",
                    "Signature solving failed",
                    "n challenge solving failed",
                    "Only images are available"
                ]):
                    fallback_label = "Web" if use_android_first else "Android"
                    print(f"[DOWNLOAD] [{video_id}] {client_label} failed, trying {fallback_label} fallback...")
                    self.logger.warning(f"Format/signature error, retrying with {fallback_label} client...")
                    
                    try:
                        await loop.run_in_executor(self.executor, _download_sync, ydl_opts_fallback)
                        print(f"[DOWNLOAD] [{video_id}] SUCCESS: {fallback_label} fallback succeeded")
                        self.logger.info(f"SUCCESS: Fallback {fallback_label} client download succeeded")
                    except Exception as fallback_error:
                        self.logger.error(f"Fallback {fallback_label} also failed: {fallback_error}")
                        raise first_error  # Re-raise original error for logging below
                else:
                    # Not a format error, re-raise
                    raise
            
            # Verify file was created
            if os.path.exists(cache_file):
                print(f"[DOWNLOAD] [{video_id}] File verified")
                self.logger.info(f"Downloaded: {song_info.get('title', 'Unknown')}")
                return True
            else:
                # File not at expected path - check if it exists with a different extension
                base_path = cache_file[:-4] if cache_file.endswith('.mp3') else cache_file
                import glob
                possible_files = glob.glob(f"{base_path}*")
                if possible_files:
                    print(f"[DOWNLOAD] [{video_id}] File found at different path: {possible_files[0]}")
                    # Rename it to expected path
                    try:
                        os.rename(possible_files[0], cache_file)
                        print(f"[DOWNLOAD] [{video_id}] Renamed to: {cache_file}")
                        return True
                    except Exception as rename_error:
                        print(f"[DOWNLOAD] [{video_id}] Failed to rename: {rename_error}")
                        return False
                else:
                    print(f"[DOWNLOAD] [{video_id}] ERROR: File not found. Expected: {cache_file}")
                    print(f"[DOWNLOAD] [{video_id}] Searched for: {base_path}*")
                    self.logger.error(f"Download failed (file not found): {song_info.get('title', 'Unknown')}")
                    return False
            
        except Exception as e:
            print(f"[DOWNLOAD] Exception caught: {type(e).__name__}: {str(e)[:100]}")
            error_str = str(e)
            if self._is_403_error(error_str):
                self.record_403_error()
                self._record_url_cooldown(url, 3600, "403 download")
            
            # If it's a format error, list available formats for debugging
            if "Requested format is not available" in error_str or "list-formats" in error_str:
                self.logger.error(f"Format error for {url}: {error_str}")
                self.logger.info("Listing available formats for debugging...")
                try:
                    list_opts = get_ydl_opts(download=False, quiet=False, use_android_client=True)
                    list_opts['listformats'] = True
                    
                    def _list_formats():
                        with yt_dlp.YoutubeDL(list_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            return info
                    
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(self.executor, _list_formats)
                except Exception as list_e:
                    self.logger.error(f"Could not list formats: {list_e}")
            else:
                self.logger.error(f"Error downloading: {error_str}")
            return False
    
    def _get_song_identity(self, song_info: Optional[Dict]) -> Optional[str]:
        """Build a stable song identity token for repeat prevention."""
        if not isinstance(song_info, dict):
            return None

        number = song_info.get('number')
        if number is not None:
            return f"num:{number}"

        youtube_url = song_info.get('youtube_url')
        if youtube_url:
            return f"url:{youtube_url}"

        title = (song_info.get('title') or '').strip().lower()
        artist = (song_info.get('artist') or '').strip().lower()
        if title or artist:
            return f"meta:{title}|{artist}"

        return None

    def _record_autoplay_song(self, song_info: Optional[Dict]):
        """Track recent autoplay picks to avoid short-cycle repeats."""
        song_id = self._get_song_identity(song_info)
        if song_id:
            self.autoplay_recent_ids.append(song_id)
        artist_key = self._get_song_artist_key(song_info)
        if artist_key:
            self.autoplay_recent_artists.append(artist_key)
        self._save_autoplay_state()

    async def pre_cache_next_random(self, exclude_song: Optional[Dict] = None):
        """Queue the next likely random song for smooth auto-playlist"""
        try:
            if not self.playlist_cache:
                return
            excluded_ids = set()
            exclude_id = self._get_song_identity(exclude_song)
            if exclude_id:
                excluded_ids.add(exclude_id)

            if self.next_random_cached:
                cached_id = self._get_song_identity(self.next_random_cached)
                if cached_id:
                    excluded_ids.add(cached_id)

            # Get next random song (same logic as get_random_playlist_song)
            random_song = self.get_random_playlist_song(extra_excluded_ids=excluded_ids)
            if not random_song or not random_song.get('youtube_url'):
                return
                
            # Check if already cached
            cache_file = self._get_cache_filename(random_song)
            if os.path.exists(cache_file):
                self.next_random_cached = random_song
                return
                
            # Queue this random song with NORMAL priority
            self.download_queue.add(random_song, DownloadQueue.PRIORITY_NORMAL)
            self.next_random_cached = random_song
            
            self.logger.info(f"Queued next random song: {random_song['title']} by {random_song['artist']}")
            
        except Exception as e:
            self.logger.error(f"Error queuing next random: {e}")

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

    def get_next_catalog_number_append_only(self) -> int:
        """Return the next catalog number using append-only numbering."""
        if not self.playlist_cache:
            return 1
        existing_numbers = [song.get('number') for song in self.playlist_cache if isinstance(song.get('number'), int)]
        if not existing_numbers:
            return 1
        return max(existing_numbers) + 1

    def sync_local_folder_to_catalog(self, folder_path: Optional[str] = None) -> Dict:
        """
        Import new .mp3 files from a local folder into SRX catalog.
        Append-only behavior: never remove songs from catalog.
        """
        target_folder = folder_path or LOCAL_SRX_FOLDER

        result = {
            'success': False,
            'folder': target_folder,
            'added': 0,
            'skipped': 0,
            'total_mp3': 0,
            'start_total': len(self.playlist_cache),
            'end_total': len(self.playlist_cache),
            'error': None,
        }

        try:
            if not os.path.isdir(target_folder):
                result['error'] = f"Local folder not found: {target_folder}"
                return result

            mp3_files = [
                f for f in os.listdir(target_folder)
                if os.path.isfile(os.path.join(target_folder, f)) and f.lower().endswith('.mp3')
            ]
            mp3_files.sort(key=lambda name: name.lower())
            result['total_mp3'] = len(mp3_files)

            # Build a quick lookup so repeated syncs do not duplicate catalog entries.
            known_local_files = set()
            for song in self.playlist_cache:
                local_file = (song.get('local_file') or '').strip().lower()
                if local_file:
                    known_local_files.add(local_file)

            for filename in mp3_files:
                full_path = os.path.abspath(os.path.join(target_folder, filename))
                normalized_path = os.path.normcase(full_path).lower()
                if normalized_path in known_local_files:
                    result['skipped'] += 1
                    continue

                stem = os.path.splitext(filename)[0].strip()
                artist = "Local"
                title = stem
                if ' - ' in stem:
                    left, right = stem.split(' - ', 1)
                    if left.strip() and right.strip():
                        artist = left.strip()
                        title = right.strip()

                new_song = {
                    'number': self.get_next_catalog_number_append_only(),
                    'title': title,
                    'artist': artist,
                    'duration': 0,
                    'verified': True,
                    'play_count': 0,
                    'local_file': full_path,
                    'source': 'local_mp3'
                }

                self.playlist_cache.append(new_song)
                known_local_files.add(normalized_path)
                result['added'] += 1

            if result['added'] > 0:
                self.playlist_cache.sort(key=lambda x: x['number'])
                self._save_playlist_sync()

            result['success'] = True
            result['end_total'] = len(self.playlist_cache)
            return result
        except Exception as e:
            result['error'] = str(e)
            return result
    
    def _get_cache_filename(self, song_info):
        """Get consistent cache filename for a song"""
        import os
        
        if song_info.get('number'):
            # Playlist song - use number and sanitized title
            title = song_info.get('title', 'Unknown')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            filename = f"{song_info['number']:03d}_{safe_title}.mp3"
        else:
            # YouTube request - use hash of URL
            url_hash = abs(hash(song_info.get('youtube_url', '')))
            title = song_info.get('title', 'YouTube_Song')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            filename = f"yt_{url_hash}_{safe_title}.mp3"
            
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
        """Queue missing songs for download via download queue"""
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
            
            self.logger.info(f"Queuing {len(songs_to_download)} songs for download")
            if chat_channel:
                await chat_channel.send(f"📥 Queuing {len(songs_to_download)} songs for download (via queue system)")
            
            # Start background music during caching if not already playing
            if not self.is_playing and not self.is_paused:
                try:
                    self.logger.info("🎵 Starting background music during cache operation...")
                    background_result = await self.simple_play_cached_file(chat_channel)
                    if background_result and chat_channel:
                        await chat_channel.send("🎵 Playing background music while caching...")
                except Exception as bg_error:
                    self.logger.error(f"Failed to start background music: {bg_error}")
            
            # Queue all songs for download with LOW priority (background caching)
            queued = 0
            skipped = 0
            
            for song_info in songs_to_download:
                if not song_info.get('youtube_url'):
                    self.logger.warning(f"No YouTube URL for song #{song_info['number']}: {song_info['title']}")
                    skipped += 1
                    continue
                
                # Add to download queue with LOW priority
                if self.download_queue.add(song_info, DownloadQueue.PRIORITY_LOW):
                    queued += 1
                else:
                    skipped += 1
            
            result = {
                'success': True,
                'message': f'Queued {queued} songs for download ({skipped} skipped)',
                'downloaded': queued,  # "downloaded" = queued in this context
                'failed': skipped,
                'total_missing': len(missing_songs),
                'remaining_missing': len(missing_songs) - queued
            }
            
            if chat_channel:
                queue_status = self.download_queue.get_status()
                await chat_channel.send(f"✅ {queued} songs queued. Download queue: {queue_status['queue_size']} pending")
            
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

        # Preflight check to avoid repeated 403s/broken links
        if not await self._preflight_youtube_check(youtube_url, song_title, chat_channel):
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
            
            use_android_first = self.prefer_android_client
            ydl_opts = get_ydl_opts(
                output_template=output_template,
                download=True,
                quiet=True,
                use_android_client=use_android_first
            )
            ydl_opts_fallback = get_ydl_opts(
                output_template=output_template,
                download=True,
                quiet=True,
                use_android_client=not use_android_first
            )
            
            # Download with timeout and Android client fallback
            def download_with_timeout():
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([youtube_url])
                    return (True, None)
                except Exception as e:
                    error_str = str(e)
                    
                    # Retry with fallback client if format/signature error
                    if any(x in error_str for x in [
                        "Requested format is not available",
                        "Signature solving failed",
                        "n challenge solving failed",
                        "Only images are available"
                    ]):
                        fallback_label = "web client" if use_android_first else "Android client"
                        self.logger.warning(f"Hot queue format error, retrying with {fallback_label}...")
                        try:
                            with yt_dlp.YoutubeDL(ydl_opts_fallback) as ydl:
                                ydl.download([youtube_url])
                            self.logger.info(f"✅ Fallback {fallback_label} hot queue download succeeded")
                            return (True, None)
                        except Exception as fallback_error:
                            self.logger.error(f"Fallback {fallback_label} also failed for hot queue: {fallback_error}")
                            return (False, str(fallback_error))
                    
                    self.logger.error(f"Hot queue download failed for {song_title}: {error_str}")
                    return (False, error_str)
            
            loop = asyncio.get_event_loop()
            try:
                success, error_str = await asyncio.wait_for(
                    loop.run_in_executor(None, download_with_timeout), 
                    timeout=30.0
                )
                
                if success:
                    # Find the downloaded temporary file
                    for ext in ['mp3', 'm4a', 'webm', 'mp4', 'opus', 'ogg']:
                        test_file = os.path.join(temp_dir, f"{temp_filename}.{ext}")
                        if os.path.exists(test_file):
                            self.logger.info(f"Successfully downloaded hot queue: {test_file}")
                            return test_file
                else:
                    if error_str and self._is_403_error(error_str):
                        self.record_403_error()
                        self._record_url_cooldown(youtube_url, 3600, "403 hotqueue")
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"Hot queue download timeout for {song_title}")
                if chat_channel:
                    await chat_channel.send("⏰ Hot queue download timed out")
            except Exception as e:
                self.logger.error(f"Hot queue download error for {song_title}: {e}")
                
        except Exception as e:
            self.logger.error(f"Error in hot queue download: {e}")
            
        return None

    async def download_and_normalize_audio(self, youtube_url: str, song_title: str, chat_channel=None, allow_fallback_cached: bool = True) -> Optional[str]:
        """Download YouTube audio (no FFmpeg required) with global 403 rate limiting"""
        if not YT_DLP_AVAILABLE:
            self.logger.error(f"yt-dlp not available for download: {song_title}")
            return None

        # Check if we're in 403 cooldown
        in_cooldown, remaining = self.is_in_403_cooldown()
        if in_cooldown:
            self.logger.warning(f"Skipping download due to 403 cooldown ({remaining}s remaining): {song_title}")
            # Try to return a cached file instead
            safe_title = "".join(c for c in song_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            for ext in ['m4a', 'webm', 'mp4', 'mp3', 'opus', 'ogg']:
                audio_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                if os.path.exists(audio_file):
                    self.logger.info(f"Using cached audio during cooldown: {audio_file}")
                    return audio_file
            return None

        # Don't do preflight check - just try to download and fall back to cache if it fails
        # This allows us to play cached songs when YouTube videos are unavailable
        
        # Use global lock to prevent concurrent downloads during 403 issues
        async with SimpleSongManager._youtube_download_lock:
            self.logger.info(f"Starting download for: {song_title} from {youtube_url}")
            
            # Reset fallback tracking for this request
            self.last_fallback_audio_file = None
            self.last_fallback_song_info = None

            # Create safe filename
            safe_title = "".join(c for c in song_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '_')
            
            # Try multiple audio extensions
            for ext in ['m4a', 'webm', 'mp4', 'mp3']:
                audio_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                if os.path.exists(audio_file):
                    self.logger.info(f"Using cached audio: {audio_file}")
                    return audio_file
            
            # Download best audio format available (MP3 preferred)
            output_template = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.%(ext)s")
            
            ydl_opts = get_ydl_opts(
                output_template=output_template,
                download=True,
                quiet=True,
                use_android_client=self.prefer_android_client
            )
            
            # Check if file already exists first
            for ext in ['mp3', 'm4a', 'webm', 'mp4', 'opus', 'ogg']:
                test_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                if os.path.exists(test_file):
                    self.logger.info(f"Using existing cached audio: {test_file}")
                    return test_file
            
            # Attempt actual download with timeout protection
            self.logger.info(f"Attempting download for {song_title} from {youtube_url}")
            
            async def get_available_formats(url: str) -> list:
                """Get list of available formats for a URL"""
                try:
                    def _get_formats():
                        self.logger.debug(f"🔍 Starting format detection for {url}")
                        opts = get_ydl_opts(download=False, quiet=True, use_android_client=self.prefer_android_client)
                        opts['socket_timeout'] = 10
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            formats = info.get('formats', [])
                            self.logger.debug(f"📊 Total formats available: {len(formats)}")
                            # Filter for audio or audio+video that can be converted to audio
                            audio_formats = []
                            for fmt in formats:
                                fmt_id = fmt.get('format_id', '')
                                ext = fmt.get('ext', '')
                                vcodec = fmt.get('vcodec', 'none')
                                acodec = fmt.get('acodec', 'none')
                                
                                # Prefer audio-only or formats with audio we can extract
                                if acodec != 'none':
                                    audio_formats.append((fmt_id, ext, acodec, vcodec))
                                    self.logger.debug(f"  ✅ Format {fmt_id}: {ext} (audio={acodec}, video={vcodec})")
                            self.logger.info(f"✨ Filtered to {len(audio_formats)} audio-capable formats")
                            return audio_formats
                    
                    loop = asyncio.get_event_loop()
                    self.logger.info(f"🔍 Extracting format info (timeout=10s)...")
                    formats = await asyncio.wait_for(
                        loop.run_in_executor(None, _get_formats),
                        timeout=10.0
                    )
                    
                    self.logger.info(f"✅ Successfully got {len(formats)} available audio formats")
                    return formats
                except asyncio.TimeoutError:
                    self.logger.error(f"❌ Timeout while getting available formats (10s)")
                    return []
                except Exception as e:
                    self.logger.error(f"❌ Could not get available formats: {e}")
                    return []
            
            def download_with_timeout(format_spec='best'):
                try:
                    # Use the specified format (or 'best' as default)
                    opts = get_ydl_opts(
                        output_template=output_template,
                        download=True,
                        quiet=True,
                        use_android_client=self.prefer_android_client
                    )
                    opts['format'] = format_spec
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([youtube_url])
                    return (True, None, format_spec)
                except Exception as e:
                    error_str = str(e)
                    
                    # Retry with fallback client if format/signature error
                    if any(x in error_str for x in [
                        "Requested format is not available",
                        "Signature solving failed",
                        "n challenge solving failed",
                        "Only images are available"
                    ]):
                        fallback_label = "web client" if self.prefer_android_client else "Android client"
                        self.logger.warning(f"YouTube request format error, retrying with {fallback_label}...")
                        try:
                            opts_fallback = get_ydl_opts(
                                output_template=output_template,
                                download=True,
                                quiet=True,
                                use_android_client=not self.prefer_android_client
                            )
                            opts_fallback['format'] = format_spec
                            with yt_dlp.YoutubeDL(opts_fallback) as ydl:
                                ydl.download([youtube_url])
                            self.logger.info(f"✅ Fallback {fallback_label} YouTube request download succeeded")
                            return (True, None, format_spec)
                        except Exception as fallback_error:
                            self.logger.error(f"Fallback {fallback_label} also failed for YouTube request: {fallback_error}")
                            return (False, str(fallback_error), format_spec)
                    self.logger.error(f"Download failed for {song_title} with format '{format_spec}': {error_str}")
                    return (False, error_str, format_spec)
            
            # Run download in executor with timeout
            loop = asyncio.get_event_loop()
            try:
                # Try 'best' format first
                success, error_str, used_format = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: download_with_timeout('best')), 
                    timeout=30.0
                )
                
                self.logger.info(f"Initial download attempt: success={success}, error={error_str[:100] if error_str else 'None'}")
                
                # If format not available, try to get actual available formats and try those
                if not success and error_str and 'format is not available' in error_str.lower():
                    self.logger.warning(f"🔍 Format 'best' not available. Attempting to list available formats for {song_title}...")
                    available_formats = await get_available_formats(youtube_url)
                    self.logger.info(f"✅ Format detection complete: found {len(available_formats)} available audio formats")
                    
                    if available_formats:
                        self.logger.info(f"📋 Available formats: {available_formats[:10]}")  # Log first 10
                        self.logger.info(f"🔄 Found {len(available_formats)} available formats. Trying alternatives...")
                        # Try formats in order of preference (prioritize audio+video combos)
                        for fmt_id, ext, acodec, vcodec in available_formats[:5]:  # Try first 5
                            self.logger.info(f"🎯 Trying format {fmt_id} ({ext}, audio={acodec})")
                            try:
                                success, error_str, used_format = await asyncio.wait_for(
                                    loop.run_in_executor(None, lambda fid=fmt_id: download_with_timeout(fid)),
                                    timeout=30.0
                                )
                                if success:
                                    self.logger.info(f"✅ Successfully downloaded with format {fmt_id}!")
                                    break
                                else:
                                    self.logger.warning(f"❌ Format {fmt_id} failed: {error_str[:80] if error_str else 'Unknown error'}")
                            except asyncio.TimeoutError:
                                self.logger.warning(f"⏱️ Format {fmt_id} timed out (30s)")
                                continue
                            except Exception as retry_e:
                                self.logger.warning(f"❌ Format {fmt_id} error: {retry_e}")
                                continue
                    else:
                        self.logger.warning(f"❌ Could not get list of available formats for {song_title}")
                
                if success:
                    # Find the downloaded file
                    downloaded_file = None
                    for ext in ['mp3', 'm4a', 'webm', 'mp4', 'opus', 'ogg']:
                        test_file = os.path.join(MUSIC_CACHE_DIR, f"{safe_title}.{ext}")
                        if os.path.exists(test_file):
                            downloaded_file = test_file
                            break
                    
                    if downloaded_file:
                        # Normalize the audio file
                        if self.normalize_audio_file(downloaded_file):
                            self.logger.info(f"Successfully downloaded and normalized: {downloaded_file}")
                            return downloaded_file
                        else:
                            # Still return the file even if normalization fails (it's playable)
                            self.logger.warning(f"Downloaded but normalization failed: {downloaded_file}")
                            return downloaded_file
                else:
                    if error_str and self._is_403_error(error_str):
                        self.record_403_error()
                        self._record_url_cooldown(youtube_url, 3600, "403 download")
                    
            except asyncio.TimeoutError:
                self.logger.warning(f"Download timeout for {song_title}")
            except Exception as e:
                error_str = str(e)
                self.logger.error(f"Download error for {song_title}: {error_str}")
                
                # Only skip if video is TRULY unavailable (not format issues)
                if any(x in error_str.lower() for x in ['age restricted', 'not available', 'video unavailable', 'private', 'removed', 'deleted']):
                    self.logger.warning(f"Video unavailable for download: {song_title}")
                    if chat_channel:
                        await chat_channel.send(f"⚠️ Video unavailable: {song_title}")
                    return False
                
                # Check for 403 errors and activate cooldown
                if self._is_403_error(error_str):
                    self.record_403_error()
                    self._record_url_cooldown(youtube_url, 3600, "403 download exception")
                    if chat_channel:
                        in_cooldown, remaining = self.is_in_403_cooldown()
                        await chat_channel.send(f"⚠️ YouTube rate limit detected. Cooldown active for {remaining}s.")
                    
                    try:
                        asyncio.create_task(chat_channel.send(error_msg))
                    except Exception as chat_error:
                        self.logger.error(f"Failed to send error to chat: {chat_error}")
            
            # Check all files in cache directory for our title
            if os.path.exists(MUSIC_CACHE_DIR):
                for filename in os.listdir(MUSIC_CACHE_DIR):
                    if safe_title.lower() in filename.lower():
                        full_path = os.path.join(MUSIC_CACHE_DIR, filename)
                        self.logger.info(f"Found cached file: {full_path}")
                        return full_path
                
                # If no specific match, optionally return ANY cached file to get music playing
                if allow_fallback_cached:
                    cached_files = [f for f in os.listdir(MUSIC_CACHE_DIR) 
                                  if f.lower().endswith(('.m4a', '.webm', '.mp4', '.opus', '.ogg', '.mp3'))]
                    if cached_files:
                        import random
                        excluded = set()
                        if self.current_song:
                            excluded.add(os.path.basename(self.current_song))
                        if self.last_fallback_audio_file:
                            excluded.add(os.path.basename(self.last_fallback_audio_file))

                        candidates = [f for f in cached_files if f not in excluded]
                        if not candidates:
                            candidates = cached_files

                        selected_file = random.choice(candidates)
                        fallback_file = os.path.join(MUSIC_CACHE_DIR, selected_file)
                        self.logger.info(f"Using fallback cached file: {fallback_file}")

                        # Capture display info so chat/now-playing matches the file actually played
                        self.last_fallback_audio_file = fallback_file
                        self.last_fallback_song_info = self._get_friendly_song_info(selected_file)

                        # Don't announce here - let play_song() handle the announcement with correct info
                        return fallback_file
            
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
            # Only stop music if something is actually currently playing
            # Don't unconditionally kill ffmpeg before starting next song (causes race condition)
            if self.is_playing or self.is_paused:
                self.logger.info(f"Stopping current playback before starting new song")
                await self.stop_music()
                await asyncio.sleep(0.2)  # Brief pause for cleanup
            
            local_file = song_info.get('local_file')
            youtube_url = song_info.get('youtube_url')

            # Local catalog entries play directly from disk.
            if local_file:
                audio_file = local_file
                if not os.path.exists(audio_file):
                    self.logger.error(f"Local song file not found: {audio_file}")
                    if chat_channel:
                        await chat_channel.send(f"❌ File not found for #{song_info.get('number', '?')}: {song_info.get('title', 'Unknown')}")
                    if MUSIC_STATE_AVAILABLE and music_state_manager:
                        music_state_manager.stop_playback()
                    return False
            else:
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
                    allow_fallback_cached = username != "AutoPlaylist"
                    audio_file = await self.download_and_normalize_audio(
                        youtube_url,
                        song_info['title'],
                        chat_channel,
                        allow_fallback_cached=allow_fallback_cached,
                    )
            
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
            
            # If we had to fall back to a cached file, update display info to match what will actually play
            effective_song_info = song_info
            if (self.last_fallback_audio_file and self.last_fallback_song_info and
                os.path.normcase(self.last_fallback_audio_file) == os.path.normcase(audio_file)):
                effective_song_info = {**song_info, **self.last_fallback_song_info}
                self.logger.warning(
                    f"Using fallback cached song info: {effective_song_info.get('title', 'Unknown')} by {effective_song_info.get('artist', 'Unknown')}"
                )
            else:
                # Clear fallback state if it didn't apply to this playback
                self.last_fallback_audio_file = None
                self.last_fallback_song_info = None

            # Unified music playback using AudioManager
            if not self.audio_manager.play_music(audio_file):
                self.logger.error(f"Failed to play song '{effective_song_info.get('title', 'Unknown')}' by {effective_song_info.get('artist', 'Unknown')} - audio file: {audio_file}")
                if chat_channel:
                    await chat_channel.send(f"❌ Failed to play: {effective_song_info.get('title', 'Unknown')} - skipping to next song")
                if MUSIC_STATE_AVAILABLE and music_state_manager:
                    music_state_manager.stop_playback()
                return False
            
            # Update local state
            self.is_playing = True
            self.is_paused = False
            self.current_song = audio_file
            self.current_song_info = (effective_song_info, username)
            self.current_hot_queue_file = audio_file if song_info.get('hot_queue', False) else None  # Track for cleanup
            
            # Track song timing
            import time
            self.song_start_time = time.time()
            self.song_duration = effective_song_info.get('duration', 300)  # Default 5 minutes if no duration
            
            self.logger.info(f"🎵 Playing: {effective_song_info['title']} (requested by {username}) via {self.audio_backend}")
            
            # Increment play count for playlist songs (not user requests)
            if username == "AutoPlaylist":
                self._record_autoplay_song(effective_song_info)
                self.increment_play_count(effective_song_info)
            elif effective_song_info.get('number'):
                self.update_last_played(effective_song_info)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error playing song: {e}")
            if MUSIC_STATE_AVAILABLE and music_state_manager:
                music_state_manager.stop_playback()
            return False

    async def stop_music(self):
        """Stop current music using global music state manager"""
        self.logger.info(f"🛑 stop_music called | audio_ready={self.audio_ready} backend={self.audio_backend} is_playing={self.is_playing} is_paused={self.is_paused}")
        # Use global music state manager to stop
        if MUSIC_STATE_AVAILABLE and music_state_manager:
            self.logger.info("Calling music_state_manager.stop_playback()")
            music_state_manager.stop_playback()
        # Also handle local audio backend cleanup
        if self.audio_ready and self.audio_backend == "pygame":
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.set_volume(0.0)
                await asyncio.sleep(0.1)
                pygame.mixer.music.set_volume(self.master_volume)
                self.logger.info("✅ Pygame stop completed")
            except Exception as e:
                self.logger.error(f"❌ Error during pygame stop: {e}")
                try:
                    pygame.mixer.quit()
                    pygame.mixer.init()
                    pygame.mixer.music.set_volume(self.master_volume)
                    self.logger.info("🔄 Pygame reinitialized after error")
                except Exception as reinit_error:
                    self.logger.error(f"❌ Failed to reinitialize pygame: {reinit_error}")
        elif self.audio_backend == "playsound3":
            self.logger.info("Calling music_state_manager.force_stop_playback() for playsound3")
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
        self.logger.info(f"Clearing state: is_playing={self.is_playing}, is_paused={self.is_paused}, current_song={self.current_song}")
        self.is_playing = False
        self.is_paused = False
        self.current_song = None
        self.current_song_info = None
        self.song_start_time = None
        self.song_duration = None
        self.logger.info("🔄 Music state cleared")

    def pause_music(self):
        """Pause current music playback"""
        self.logger.info(f"pause_music called | audio_ready={self.audio_ready} backend={self.audio_backend} is_playing={self.is_playing} is_paused={self.is_paused}")
        if self.audio_ready and self.is_playing:
            if self.audio_backend == "pygame" and pygame.mixer.get_init():
                pygame.mixer.music.pause()
                self.is_paused = True
                self.logger.info("Paused music with pygame")
            elif self.audio_backend == "playsound3":
                self.logger.info("playsound3 does not support pause")
                return False
        return True

    def resume_music(self):
        """Resume paused music playback"""
        self.logger.info(f"resume_music called | audio_ready={self.audio_ready} backend={self.audio_backend} is_paused={self.is_paused}")
        if self.audio_ready and self.is_paused:
            if self.audio_backend == "pygame" and pygame.mixer.get_init():
                pygame.mixer.music.unpause()
                self.is_paused = False
                self.logger.info("Resumed music with pygame")
                return True
            elif self.audio_backend == "playsound3":
                self.logger.info("playsound3 does not support resume")
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

    def is_actually_playing(self):
        """Check if music is actually playing (not just flagged as playing)"""
        if self.audio_backend == "pygame" and pygame.mixer.get_init():
            return pygame.mixer.music.get_busy()
        # For other backends, assume playing if flagged (no reliable way to check)
        return self.is_playing

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

    def get_random_playlist_song(self, extra_excluded_ids: Optional[set] = None):
        """Pick next auto-play song using a high-variety shuffle-bag policy.

        Priority:
        1) Shuffle-bag with strict filters (recent songs, artist spacing, cooldown).
        2) Relax artist spacing.
        3) Relax recent-song filter.
        4) Rebuild bag and retry before emergency fallback.
        """
        if not self.playlist_cache:
            return None

        import random

        excluded_ids = set(self.autoplay_recent_ids)
        if extra_excluded_ids:
            excluded_ids.update(extra_excluded_ids)

        id_to_song = {}
        for song in self.playlist_cache:
            song_id = self._get_song_identity(song)
            if song_id:
                id_to_song[song_id] = song

        blocked_artists = set(list(self.autoplay_recent_artists)[-self.autoplay_artist_spacing:])
        recent_ids = set(self.autoplay_recent_ids)

        def _is_eligible(song, enforce_recent=True, enforce_artist=True, enforce_cooldown=True):
            song_id = self._get_song_identity(song)
            if song_id and song_id in excluded_ids:
                return False
            if enforce_recent and song_id and song_id in recent_ids:
                return False
            if enforce_cooldown and self.is_song_on_cooldown(song):
                return False
            if enforce_artist:
                artist_key = self._get_song_artist_key(song)
                if artist_key and artist_key in blocked_artists:
                    return False
            return True

        def _pick_from_bag(enforce_recent=True, enforce_artist=True, enforce_cooldown=True):
            idx = 0
            while idx < len(self.autoplay_shuffle_bag):
                song_id = self.autoplay_shuffle_bag[idx]
                song = id_to_song.get(song_id)
                if not song:
                    self.autoplay_shuffle_bag.pop(idx)
                    continue
                if _is_eligible(song, enforce_recent, enforce_artist, enforce_cooldown):
                    self.autoplay_shuffle_bag.pop(idx)
                    self._save_autoplay_state()
                    return song
                idx += 1
            return None

        if not self.autoplay_shuffle_bag:
            self._rebuild_autoplay_shuffle_bag()

        choice = _pick_from_bag(enforce_recent=True, enforce_artist=True, enforce_cooldown=True)
        reason = "shuffle-bag strict"
        if not choice:
            choice = _pick_from_bag(enforce_recent=True, enforce_artist=False, enforce_cooldown=True)
            reason = "shuffle-bag relaxed artist spacing"
        if not choice:
            choice = _pick_from_bag(enforce_recent=False, enforce_artist=False, enforce_cooldown=True)
            reason = "shuffle-bag relaxed recent filter"

        if not choice:
            self._rebuild_autoplay_shuffle_bag()
            choice = _pick_from_bag(enforce_recent=True, enforce_artist=True, enforce_cooldown=True)
            reason = "reshuffled bag strict"
        if not choice:
            choice = _pick_from_bag(enforce_recent=False, enforce_artist=False, enforce_cooldown=True)
            reason = "reshuffled bag relaxed"

        if not choice:
            fallback_pool = [
                song for song in self.playlist_cache
                if self._get_song_identity(song) not in excluded_ids and not self.is_song_on_cooldown(song)
            ]
            if not fallback_pool:
                fallback_pool = [song for song in self.playlist_cache if self._get_song_identity(song) not in excluded_ids]
            if not fallback_pool:
                fallback_pool = list(self.playlist_cache)
            choice = random.choice(fallback_pool)
            reason = "emergency fallback pool"

        self.logger.info(f"Selected random song ({reason}): {choice['title']} by {choice['artist']}")
        return choice

    def increment_play_count(self, song_info):
        """Increment play count and stamp last_played for a playlist song."""
        try:
            ts = datetime.now(timezone.utc).isoformat()
            for song in self.playlist_cache:
                if (song.get('number') and song.get('number') == song_info.get('number')) or \
                   (song.get('youtube_url') and song.get('youtube_url') == song_info.get('youtube_url')) or \
                   (song.get('title') == song_info.get('title') and song.get('artist') == song_info.get('artist')):
                    current_count = song.get('play_count', 0)
                    song['play_count'] = current_count + 1
                    song['last_played'] = ts
                    self.add_song_cooldown(song)
                    self.logger.info(
                        f"Incremented play count for '{song['title']}' by {song['artist']}: {current_count} -> {song['play_count']} (added to {self.cooldown_minutes}-minute cooldown)"
                    )
                    asyncio.create_task(self._save_playlist_async())
                    break
        except Exception as e:
            self.logger.error(f"Failed to increment play count: {e}")

    def update_last_played(self, song_info):
        """Stamp last_played for a playlist song without changing play_count."""
        try:
            ts = datetime.now(timezone.utc).isoformat()
            for song in self.playlist_cache:
                if (song.get('number') and song.get('number') == song_info.get('number')) or \
                   (song.get('youtube_url') and song.get('youtube_url') == song_info.get('youtube_url')) or \
                   (song.get('title') == song_info.get('title') and song.get('artist') == song_info.get('artist')):
                    song['last_played'] = ts
                    asyncio.create_task(self._save_playlist_async())
                    self.logger.info(f"Updated last_played for '{song['title']}' by {song['artist']} -> {ts}")
                    break
        except Exception as e:
            self.logger.error(f"Failed to update last_played: {e}")
    
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
        ydl_opts = get_ydl_opts(download=False, quiet=True)
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
            # Sync to Google Sheets in background to avoid blocking playback transition
            asyncio.create_task(self._async_sync_queue_to_sheets())
            
            # Important: Song is ALWAYS removed from queue regardless of success/failure
            # This prevents YouTube songs from getting stuck in a loop
            has_youtube_url = bool(song_info.get('youtube_url'))
            
            success = await self.play_song(song_info, username, chat_channel)
            if success:
                if chat_channel:
                    played_info = self.current_song_info[0] if self.current_song_info else song_info
                    song_number = played_info.get('number', 'Unknown')
                    command = f"!srx {song_number}"
                    await chat_channel.send(f"🎵 Now playing: {played_info['title']} by {played_info['artist']} — Play it: {command}")
                return (self.current_song_info[0], username) if self.current_song_info else (song_info, username)
            else:
                # If it's any song with a YouTube URL that failed, start background download and re-queue
                if has_youtube_url:
                    song_desc = f"#{song_info.get('number', 'Unknown')}: {song_info.get('title', 'Unknown')}" if song_info.get('number') else song_info.get('title', 'Unknown')
                    self.logger.warning(f"YouTube download failed for {song_desc} (requested by {username}): {song_info.get('youtube_url', 'Unknown URL')}")
                    # Start silent background download and re-queue when ready (no chat message yet)
                    asyncio.create_task(self._retry_failed_youtube_song(song_info, username, chat_channel))
                # For songs without YouTube URLs that fail, we'll try the next queue item or random playlist
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
                asyncio.create_task(self.pre_cache_next_random(exclude_song=random_song))
                
                success = await self.play_song(random_song, "AutoPlaylist", chat_channel)
                if success:
                    if chat_channel:
                        played_info = self.current_song_info[0] if self.current_song_info else random_song
                        song_number = played_info.get('number', 'Unknown')
                        command = f"!srx {song_number}"
                        await chat_channel.send(f"🎵 Now playing: {played_info['title']} by {played_info['artist']} — Play it: {command}")
                    return (self.current_song_info[0], "AutoPlaylist") if self.current_song_info else (random_song, "AutoPlaylist")
        
        return None
    
    async def _retry_failed_youtube_song(self, song_info: dict, username: str, chat_channel=None):
        """Background retry for failed YouTube song downloads - respects global 403 cooldown"""
        youtube_url = song_info.get('youtube_url')
        song_title = song_info.get('title', 'Unknown')
        song_number = song_info.get('number', '?')
        quarters_spent = song_info.get('quarters_spent', 0)
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Check if we're in cooldown - if so, wait for it to expire plus extra time
                in_cooldown, remaining = self.is_in_403_cooldown()
                if in_cooldown:
                    wait_time = remaining + 30  # Add 30s buffer after cooldown expires
                    self.logger.info(f"Retry #{attempt+1} waiting for 403 cooldown + buffer: {wait_time}s for {song_title}")
                    await asyncio.sleep(wait_time)
                else:
                    # Even if not in cooldown, use longer delays: 60s, 120s, 180s
                    retry_delay = 60 * (attempt + 1)
                    self.logger.info(f"Retrying YouTube download (attempt {attempt+1}/{max_retries}): #{song_number} {song_title} - waiting {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                
                # Try to download
                audio_file = await self.download_and_normalize_audio(youtube_url, song_title, None, allow_fallback_cached=False)
                
                if audio_file and os.path.exists(audio_file):
                    # Successfully downloaded, re-add to queue
                    self.current_queue.append((song_info, username, None))
                    song_desc = f"#{song_number}: {song_title}" if song_number != '?' else song_title
                    self.logger.info(f"YouTube retry successful: {song_desc} - re-queued for {username}")
                    if chat_channel:
                        await chat_channel.send(f"✅ {song_desc} ready! Re-queued for {username}")
                    return
                    
            except Exception as e:
                error_str = str(e)
                self.logger.debug(f"YouTube retry attempt {attempt+1} failed: {error_str[:100]}")
                # If it's a 403 error, the cooldown will be recorded by download_and_normalize_audio
        
        # All retries failed - refund quarters if applicable
        song_desc = f"#{song_number}: {song_title}" if song_number != '?' else song_title
        self.logger.error(f"YouTube song permanently failed after {max_retries} retries: {song_desc}")
        
        if quarters_spent > 0:
            self.give_quarters(username, quarters_spent)
            if chat_channel:
                await chat_channel.send(f"❌ {song_desc} unavailable. {quarters_spent} quarter(s) refunded to {username}.")
        else:
            if chat_channel:
                await chat_channel.send(f"❌ {song_desc} unavailable (requested by {username}).")

    def clear_snipe_list(self):
        """Clear the quarter song snipe list (called on bot startup)"""
        self.quarter_song_snipe_list = []
        self.logger.info("Quarter song snipe list cleared on startup.")
    
# Initialize manager
song_manager = SimpleSongManager()

class SongRequestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = song_manager
        self.chat_channel = None  # Store channel for error reporting
        self.logger = logging.getLogger(__name__)
        # Clear snipe list on bot startup
        self.manager.clear_snipe_list()
        self.playlist_running = False
        self.playlist_task = None

    @commands.command(name="np")
    async def now_playing(self, ctx):
        """Show info about the currently playing song."""
        if not self.manager.current_song_info:
            await ctx.send("❌ No song is currently playing.")
            return
        song_info, username = self.manager.current_song_info
        # Detect quarter song (YouTube request, not in playlist)
        is_quarter_song = song_info.get('youtube_url') and not song_info.get('number')
        if is_quarter_song:
            msg = f"🎬 Quarter Song Playing: {song_info.get('title', 'Custom Song')} (requested by {username})\nYouTube: {song_info.get('youtube_url', '')}"
        else:
            song_number = song_info.get('number', 'Unknown')
            command = f"!srx {song_number}"
            msg = f"🎵 Now Playing: {song_info.get('title', 'Unknown')} by {song_info.get('artist', 'Unknown Artist')} (requested by {username}) — Play it: {command}"
            if song_info.get('youtube_url'):
                msg += f"\nYouTube: {song_info.get('youtube_url', '')}"
        await ctx.send(msg)

    async def _remove_last_queued_song_for_user(self, ctx, username: str):
        """Remove the most recent queued song for a user without touching the SRX catalog."""
        removed = None
        for idx in range(len(self.manager.current_queue) - 1, -1, -1):
            song_info, queue_username, timestamp = self.manager.current_queue[idx]
            if queue_username.lower() == username.lower():
                removed = self.manager.current_queue.pop(idx)
                break

        if not removed:
            await ctx.send("❌ You don't have any songs in the queue to remove.")
            return

        song_info, queue_username, timestamp = removed
        refund_text = ""
        quarters_spent = song_info.get('quarters_spent', 0)
        if quarters_spent:
            self.manager.give_quarters(username, quarters_spent)
            refund_text = f" Refunded {quarters_spent} quarter(s)."

        asyncio.create_task(self.manager._async_sync_queue_to_sheets())

        title = song_info.get('title', 'Your song')
        await ctx.send(f"🗑️ Removed your last queued song: {title}.{refund_text}")

    @commands.command(name="wrongsong")
    async def wrongsong_command(self, ctx):
        """Remove the calling user's latest SRX queue entry (does not delete catalog entries)."""
        username = ctx.author.name
        await self._remove_last_queued_song_for_user(ctx, username)

    @commands.command(name="srx")
    async def song_request(self, ctx, action_or_request: str = None, *, url: str = None):
        """Song request system: !srx [number] (FREE) | !srx [youtube_url] (1 quarter) | !srx "title" (search) | !srx add [url] (mod) | !srx hot [url] (mod) | !srx del [number] (mod) | !srx importlocal [folder] (mod) | !srx [start|stop|pause|resume|next|status] (mod - playback control)"""
        if not action_or_request:
            await ctx.send("🎵 **Song Requests:** `!srx 42` (playlist, FREE) | `!srx [youtube_url]` (1 quarter) | `!srx keyword` (search) | `!srx add [url]` (mod) | `!srx hot [url]` (mod) | `!srx del [number]` (mod) | `!srx importlocal [folder]` (mod, mp3 only) | **Playback:** `!srx start/stop/pause/resume/next/status` (mod)")
            return

        username = ctx.author.name
        action_or_request = action_or_request.strip()

        # Check for playback control subcommands (mod-only)
        if action_or_request.lower() == "start":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can control SRX playback.")
                return
            self.manager.music_enabled = True
            self.playlist_running = True
            if self.playlist_task and not self.playlist_task.done():
                self.playlist_task.cancel()
            self.playlist_task = asyncio.create_task(self._run_playlist(ctx.channel))
            return
        elif action_or_request.lower() == "remove":
            await self._remove_last_queued_song_for_user(ctx, username)
            return
        elif action_or_request.lower() == "stop":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can control SRX playback.")
                return
            self.manager.music_enabled = False
            self.playlist_running = False
            if self.playlist_task:
                self.playlist_task.cancel()
            await self.manager.stop_music()
            await ctx.send("⏹️ SRX stopped.")
            return
        elif action_or_request.lower() == "pause":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can control SRX playback.")
                return
            if self.manager.is_playing and not self.manager.is_paused:
                self.manager.pause_music()
                await ctx.send("⏸️ SRX paused.")
            else:
                await ctx.send("❌ No music currently playing to pause.")
            return
        elif action_or_request.lower() == "resume":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can control SRX playback.")
                return
            if self.manager.is_paused:
                self.manager.resume_music()
                await ctx.send("▶️ SRX resumed.")
            else:
                await ctx.send("❌ No paused music to resume.")
            return
        elif action_or_request.lower() == "next":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can skip songs.")
                return
            await self.manager.stop_music()
            self.manager.is_paused = False
            # Immediately advance to the next song if playback is running
            if self.manager.music_enabled and self.playlist_running:
                await self.manager.process_queue(ctx.channel)
            await ctx.send("⏭️ Skipped to next song...")
            return
        elif action_or_request.lower() == "status":
            status = self.manager.get_playback_status()
            queue_size = len(self.manager.current_queue)
            current_info = ""
            if self.manager.current_song_info:
                song_info, username_current = self.manager.current_song_info
                current_info = f"\nNow: {song_info['title']} (by {username_current})"
            await ctx.send(f"🎵 {status} | Queue: {queue_size} songs{current_info}")
            return
        elif action_or_request.lower() == "hype":
            # Play Quad City DJs - C'mon Ride It immediately, then continue queue (Mod only)
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can use the hype command.")
                return
            
            # Find the hype song in the playlist
            hype_song = None
            for song in self.manager.playlist_cache:
                if song.get('number') == 579:  # Quad City DJs - C'mon Ride It
                    hype_song = song
                    break
            
            if not hype_song:
                await ctx.send("❌ Hype song not found in catalog!")
                return
            
            # Stop current song and play hype song immediately
            await self.manager.stop_music()
            success = await self.manager.play_song(hype_song, "System", ctx)
            
            if success:
                await ctx.send(f"🔥 HYPE TIME! Now playing: {hype_song['title']} by {hype_song['artist']}")
            else:
                await ctx.send(f"❌ Failed to play hype song")
            return

        # Check for subcommands first
        if action_or_request.lower() == "add":
            # Mod-only: Add to catalog
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can add songs to the catalog.")
                return
            # Accept either url param or action_or_request as the YouTube input
            target_input = url if url else action_or_request
            if not target_input:
                await ctx.send("❌ Please provide a YouTube URL or video ID. Usage: `!srx add [youtube_url|video_id]`")
                return
            if not self.manager.is_youtube_url(target_input):
                await ctx.send("❌ Invalid YouTube URL or video ID. Usage: `!srx add [youtube_url|video_id]`")
                return
            # If it's a playlist URL, extract the video ID
            if self.manager.is_youtube_playlist_url(target_input):
                target_input = self.manager.extract_video_from_playlist_url(target_input)
                if not target_input:
                    await ctx.send("❌ Could not extract video from playlist URL. Please provide a direct video link.")
                    return
            # If it's a video ID, convert to full URL
            import re
            if re.fullmatch(r'[A-Za-z0-9_-]{11}', target_input):
                target_url = f"https://youtu.be/{target_input}"
            else:
                target_url = target_input
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
                
            # Check for playlist URLs and extract video
            if self.manager.is_youtube_playlist_url(target_url):
                target_url = self.manager.extract_video_from_playlist_url(target_url)
                if not target_url:
                    await ctx.send("❌ Could not extract video from playlist URL. Please provide a direct video link.")
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

        elif action_or_request.lower() == "importlocal":
            if not (ctx.author.is_mod or ctx.author.is_broadcaster):
                await ctx.send("❌ Only moderators or the broadcaster can import local songs into the catalog.")
                return

            target_folder = url.strip() if url else LOCAL_SRX_FOLDER
            await self._handle_import_local_folder(ctx, target_folder)
            return

        # Handle regular requests (existing logic)
        # Check if it's a number (playlist request)
        if action_or_request.isdigit():
            await self._handle_playlist_request(ctx, int(action_or_request), username)
        elif self.manager.is_youtube_url(action_or_request):
            # If it's a playlist URL, extract the video ID
            processed_url = action_or_request
            if self.manager.is_youtube_playlist_url(action_or_request):
                processed_url = self.manager.extract_video_from_playlist_url(action_or_request)
                if not processed_url:
                    await ctx.send("❌ Could not extract video from playlist URL. Please provide a direct video link.")
                    return
            await self._handle_youtube_request(ctx, processed_url, username)
        else:
            # Treat remaining input as a search query across title/artist/number
            search_query = action_or_request
            if url:
                search_query = f"{action_or_request} {url}".strip()

            matches = self.manager.search_playlist(search_query, limit=5)

            if not matches:
                await ctx.send(f"❌ No playlist match for \"{search_query}\". Try a number like `!srx 42` or a YouTube link.")
                return

            # Searches always show choices; only an explicit song number queues a track.
            lines = ["🔍 Search results. Request by number:"]
            for song in matches:
                lines.append(f"• #{song.get('number', '?')} — {song.get('title', 'Unknown')} by {song.get('artist', 'Unknown')}")
            await ctx.send("\n".join(lines))
            return

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

        # Start pre-caching this song immediately to reduce gaps (HIGH priority for queued songs)
        if song.get('youtube_url'):
            asyncio.create_task(self.manager.start_smart_pre_cache(song, priority=DownloadQueue.PRIORITY_HIGH))
        
        # Add to queue (playlist requests are FREE)
        queue_item = (song, username, datetime.now())
        self.manager.current_queue.append(queue_item)
        
        # Sync to Google Sheets asynchronously (don't block)
        asyncio.create_task(self.manager._async_sync_queue_to_sheets())
        
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

        # Trigger ZAP for song requests (playlist/free)
        raffle_cog = self.bot.get_cog("RaffleCog") if hasattr(self, 'bot') else None
        if raffle_cog:
            try:
                await raffle_cog.trigger_zap_song(username, ctx)
            except Exception:
                pass

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

        # Start pre-caching immediately with HIGH priority (user paid for this)
        temp_song_for_cache = {
            'youtube_url': url,
            'title': 'YouTube Request',  # Will be updated below
            'artist': 'YouTube'
        }
        asyncio.create_task(self.manager.start_smart_pre_cache(temp_song_for_cache, priority=DownloadQueue.PRIORITY_HIGH))
        
        # Get actual video information to avoid caching conflicts
        try:
            import yt_dlp
            ydl_opts = get_ydl_opts(download=False, quiet=True)
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'YouTube Song')
                artist = info.get('uploader', 'YouTube')
        except Exception as e:
            # Fallback if yt-dlp fails
            self.logger.warning(f"Failed to get YouTube info for quarter song: {e}")
            title = f'YouTube Song ({url[-8:]})'
            # Use last 8 chars of URL for uniqueness
            artist = 'YouTube'
        
        song_info = {
            'title': title,
            'artist': artist,
            'youtube_url': url,
            'quarters_spent': self.manager.quarters_per_youtube_request
        }

        # Add to queue
        queue_item = (song_info, username, datetime.now())
        self.manager.current_queue.append(queue_item)
        
        # Sync to Google Sheets asynchronously (don't block)
        asyncio.create_task(self.manager._async_sync_queue_to_sheets())
        
        position = len(self.manager.current_queue)
        await ctx.send(f"🎵 Added YouTube song to queue (Position {position}) [-{self.manager.quarters_per_youtube_request} quarter]")

        # Trigger ZAP for song requests (YouTube/paid)
        raffle_cog = self.bot.get_cog("RaffleCog") if hasattr(self, 'bot') else None
        if raffle_cog:
            try:
                await raffle_cog.trigger_zap_song(username, ctx)
            except Exception:
                pass

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
    
    @commands.command(name="dlq", aliases=["downloadqueue", "dlqueue"])
    async def download_queue_status(self, ctx):
        """Show download queue status (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can check download queue status.")
            return
        
        status = self.manager.download_queue.get_status()
        
        msg = f"📥 **Download Queue Status**\n"
        msg += f"• Queue Size: {status['queue_size']}\n"
        msg += f"• Currently Downloading: {status['downloading'] or 'None'}\n"
        msg += f"• Worker Running: {'Yes' if status['is_running'] else 'No'}\n"
        msg += f"• Stats: {status['stats']['total_completed']} completed, "
        msg += f"{status['stats']['total_failed']} failed, "
        msg += f"{status['stats']['total_queued']} total queued"
        
        await ctx.send(msg)

    @commands.command(name="srxvariety", aliases=["autoplaystats", "varietystats"])
    async def srx_variety_status(self, ctx):
        """Show autoplay variety diagnostics (Mod only)."""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can check autoplay variety status.")
            return

        stats = self.manager.get_autoplay_variety_status()

        artist_window = stats['artist_window']
        artist_window_text = ", ".join(artist_window) if artist_window else "(none)"

        msg = "🎲 **SRX Autoplay Variety Status**\n"
        msg += f"• Playlist songs: {stats['playlist_total']}\n"
        msg += f"• Shuffle bag remaining: {stats['bag_remaining']} ({stats['bag_fill_percent']}%)\n"
        msg += f"• Recent track memory: {stats['recent_tracks']}/{stats['recent_tracks_max']}\n"
        msg += f"• Artist spacing window: {stats['artist_spacing']}\n"
        msg += f"• Current artist blocklist: {artist_window_text}\n"
        msg += f"• Active cooldown entries: {stats['active_cooldowns']}"

        await ctx.send(msg)

    async def _handle_add_song_from_url(self, ctx, youtube_url: str):
        """Handle !srx add [url] - Add song to catalog from YouTube URL"""
        try:
            # Get video information using yt-dlp
            import yt_dlp
            
            await ctx.send("🔍 Getting video information...")
            
            def _extract_info(use_android: bool):
                opts = get_ydl_opts(download=False, quiet=True, use_android_client=use_android)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(youtube_url, download=False)
            
            info = None
            extract_error = None
            try:
                info = _extract_info(self.manager.prefer_android_client)
            except Exception as e:
                extract_error = e
                try:
                    info = _extract_info(not self.manager.prefer_android_client)
                except Exception as e2:
                    extract_error = e2

            if info is None:
                # Fallback to oEmbed for basic metadata
                try:
                    import urllib.request
                    import json as _json
                    oembed_url = f"https://www.youtube.com/oembed?url={youtube_url}&format=json"
                    with urllib.request.urlopen(oembed_url, timeout=10) as resp:
                        data = _json.load(resp)
                    title = data.get('title', 'Unknown Title')
                    uploader = data.get('author_name', 'Unknown Artist')
                    duration = 0
                    await ctx.send("⚠️ Limited metadata (duration unavailable).")
                except Exception:
                    raise extract_error
            else:
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
            
            await ctx.send(f"✅ Adding #{next_number}: {title} by {uploader}{duration_str} 🎬")

            # Prepare immediately so it is ready to play
            print(f"[ADD_COMMAND] Starting immediate download for #{next_number}")
            try:
                download_ok = await self.manager._queue_download_song(new_song)
            except Exception as download_error:
                download_ok = False
                print(f"[ADD_COMMAND] Immediate download exception for #{next_number}: {download_error}")
                self.manager.logger.error(f"Immediate download failed for #{next_number}: {download_error}")

            if download_ok:
                await ctx.send(f"✅ Ready to play: !srx {next_number}")
            else:
                # Queue for background retry
                self.manager.download_queue.add(new_song, DownloadQueue.PRIORITY_LOW)
                await ctx.send(f"🔄 Retrying in background...")
            
        except Exception as e:
            await ctx.send(f"❌ Error adding song: {str(e)[:100]}")

    async def _handle_import_local_folder(self, ctx, folder_path: str):
        """Handle !srx importlocal [folder] - import .mp3 files into catalog as local tracks."""
        result = self.manager.sync_local_folder_to_catalog(folder_path)

        if not result['success']:
            await ctx.send(f"❌ {result.get('error', 'Failed to import local songs.')}")
            return

        # Sync catalog to Google Sheets after successful import.
        if result['added'] > 0 and SHEETS_SYNC_AVAILABLE and music_sheets_manager:
            try:
                music_sheets_manager.force_sync_catalog()
            except Exception as e:
                self.manager.logger.error(f"Failed to sync catalog after local import: {e}")

        await ctx.send(
            f"📁 Local import complete from {result['folder']}: "
            f"{result['added']} added, {result['skipped']} already known, "
            f"catalog {result['start_total']} -> {result['end_total']}"
        )

    async def _handle_hot_queue(self, ctx, youtube_url: str):
        """Handle !srx hot [url] - Hot queue a YouTube song"""
        try:
            # Get actual video information for unique caching
            try:
                import yt_dlp
                ydl_opts = get_ydl_opts(download=False, quiet=True)
                
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
            
            # Sync to sheets asynchronously
            asyncio.create_task(self.manager._async_sync_queue_to_sheets())
            
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

        if not target_user or not target_user.strip():
            await ctx.send("Usage: !givequarter username [amount] or !givequarter @username [amount]")
            return

        # Strip @ if present
        username_clean = target_user.lstrip("@").strip()
        self.manager.give_quarters(username_clean, amount)
        await ctx.send(f"💰 Gave {amount} quarter(s) to {username_clean}.")

    @commands.command(name="clearqueue")
    async def clear_queue(self, ctx):
        """Clear song queue (Mod only)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can clear the queue.")
            return

        self.manager.current_queue.clear()
        # Sync to Google Sheets after clearing queue asynchronously
        asyncio.create_task(self.manager._async_sync_queue_to_sheets())
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
            
            await ctx.send("🔍 Getting video information...")
            
            def _extract_info(use_android: bool):
                opts = get_ydl_opts(download=False, quiet=True, use_android_client=use_android)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(youtube_url, download=False)
            
            info = None
            extract_error = None
            try:
                info = _extract_info(self.manager.prefer_android_client)
            except Exception as e:
                extract_error = e
                try:
                    info = _extract_info(not self.manager.prefer_android_client)
                except Exception as e2:
                    extract_error = e2

            if info is None:
                # Fallback to oEmbed for basic metadata
                try:
                    import urllib.request
                    import json as _json
                    oembed_url = f"https://www.youtube.com/oembed?url={youtube_url}&format=json"
                    with urllib.request.urlopen(oembed_url, timeout=10) as resp:
                        data = _json.load(resp)
                    title = data.get('title', 'Unknown Title')
                    uploader = data.get('author_name', 'Unknown Artist')
                    duration = 0
                    await ctx.send("⚠️ Limited metadata (duration unavailable).")
                except Exception:
                    raise extract_error
            else:
                title = info.get('title', 'Unknown Title')
                uploader = info.get('uploader', 'Unknown Artist')
                duration = info.get('duration', 0)
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
                ydl_opts = get_ydl_opts(download=False, quiet=True)
                
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
            
            # Sync to sheets asynchronously
            asyncio.create_task(self.manager._async_sync_queue_to_sheets())
            
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

    @commands.command(name="modsrx", aliases=["modcommands", "musicmod", "modmusic"])
    async def mod_music_help(self, ctx):
        """Show mod-only SRX commands"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can view mod commands.")
            return
        
        help_text = """🎵 **Mod SRX Commands:**
        
**Quick Add (Recommended):**
• `!addurl [youtube_url]` - Add song to catalog (auto-gets title/artist)
• `!addsong [youtube_url]` - Same as addurl (detects URLs automatically)

**Hot Queue:**
• `!hotqueue [youtube_url]` - Download, play once, then auto-delete
• `!cleantemp` - Clean up leftover temporary files

**Playback Control:**
• `!srx start` - Start music system
• `!srx stop` - Stop music and disable system
• `!srx pause` - Pause current song
• `!srx resume` - Resume paused song
• `!srx next` - Skip to next song
• `!srx status` - Show playback status & queue

**Advanced Catalog:**
• `!addsong [number] Title | Artist | YouTube_URL` - Full manual entry
• `!playlistinfo [number]` - Check song details

**Audio Normalization:**
• `!normalizecache` - Normalize all cached songs to -16 LUFS
• `!normalizecache [number]` - Normalize specific song by catalog number
• `!srxnorm [number]` - Shorthand for normalizecache

**Volume Control:**
• `!volume [0-100]` - Set master volume

💡 **Tip:** Use `!addurl` or `!addsong [url]` for easiest song adding!
💡 **Audio:** New downloads are auto-normalized. Use `!normalizecache` for existing songs."""
        
        await ctx.send(help_text)

    @commands.command(name="normalizecache", aliases=["normalizeaudio", "normalizemusic", "srxnorm"])
    async def normalize_cache_cmd(self, ctx, song_number: str = None):
        """Normalize cached audio files to -16 LUFS (Mod only)
        Usage: !normalizecache (all) or !normalizecache [number] (specific song)"""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can normalize audio files.")
            return
        
        import os
        import glob
        
        if not os.path.exists(MUSIC_CACHE_DIR):
            await ctx.send("❌ Cache directory not found.")
            return
        
        # Normalize specific song by catalog number
        if song_number and song_number.isdigit():
            song_num = int(song_number)
            song = self.manager.find_playlist_song(song_num)
            
            if not song:
                await ctx.send(f"❌ Song #{song_num} not found in playlist.")
                return
            
            cache_file = self.manager._get_cache_filename(song)
            
            if not os.path.exists(cache_file):
                await ctx.send(f"❌ Song #{song_num} not in cache. Download it first with !srx {song_num}")
                return
            
            await ctx.send(f"🔊 Normalizing song #{song_num}: {song['title']}...")
            
            try:
                # Normalize synchronously (blocking)
                success = self.manager.normalize_audio_file(cache_file)
                
                if success:
                    await ctx.send(f"✅ Normalized #{song_num}: {song['title']} to -16 LUFS")
                else:
                    await ctx.send(f"⚠️ Normalization completed for #{song_num}, but with warnings. File is still playable.")
            except Exception as e:
                await ctx.send(f"❌ Error normalizing #{song_num}: {str(e)[:100]}")
            
            return
        
        # Normalize all cached songs
        await ctx.send("🔊 Starting normalization of all cached songs...")
        await ctx.send("⏳ This may take several minutes depending on cache size. I'll update you as songs are completed.")
        
        try:
            # Get all cached audio files
            cache_files = []
            for ext in ['mp3', 'm4a', 'webm', 'mp4', 'opus', 'ogg']:
                pattern = os.path.join(MUSIC_CACHE_DIR, f"*.{ext}")
                cache_files.extend(glob.glob(pattern))
            
            if not cache_files:
                await ctx.send("❌ No cached audio files found.")
                return
            
            total_files = len(cache_files)
            normalized_count = 0
            failed_count = 0
            
            await ctx.send(f"📦 Found {total_files} cached files to normalize...")
            
            for idx, cache_file in enumerate(cache_files, 1):
                filename = os.path.basename(cache_file)
                
                try:
                    # Normalize the file
                    success = self.manager.normalize_audio_file(cache_file)
                    
                    if success:
                        normalized_count += 1
                    else:
                        # File may still be playable even if normalization failed
                        failed_count += 1
                    
                    # Progress update every 5 files
                    if idx % 5 == 0 or idx == total_files:
                        await ctx.send(f"📥 Progress: {idx}/{total_files} songs normalized...")
                    
                    # Small delay to prevent overwhelming the system
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    self.manager.logger.error(f"Error normalizing {filename}: {e}")
                    failed_count += 1
            
            # Final summary
            await ctx.send(f"✅ Normalization complete!")
            await ctx.send(f"🎵 Normalized: {normalized_count}/{total_files} songs")
            if failed_count > 0:
                await ctx.send(f"⚠️ {failed_count} songs had issues but are still playable")
            
        except Exception as e:
            await ctx.send(f"❌ Error during normalization batch: {str(e)[:100]}")

    async def _run_playlist(self, channel):
        """Continuously play songs from the queue or random playlist"""
        while self.playlist_running:
            if self.manager.music_enabled:
                # Clear stale playback state if audio has finished but state flags remain
                if not self.manager.is_actually_playing():
                    if self.manager.is_playing or self.manager.is_paused:
                        self.manager.is_playing = False
                        self.manager.is_paused = False
                    if MUSIC_STATE_AVAILABLE and music_state_manager and music_state_manager.is_music_playing():
                        self.logger.info("Clearing stale global music state (no audio playing)")
                        music_state_manager.stop_playback()

                if not self.manager.is_actually_playing():
                    result = await self.manager.process_queue(channel)
                    if not result:  # No song was played (empty queue and no random)
                        await asyncio.sleep(5)  # Wait before checking again
            await asyncio.sleep(1)  # Check every second

def prepare(bot):
    bot.add_cog(SongRequestCog(bot))
