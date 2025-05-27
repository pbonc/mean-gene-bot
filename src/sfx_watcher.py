import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time

SFX_DIR = "sfx"  # Adjust to your actual sfx directory path

class SFXEventHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        # Only care about .mp3 files
        if event.is_directory:
            return
        if not event.src_path.endswith(".mp3"):
            return

        # Figure out what happened and where
        action = "modified"
        if event.event_type == "created":
            action = "added"
        elif event.event_type == "deleted":
            action = "removed"
        elif event.event_type == "moved":
            action = "moved"

        print(f"SFX {action}: {event.src_path}")

def start_sfx_watcher():
    event_handler = SFXEventHandler()
    observer = Observer()
    observer.schedule(event_handler, SFX_DIR, recursive=True)
    observer.start()
    print(f"Started SFX watcher on {SFX_DIR}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_sfx_watcher()