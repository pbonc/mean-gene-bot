import os
import asyncio
from twitchio.ext import commands
from bot.loader import register_img_command, unregister_img_command

IMG_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "img"))
CHECK_INTERVAL = 5  # seconds

class ImgWatcher:
    def __init__(self, bot: commands.Bot, verbose=False):
        self.bot = bot
        self.known_commands = set()
        self.task = None
        self.verbose = verbose
        self.initialized = False

    def start(self):
        print(f"👁️ ImgWatcher START requested. Scanning folder: {IMG_FOLDER}")
        self.task = asyncio.create_task(self._watch_img_folder())
        if self.verbose:
            print("🧪 ImgWatcher task launched.")

    def stop(self):
        if self.task:
            self.task.cancel()
            if self.verbose:
                print("🛑 ImgWatcher task cancelled via stop().")

    async def _send_twitch_msg(self, message: str):
        if self.bot.connected_channels:
            try:
                await self.bot.connected_channels[0].send(message)
            except Exception as e:
                print(f"⚠️ Failed to send twitch message: {e}")

    async def _watch_img_folder(self):
        await asyncio.sleep(2)
        if self.verbose:
            print("🚀 Entered _watch_img_folder()")
        while True:
            try:
                if self.verbose:
                    print("🔁 ImgWatcher tick — scanning for changes...")

                current_imgs = self._get_img_commands()
                added = current_imgs - self.known_commands
                removed = self.known_commands - current_imgs

                if self.initialized:
                    for img in added:
                        register_img_command(self.bot, img)
                        print(f"✅ Registered new IMG command: !{img}")
                        await self._send_twitch_msg(f"New IMG command added: !{img}")

                    for img in removed:
                        unregister_img_command(self.bot, img)
                        print(f"❌ Unregistered IMG command: !{img}")
                        await self._send_twitch_msg(f"IMG command removed: !{img}")
                else:
                    if self.verbose:
                        print(f"🌱 ImgWatcher baseline: {current_imgs}")

                self.known_commands = current_imgs
                self.initialized = True
                await asyncio.sleep(CHECK_INTERVAL)

            except asyncio.CancelledError:
                if self.verbose:
                    print("🛑 ImgWatcher task cancelled in loop.")
                break
            except Exception as e:
                print(f"⚠️ Error in ImgWatcher: {e}")
                await asyncio.sleep(CHECK_INTERVAL)

    def _get_img_commands(self):
        img_commands = set()
        supported_ext = (".gif", ".jpg", ".jpeg", ".png")
        if not os.path.exists(IMG_FOLDER):
            if self.verbose:
                print(f"DEBUG: IMG_FOLDER does not exist: {IMG_FOLDER}")
            return img_commands
        for root, dirs, files in os.walk(IMG_FOLDER):
            imgs = [f for f in files if f.lower().endswith(supported_ext)]
            if root == IMG_FOLDER:
                for file in imgs:
                    name = os.path.splitext(file)[0]
                    img_commands.add(name.lower())
            else:
                folder_name = os.path.basename(root).lower()
                if imgs:
                    img_commands.add(folder_name)
                    for file in imgs:
                        name = os.path.splitext(file)[0]
                        img_commands.add(name.lower())
        return img_commands