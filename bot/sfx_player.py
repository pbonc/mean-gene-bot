import asyncio
import os
from threading import Thread
from queue import Queue
from playsound import playsound

sfx_queue = Queue()
queue_worker_started = False


async def queue_sfx(path: str):
    global queue_worker_started
    abs_path = os.path.abspath(path)
    sfx_queue.put(abs_path)

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
