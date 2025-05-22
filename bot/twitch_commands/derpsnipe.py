import os
import asyncio
import re
import traceback
from twitchio.ext import commands

DERP_FILE = "bot/data/derpism.txt"
MAX_ATTEMPTS = 3
DELAY_BETWEEN_ENTRIES = 3.0

class DerpSnipe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.response_queue = asyncio.Queue()
        print("📸 DerpSnipe Cog initialized")

    @commands.command(name="derpsnipe")
    async def derpsnipe(self, ctx: commands.Context):
        if ctx.author.name.lower() != "iamdar":
            return

        await ctx.send("🎯 Starting derpism scrape...")
        print("🚀 derpsnipe started")

        derps = []
        if os.path.exists(DERP_FILE):
            with open(DERP_FILE, "r", encoding="utf-8") as f:
                derps = [line.strip() for line in f if line.strip()]
            print(f"📥 Loaded {len(derps)} derpisms.")
        else:
            print("📄 derpism.txt not found. Starting fresh.")
            os.makedirs(os.path.dirname(DERP_FILE), exist_ok=True)

        index = len(derps)
        print(f"🔍 Starting at index {index}")

        while True:
            success = await self.attempt_fetch_and_save(ctx, index, derps)
            if not success:
                print(f"❌ Derpism #{index} failed after {MAX_ATTEMPTS} attempts. Stopping.")
                await ctx.send(f"❌ Failed to get Derpism #{index}. Derpsnipe aborted.")
                break
            index += 1
            await asyncio.sleep(DELAY_BETWEEN_ENTRIES)

        await ctx.send("✅ Derpsnipe complete!")

    async def attempt_fetch_and_save(self, ctx, index, derps):
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"📤 Sending !derpism {index} (Attempt {attempt})")
            await ctx.send(f"!derpism {index}")
            try:
                msg = await asyncio.wait_for(self.response_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                print("⚠️ Timeout waiting for response.")
                continue
            except Exception as e:
                print("💥 Unhandled exception waiting for response_queue:")
                traceback.print_exc()
                continue

            match = re.match(rf"Derpism #({index}):\s+\"?(.+?)\"?(?:\s+@.+)?$", msg.content)
            if not match:
                print(f"❌ Could not parse: {msg.content}")
                continue

            text = match.group(2).strip()
            derps.append(text)
            print(f"✅ Parsed and added: {text}")

            try:
                with open(DERP_FILE, "w", encoding="utf-8") as f:
                    f.writelines(line + "\n" for line in derps)
                    f.flush()
                    os.fsync(f.fileno())
                with open(DERP_FILE, "r", encoding="utf-8") as verify:
                    lines = [line.strip() for line in verify if line.strip()]
                    if text in lines:
                        print("🧪 Verified entry written successfully.")
                        return True
                    else:
                        print("❌ Text not found after write.")
            except Exception as e:
                print("💥 Error writing or verifying file:")
                traceback.print_exc()

            await asyncio.sleep(1)

        return False

    @commands.Cog.event()
    async def event_message(self, msg):
        if msg.author.name.lower() == "botdar" and msg.content.startswith("Derpism #"):
            await self.response_queue.put(msg)


def prepare(bot: commands.Bot):
    if bot.get_cog("DerpSnipe"):
        return
    bot.add_cog(DerpSnipe(bot))