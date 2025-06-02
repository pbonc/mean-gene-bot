import os
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

SFX_COMMAND_PREFIX = "!"
SFX_EXTENSIONS = (".mp3", ".wav", ".ogg")

def sfx_command_from_filename(filename):
    """Create the SFX chat command from a filename: sfx/dah.mp3 -> !dah"""
    base = os.path.basename(filename)
    name, ext = os.path.splitext(base)
    return SFX_COMMAND_PREFIX + name.lower()

class SFXRegistry:
    """
    Handles registration and lookup of SFX commands to file paths.
    Scans a directory for SFX files and builds a mapping like {"!dah": "sfx/dah.mp3"}
    """
    def __init__(self, sfx_root="sfx"):
        self.sfx_root = sfx_root
        self.file_commands = {}  # Maps "!dah" -> "sfx/dah.mp3"
        self.observer = None
        self._lock = threading.Lock()

    def scan_and_register(self, notify_callback=None):
        base_path = os.path.join(os.path.dirname(__file__), self.sfx_root)
        print(f"\n[SFXRegistry] scan_and_register: __file__={__file__}")
        print(f"[SFXRegistry] scan_and_register: sfx_root={self.sfx_root}")
        print(f"[SFXRegistry] scan_and_register: base_path={base_path}")
        print(f"[SFXRegistry] scan_and_register: exists={os.path.isdir(base_path)}")
        print(f"[SFXRegistry] scan_and_register: listdir={os.listdir(base_path) if os.path.isdir(base_path) else 'N/A'}\n")
        file_commands = {}
        for dirpath, dirnames, filenames in os.walk(base_path):
            for file in filenames:
                if file.lower().endswith(SFX_EXTENSIONS):
                    relpath = os.path.relpath(os.path.join(dirpath, file), os.path.dirname(__file__))
                    command = sfx_command_from_filename(file)
                    file_commands[command] = relpath
        with self._lock:
            self.file_commands = file_commands
        if notify_callback:
            notify_callback(sorted(self.file_commands.keys()))
        print("Available SFX commands:", sorted(self.file_commands.keys()))

    def get_sfx_path(self, command):
        """Return the filepath for a given command, or None."""
        with self._lock:
            return self.file_commands.get(command)

    def start_watching(self, notify_callback=None):
        """Start FS watching for changes to SFX files."""
        if self.observer:
            return
        event_handler = SFXDirEventHandler(self, notify_callback=notify_callback)
        observer = Observer()
        observer.schedule(event_handler, self.sfx_root, recursive=True)
        observer.daemon = True
        observer.start()
        self.observer = observer

    def stop_watching(self):
        """Stop FS watching."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None

class SFXDirEventHandler(FileSystemEventHandler):
    """Fires when the SFX directory changes."""
    def __init__(self, registry, notify_callback=None):
        super().__init__()
        self.registry = registry
        self.notify_callback = notify_callback

    def on_any_event(self, event):
        # Any change in the directory should cause a rescan
        logging.info("SFX directory changed: %s", event)
        self.registry.scan_and_register(self.notify_callback)

def build_sfx_registry():
    """Builds and returns a ready-to-use SFXRegistry. For use in main.py."""
    registry = SFXRegistry()
    registry.scan_and_register(notify_callback=None)
    return registry