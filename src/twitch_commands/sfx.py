import os
import random
import asyncio
from twitchio.ext import commands
from playsound import playsound  # Or your preferred sound playback method

SFX_ROOT = os.path.join(os.path.dirname(__file__), "..", "sfx")

class SFXCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.event()
    async def event_message(self, message):
        if not message.content or not message.content.startswith("!"):
            return

        command = message.content[1:].strip().lower()

        # 1. Check for direct file: src/sfx/filename.mp3
        file_path = os.path.join(SFX_ROOT, f"{command}.mp3")
        if os.path.isfile(file_path):
            await self._play_and_ack(file_path, message, f"!{command}")
            return

        # 2. Check subfolders: src/sfx/*/filename.mp3
        subfolder_match = None
        for root, dirs, files in os.walk(SFX_ROOT):
            if root == SFX_ROOT:
                continue  # Skip top-level, already checked
            for fn in files:
                if fn.lower() == f"{command}.mp3":
                    file_path = os.path.join(root, fn)
                    await self._play_and_ack(file_path, message, f"!{command}")
                    return

        # 3. If command matches a subfolder, pick a random mp3 in it
        subfolder_path = os.path.join(SFX_ROOT, command)
        if os.path.isdir(subfolder_path):
            mp3s = [f for f in os.listdir(subfolder_path) if f.lower().endswith(".mp3")]
            if mp3s:
                chosen = random.choice(mp3s)
                chosen_path = os.path.join(subfolder_path, chosen)
                # The command to play this file directly
                chosen_cmd = f"!{os.path.splitext(chosen)[0]}"
                await self._play_and_ack(chosen_path, message, chosen_cmd, announce=True)
                return

        # 4. Not found, ignore or print a message
        # await message.channel.send(f"No SFX found for '{command}'.")

    async def _play_and_ack(self, file_path, message, cmd, announce=False):
        # Play sound (consider running in executor if non-async)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, playsound, file_path)
        if announce:
            await message.channel.send(f"Played random sound: {os.path.basename(file_path)} — use `{cmd}` to play it directly.")

def prepare(bot):
    bot.add_cog(SFXCog(bot))