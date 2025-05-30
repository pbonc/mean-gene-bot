import logging
from twitchio.ext import commands
import asyncio
import os
import re

# Import your broadcast function from the websocket server module
from backend.ws_server import broadcast_overlay_message

logger = logging.getLogger("overlay")

# Always resolve path relative to this file's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEART_IMAGE_DIR = os.path.join(BASE_DIR, "..", "overlay", "gifs", "heart")
GIFS_IMAGE_DIR = os.path.join(BASE_DIR, "..", "overlay", "gifs")
IMAGE_EXTENSIONS = (".gif", ".jpg", ".jpeg", ".png", ".webp")

def list_heart_bases():
    """Scan the heart folder and return a set of valid bases (e.g. 'dar', 'dar2', 'fal6')."""
    bases = set()
    if not os.path.isdir(HEART_IMAGE_DIR):
        logger.warning(f"[OverlayCog] Heart image directory {HEART_IMAGE_DIR} does not exist.")
        return bases
    for fname in os.listdir(HEART_IMAGE_DIR):
        name, ext = os.path.splitext(fname)
        if ext.lower() in IMAGE_EXTENSIONS:
            m = re.match(r"^([a-z][a-z0-9]*)(\d*)$", name)
            if m:
                bases.add(name)
    return bases

def list_gif_bases():
    """Scan the gifs folder (excluding heart) and return set of valid bases (e.g. 'meme3')."""
    bases = set()
    if not os.path.isdir(GIFS_IMAGE_DIR):
        logger.warning(f"[OverlayCog] Gifs image directory {GIFS_IMAGE_DIR} does not exist.")
        return bases
    for fname in os.listdir(GIFS_IMAGE_DIR):
        path = os.path.join(GIFS_IMAGE_DIR, fname)
        if fname == "heart" or os.path.isdir(path):
            continue
        name, ext = os.path.splitext(fname)
        if ext.lower() in IMAGE_EXTENSIONS:
            bases.add(name)
    return bases

class OverlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.refresh_bases()
        logger.info(f"[OverlayCog] Loaded heart bases: {self.heart_bases}")
        logger.info(f"[OverlayCog] Loaded gif bases: {self.gif_bases}")

    def refresh_bases(self):
        self.heart_bases = list_heart_bases()
        self.gif_bases = list_gif_bases()

    async def try_handle_overlay(self, message):
        print(f"[OverlayCog] try_handle_overlay called with: {message.content}")
        if message.echo:
            return False
        if message.author and message.author.name.lower() == self.bot.nick.lower():
            return False
        if not message.content.startswith("!"):
            return False

        command = message.content.split()[0]

        # Hot reload overlay bases every trigger, so you can add images live!
        self.refresh_bases()

        # Regex for !name<3> or !name<3N> commands (heart overlays)
        m = re.match(r"^!([a-z][a-z0-9]*)<3(\d*)$", command)
        if m:
            base = m.group(1)
            number = m.group(2) or ""
            overlay_base = base + number  # e.g. 'dar2' for !dar<32>, 'fal' for !fal<3>
            action = None
            if overlay_base in self.heart_bases:
                if number:
                    action = f"trigger_{base}{number}_heart"
                else:
                    action = f"trigger_{base}_heart"
            if action:
                logger.info(f"[OverlayCog] Handling overlay command: {command} -> {action}")
                print(f"[OverlayCog] Trigger overlay: {action} (from {command})")
                payload = {
                    "action": action,
                    "user": message.author.name
                }
                if hasattr(self.bot, "overlay_ws_loop") and self.bot.overlay_ws_loop is not asyncio.get_event_loop():
                    asyncio.run_coroutine_threadsafe(
                        broadcast_overlay_message(payload),
                        self.bot.overlay_ws_loop
                    )
                else:
                    await broadcast_overlay_message(payload)
                return True

        # Regex for non-heart: !meme3 etc. (gifs folder)
        m2 = re.match(r"^!([a-z0-9_]+)$", command)
        if m2:
            base = m2.group(1)
            if base in self.gif_bases:
                action = f"trigger_{base}"
                logger.info(f"[OverlayCog] Handling overlay command: {command} -> {action}")
                print(f"[OverlayCog] Trigger overlay: {action} (from {command})")
                payload = {
                    "action": action,
                    "user": message.author.name
                }
                if hasattr(self.bot, "overlay_ws_loop") and self.bot.overlay_ws_loop is not asyncio.get_event_loop():
                    asyncio.run_coroutine_threadsafe(
                        broadcast_overlay_message(payload),
                        self.bot.overlay_ws_loop
                    )
                else:
                    await broadcast_overlay_message(payload)
                return True

        return False

def prepare(bot):
    if not bot.get_cog("OverlayCog"):
        bot.add_cog(OverlayCog(bot))