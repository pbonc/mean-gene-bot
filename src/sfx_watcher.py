import os
import threading
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Base directory is the project root (one level above this file)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# SFX directory (always ../sfx relative to this script)
SFX_DIR = os.path.join(BASE_DIR, "sfx")

# Logs directory and log file
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
SFX_LOG_PATH = os.path.join(LOGS_DIR, "sfx_creation.log")

sfx_logger = logging.getLogger("sfx_creation")
sfx_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(SFX_LOG_PATH)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
if not any(isinstance(h, logging.FileHandler) and h.baseFilename == file_handler.baseFilename for h in sfx_logger.handlers):
    sfx_logger.addHandler(file_handler)

class SFXRegistry:
    def __init__(self):
        self.file_commands = {}    # '!zap': 'fe/zap.mp3'
        self.folder_commands = {}  # '!fe': ['fe/zap.mp3', ...]
        self.registered_commands = set()
        self.sfx_dir = SFX_DIR     # Store absolute SFX dir for use by cogs

    def scan_and_register(self, notify_callback=None):
        file_cmd_count = 0
        folder_cmd_count = 0
        for root, dirs, files in os.walk(self.sfx_dir):
            rel_folder = os.path.relpath(root, self.sfx_dir)
            for f in files:
                if f.lower().endswith(".mp3"):
                    cmd = f"!{os.path.splitext(f)[0]}"
                    path = f if rel_folder == "." else os.path.join(rel_folder, f)
                    if cmd not in self.registered_commands:
                        self.file_commands[cmd] = path
                        self.registered_commands.add(cmd)
                        file_cmd_count += 1
            if rel_folder != ".":
                folder_cmd = f"!{os.path.basename(rel_folder)}"
                mp3s = [f for f in files if f.lower().endswith(".mp3")]
                if mp3s and folder_cmd not in self.registered_commands:
                    self.folder_commands[folder_cmd] = [os.path.join(rel_folder, f) for f in mp3s]
                    self.registered_commands.add(folder_cmd)
                    folder_cmd_count += 1
        total_cmds = file_cmd_count + folder_cmd_count
        print(f"SFX: {file_cmd_count} file commands and {folder_cmd_count} folder commands registered ({total_cmds} total).")
        sfx_logger.info(f"{file_cmd_count} SFX file commands and {folder_cmd_count} folder commands registered ({total_cmds} total).")
        if notify_callback:
            notify_callback(f"{file_cmd_count} file and {folder_cmd_count} folder SFX commands registered.")

    def register_file_command(self, cmd, path, notify_callback=None):
        if cmd not in self.registered_commands:
            self.file_commands[cmd] = path
            self.registered_commands.add(cmd)
            msg = f"Registering command {cmd} for {path}"
            sfx_logger.info(msg)
            if notify_callback:
                notify_callback(f"SFX command {cmd} added for {path}")

    def unregister_file_command(self, cmd, notify_callback=None):
        if cmd in self.registered_commands:
            path = self.file_commands.get(cmd, "")
            self.file_commands.pop(cmd, None)
            self.registered_commands.remove(cmd)
            msg = f"Unregistered command {cmd}"
            sfx_logger.info(msg)
            if notify_callback:
                notify_callback(f"SFX command {cmd} removed (was for {path})")

    def register_folder_command(self, cmd, files, notify_callback=None):
        if cmd not in self.registered_commands:
            self.folder_commands[cmd] = files
            self.registered_commands.add(cmd)
            msg = f"Registering folder command {cmd}"
            sfx_logger.info(msg)
            if notify_callback:
                notify_callback(f"SFX folder command {cmd} added")

    def unregister_folder_command(self, cmd, notify_callback=None):
        if cmd in self.registered_commands:
            self.folder_commands.pop(cmd, None)
            self.registered_commands.remove(cmd)
            msg = f"Unregistered folder command {cmd}"
            sfx_logger.info(msg)
            if notify_callback:
                notify_callback(f"SFX folder command {cmd} removed")

class SFXEventHandler(FileSystemEventHandler):
    def __init__(self, registry, notify_callback=None):
        super().__init__()
        self.registry = registry
        self.notify_callback = notify_callback

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".mp3"):
            return
        rel_path = os.path.relpath(event.src_path, SFX_DIR)
        cmd = f"!{os.path.splitext(os.path.basename(event.src_path))[0]}"
        self.registry.register_file_command(cmd, rel_path, self.notify_callback)

    def on_deleted(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".mp3"):
            return
        cmd = f"!{os.path.splitext(os.path.basename(event.src_path))[0]}"
        self.registry.unregister_file_command(cmd, self.notify_callback)

    def on_moved(self, event):
        if event.is_directory or not event.dest_path.lower().endswith(".mp3"):
            return
        old_cmd = f"!{os.path.splitext(os.path.basename(event.src_path))[0]}"
        new_cmd = f"!{os.path.splitext(os.path.basename(event.dest_path))[0]}"
        self.registry.unregister_file_command(old_cmd, self.notify_callback)
        rel_path = os.path.relpath(event.dest_path, SFX_DIR)
        self.registry.register_file_command(new_cmd, rel_path, self.notify_callback)

class SFXWatcher:
    def __init__(self, notify_callback=None):
        self.registry = SFXRegistry()
        self.notify_callback = notify_callback
        self.observer = None

    def start(self):
        self.registry.scan_and_register(notify_callback=None)
        event_handler = SFXEventHandler(self.registry, self.notify_callback)
        self.observer = Observer()
        self.observer.schedule(event_handler, SFX_DIR, recursive=True)
        self.observer.start()

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()

def build_sfx_registry():
    """Builds and returns a ready-to-use SFXRegistry. For use in main.py."""
    registry = SFXRegistry()
    registry.scan_and_register(notify_callback=None)
    return registry

# For standalone testing
if __name__ == "__main__":
    watcher = SFXWatcher()
    watcher.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()