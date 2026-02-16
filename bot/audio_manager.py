import threading
import time
import os
import asyncio
import queue

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    pygame = None
    PYGAME_AVAILABLE = False

try:
    from playsound3 import playsound as ps3
    PLAYSOUND3_AVAILABLE = True
except ImportError:
    ps3 = None
    PLAYSOUND3_AVAILABLE = False

class AudioManager:
    def __init__(self, music_volume=0.3, sfx_volume=0.6, duck_volume=0.1):
        self.music_volume = music_volume
        self.sfx_volume = sfx_volume
        self.duck_volume = duck_volume
        self.music_playing = False
        self.sfx_playing = False
        self.music_file = None
        self.sfx_thread = None
        self.music_backend = None
        self.sfx_backend = None
        # Unified SFX queue to prevent overlaps
        self.sfx_queue = queue.Queue()
        self.sfx_lock = threading.Lock()
        self.sfx_worker_thread = None
        self._init_pygame()
        self._start_sfx_worker()

    def _init_pygame(self):
        if PYGAME_AVAILABLE:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
                    pygame.mixer.init()
                self.music_backend = 'pygame'
                self.sfx_backend = 'pygame'
            except Exception as e:
                print(f"[AudioManager] Pygame mixer init failed: {e}")
                self.music_backend = None
                self.sfx_backend = None

    def _start_sfx_worker(self):
        """Start background thread that processes SFX queue serially."""
        def worker():
            while True:
                try:
                    path = self.sfx_queue.get()
                    if path is None:  # Shutdown signal
                        break
                    self._play_sfx_blocking(path)
                    self.sfx_queue.task_done()
                except Exception as e:
                    print(f"[AudioManager] SFX worker error: {e}")
        self.sfx_worker_thread = threading.Thread(target=worker, daemon=True)
        self.sfx_worker_thread.start()
        print("[AudioManager] SFX queue worker started")

    def play_music(self, path):
        if self.music_backend == 'pygame':
            try:
                if not os.path.exists(path):
                    print(f"[AudioManager] File does not exist: {path}")
                    return False
                file_size = os.path.getsize(path)
                print(f"[AudioManager] Playing: {os.path.basename(path)} ({file_size} bytes)")
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self.music_volume)
                pygame.mixer.music.play()
                self.music_playing = True
                self.music_file = path
                return True
            except Exception as e:
                print(f"[AudioManager] Error playing {os.path.basename(path)}: {type(e).__name__}: {e}")
                return False
        else:
            print(f"[AudioManager] No available backend for music: {path}")
            return False

    def _fallback_play_music(self, path):
        if PLAYSOUND3_AVAILABLE:
            def music_thread():
                try:
                    ps3(path, block=True)
                    self.music_playing = False
                    print(f"[AudioManager] Finished playing music: {os.path.basename(path)} (playsound3)")
                except Exception as e:
                    self.music_playing = False
                    print(f"[AudioManager] Playsound3 music error: {e}")
            t = threading.Thread(target=music_thread, daemon=True)
            t.start()
            self.music_playing = True
            self.music_file = path
            return True
        else:
            print(f"[AudioManager] No available backend for music: {path}")
            return False

    def stop_music(self):
        if self.music_backend == 'pygame' and pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            self.music_playing = False
        # No stop for playsound3 fallback

    def play_sfx(self, path):
        """Queue an SFX for playback. Returns immediately without blocking."""
        print(f"[AudioManager] Queueing SFX: {os.path.basename(path)}")
        self.sfx_queue.put(path)

    def _play_sfx_blocking(self, path):
        """Actually play the SFX (blocking). Called by worker thread."""
        print(f"[AudioManager] Playing SFX: {os.path.basename(path)}")
        if self.sfx_backend == 'pygame':
            try:
                if self.music_playing and pygame.mixer.music.get_busy():
                    pygame.mixer.music.set_volume(self.duck_volume)
                sound = pygame.mixer.Sound(path)
                sound.set_volume(self.sfx_volume)
                channel = sound.play()
                while channel.get_busy():
                    pygame.time.wait(10)
                print(f"[AudioManager] Finished SFX: {os.path.basename(path)} (pygame)")
            except Exception as e:
                print(f"[AudioManager] Pygame SFX error: {e}")
                self._fallback_play_sfx_blocking(path)
            finally:
                if self.music_playing and pygame.mixer.music.get_busy():
                    pygame.mixer.music.set_volume(self.music_volume)
        else:
            self._fallback_play_sfx_blocking(path)

    def _fallback_play_sfx_blocking(self, path):
        """Fallback SFX playback using playsound3 (blocking)."""
        if PLAYSOUND3_AVAILABLE:
            try:
                ps3(path, block=True)
                print(f"[AudioManager] Finished SFX: {os.path.basename(path)} (playsound3)")
            except Exception as e:
                print(f"[AudioManager] Playsound3 SFX error: {e}")
        else:
            print(f"[AudioManager] No available backend for SFX: {path}")

    def set_music_volume(self, volume):
        self.music_volume = volume
        if self.music_backend == 'pygame' and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(volume)

    def set_sfx_volume(self, volume):
        self.sfx_volume = volume

    def is_music_playing(self):
        if self.music_backend == 'pygame':
            return pygame.mixer.music.get_busy()
        return self.music_playing

    def is_sfx_playing(self):
        if self.sfx_thread and self.sfx_thread.is_alive():
            return True
        return False
