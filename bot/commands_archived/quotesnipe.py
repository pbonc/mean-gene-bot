import os
import json
import asyncio
import re
import traceback
from twitchio.ext import commands

QUOTES_FILE = "bot/data/quotes.json"
MAX_ATTEMPTS_WITHOUT_RESPONSE = 5
DELAY_BETWEEN_QUOTES = 3.0

class QuoteSnipe(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.response_queue = asyncio.Queue()
        print("📸 QuoteSnipe Cog initialized")

    @commands.command(name="quotesnipe")
    async def quotesnipe(self, ctx: commands.Context):
        if ctx.author.name.lower() != "iamdar":
            return

        await ctx.send("🎯 Starting quote scrape...")
        print("🚀 quotesnipe started")

        quotes = {}
        try:
            if os.path.exists(QUOTES_FILE):
                print(f"📄 Opening existing quotes file: {QUOTES_FILE}")
                with open(QUOTES_FILE, "r", encoding="utf-8") as f:
                    quotes = json.load(f)
                print(f"📥 Loaded {len(quotes)} quotes.")
            else:
                print("📄 quotes.json does not exist, starting fresh.")
        except Exception:
            print("❌ Error loading quotes.json:")
            traceback.print_exc()

        # Identify missing quote IDs
        if quotes:
            known_ids = set(map(int, quotes.keys()))
            max_known = max(known_ids)
        else:
            known_ids = set()
            max_known = -1

        missing_ids = sorted(set(range(max_known + 1)) - known_ids)
        print(f"🔍 Missing quote IDs: {missing_ids[:10]} ... (total: {len(missing_ids)})")

        no_response_count = 0
        current_index = 0

        # First recover missing known quotes
        for quote_id in missing_ids:
            if no_response_count >= MAX_ATTEMPTS_WITHOUT_RESPONSE:
                print("🛑 Max no-response count hit during recovery. Ending scrape.")
                break
            success = await self.fetch_quote(ctx, quote_id, quotes)
            if not success:
                no_response_count += 1
            else:
                no_response_count = 0
            await asyncio.sleep(DELAY_BETWEEN_QUOTES)

        # Then attempt new ones incrementally until 5 strikes
        current_index = max_known + 1
        no_response_count = 0

        while no_response_count < MAX_ATTEMPTS_WITHOUT_RESPONSE:
            print(f"📨 Requesting new quote #{current_index}")
            success = await self.fetch_quote(ctx, current_index, quotes)
            if not success:
                no_response_count += 1
            else:
                no_response_count = 0
            current_index += 1
            await asyncio.sleep(DELAY_BETWEEN_QUOTES)

        print("✅ Quote scrape completed.")
        await ctx.send("✅ Quote snipe completed! Check logs for summary.")

    async def fetch_quote(self, ctx, quote_id, quotes):
        if str(quote_id) in quotes:
            print(f"🟡 Quote #{quote_id} already exists, skipping.")
            return True

        await ctx.send(f"!quote {quote_id}")
        try:
            print(f"⏳ Waiting for quote #{quote_id}...")
            response = await asyncio.wait_for(self.response_queue.get(), timeout=5.0)
            print(f"✅ Received quote #{quote_id}")
        except asyncio.TimeoutError:
            print(f"⚠️ Timeout waiting for quote #{quote_id}")
            return False

        print(f"📩 Raw content: {response.content}")
        print("🔎 Attempting to parse...")

        quote_match = re.match(
            r"Quote #(\d+):\s+\"?(.*?)\"?\s*@(.+?) \[(.+?)\] \[(\d{2})(\d{2})(\d{4})\]",
            response.content
        )

        if not quote_match:
            print(f"⚠️ Could not parse quote #{quote_id}")
            return False

        quote_id_parsed, text, user, context, dd, mm, yyyy = quote_match.groups()
        quote_data = {
            "text": text.strip(),
            "user": user.strip(),
            "context": context.strip(),
            "date": f"{mm}/{dd}/{yyyy}"
        }

        quotes[quote_id_parsed] = quote_data
        print(f"💾 Writing quote #{quote_id_parsed} to file: {quote_data}")

        try:
            with open(QUOTES_FILE, "w", encoding="utf-8") as f:
                json.dump(quotes, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            print(f"✅ Successfully wrote quote #{quote_id_parsed}")
            return True
        except Exception:
            print(f"❌ File write failed for quote #{quote_id_parsed}")
            traceback.print_exc()
            return False

    @commands.Cog.event()
    async def event_message(self, msg):
        if msg.author.name.lower() == "botdar" and msg.content.startswith("Quote #"):
            await self.response_queue.put(msg)

def prepare(bot: commands.Bot):
    if bot.get_cog("QuoteSnipe"):
        print("⚠️ QuoteSnipe already loaded, skipping.")
        return
    bot.add_cog(QuoteSnipe(bot))
