import glob
import random
import os
import json
from threading import Thread
from queue import Queue
from playsound import playsound
from pathlib import Path

sfx_queue = Queue()
queue_worker_started = False

# Path to usage tracking file
DATA_DIR = Path(__file__).parent / "data"
USAGE_FILE = DATA_DIR / "sfx_usage.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load existing usage stats or initialize
if USAGE_FILE.exists():
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            sfx_usage = json.load(f)
    except json.JSONDecodeError:
        print("⚠️ Failed to parse sfx_usage.json, starting fresh.")
        sfx_usage = {}
else:
    sfx_usage = {}

# Save to file
def save_usage():
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(sfx_usage, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to write usage file: {e}")

async def queue_sfx(path: str):
    global queue_worker_started
    abs_path = os.path.abspath(path)
    filename = os.path.basename(abs_path)
    sfx_queue.put(abs_path)

    # Increment usage count
    sfx_usage[filename] = sfx_usage.get(filename, 0) + 1
    save_usage()

    if not queue_worker_started:
        thread = Thread(target=sfx_worker, daemon=True)
        thread.start()
        queue_worker_started = True

def sfx_worker():
    while True:
        path = sfx_queue.get()
        try:
            print(f"🔊 Playing SFX: {path}")
            playsound(path)
        except Exception as e:
            print(f"⚠️ Failed to play {path}: {e}")
        finally:
            sfx_queue.task_done()

def get_worst_sfx(sfx_folder):
    all_mp3s = glob.glob(os.path.join(sfx_folder, "**", "*.mp3"), recursive=True)
    if not all_mp3s:
        return None

    usage = sfx_usage
    candidates = []
    min_count = float("inf")

    for path in all_mp3s:
        name = os.path.basename(path)
        count = usage.get(name, 0)

        if count == 0:
            candidates.append(path)
        elif count < min_count:
            min_count = count
            candidates = [path] if count < min_count else candidates + [path]

    if not candidates:
        return None

    return random.choice(candidates)
