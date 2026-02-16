"""
Global Music State Manager
Prevents music overlap by tracking global playback state across all music systems
"""
import threading
import logging
import subprocess
import signal
import os
from typing import Optional

LOG = logging.getLogger("music_state")

class MusicStateManager:
    """Singleton class to manage global music state and prevent overlapping playback"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MusicStateManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.is_playing = False
        self.current_process: Optional[subprocess.Popen] = None
        self.playback_lock = threading.Lock()
        self.current_song_info = {}
        
        LOG.info("Global Music State Manager initialized")
    
    def start_playback(self, song_info: dict = None) -> bool:
        """
        Attempt to start playback. Returns True if successful, False if music already playing.
        """
        with self.playback_lock:
            if self.is_playing:
                LOG.warning(f"Music already playing: {self.current_song_info.get('title', 'Unknown')}")
                return False
            
            # Stop any existing process first
            self.force_stop_playback()
            
            self.is_playing = True
            self.current_song_info = song_info or {}
            LOG.info(f"Started playback: {self.current_song_info.get('title', 'Unknown')}")
            return True
    
    def stop_playback(self):
        """Stop current playback and clear state"""
        with self.playback_lock:
            if not self.is_playing:
                return
            
            self.force_stop_playback()
            self.is_playing = False
            self.current_song_info = {}
            LOG.info("Stopped playback")
    
    def force_stop_playback(self):
        """Force stop any running music processes"""
        try:
            # Only kill the specific music process we're tracking, not all Python processes
            # Killing all python.exe would kill the bot itself!
            if os.name == 'nt':  # Windows
                # Only kill ffmpeg processes, not python (to avoid killing the bot)
                subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe'], 
                             capture_output=True, check=False)
            else:  # Unix-like
                subprocess.run(['pkill', '-f', 'playsound'], check=False)
                subprocess.run(['pkill', '-f', 'ffmpeg'], check=False)
            
            # Clear process reference
            if self.current_process:
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=2)
                except:
                    try:
                        self.current_process.kill()
                    except:
                        pass
                finally:
                    self.current_process = None
        
        except Exception as e:
            LOG.error(f"Error force stopping playback: {e}")
    
    def set_current_process(self, process: subprocess.Popen):
        """Set the current music process for tracking"""
        with self.playback_lock:
            self.current_process = process
    
    def is_music_playing(self) -> bool:
        """Check if music is currently playing"""
        return self.is_playing
    
    def get_current_song(self) -> dict:
        """Get information about currently playing song"""
        return self.current_song_info.copy()

# Global singleton instance
music_state_manager = MusicStateManager()