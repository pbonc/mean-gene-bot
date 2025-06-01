import os
import json
import random
from datetime import datetime
from twitchio.ext import commands

QUOTES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "quotes.json")

class QuoteCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.quotes = {}
        self.load_quotes()
        print("📜 QuoteCommand loaded")

    def load_quotes(self):
        if os.path.exists(QUOTES_FILE):
            with open(QUOTES_FILE, "r", encoding="utf-8") as f:
                self.quotes = json.load(f)
        else:
            self.quotes = {}

    def save_quotes(self):
        with open(QUOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.quotes, f, indent=2)

    @commands.command(name="quote")
    async def quote(self, ctx: commands.Context):
        parts = ctx.message.content.strip().split(" ", 2)

        # !quote add <quote> <user>
        if len(parts) > 1 and parts[1].lower() == "add":
            if not ctx.author.is_mod:
                await ctx.send("⛔ Only mods can add quotes.")
                return

            content = ctx.message.content.strip()
            prefix = "!quote add"
            if not content.lower().startswith(prefix):
                await ctx.send("⚠️ Usage: !quote add <quote> <user>")
                return

            raw = content[len(prefix):].strip()
            if not raw or " " not in raw:
                await ctx.send("⚠️ Usage: !quote add <quote> <user>")
                return

            *quote_parts, user = raw.split()
            quote_text = " ".join(quote_parts).strip()
            if not quote_text or not user:
                await ctx.send("⚠️ Both quote and user must be provided.")
                return

            quote_id = str(max(map(int, self.quotes.keys()), default=-1) + 1)
            today = datetime.utcnow().strftime("%m/%d/%Y")

            self.quotes[quote_id] = {
                "text": quote_text,
                "user": user,
                "context": "Unknown",
                "date": today
            }

            self.save_quotes()
            await ctx.send(f"✅ Quote #{quote_id} added!")
            return

        # !quote X (display quote #X)
        if len(parts) > 1 and parts[1].isdigit():
            quote_id = parts[1]
            quote = self.quotes.get(quote_id)
            if not quote:
                await ctx.send(f"❌ Quote #{quote_id} not found.")
                return
        else:
            # !quote (random)
            if not self.quotes:
                await ctx.send("📭 No quotes available.")
                return
            quote_id = random.choice(list(self.quotes.keys()))
            quote = self.quotes[quote_id]

        try:
            dt = datetime.strptime(quote["date"], "%m/%d/%Y")
            formatted_date = dt.strftime("%B %d, %Y")
        except Exception:
            formatted_date = quote["date"]

        await ctx.send(
            f'Quote #{quote_id}: "{quote["text"]}" {quote["user"]} [{quote.get("context", "Unknown")}] [{formatted_date}]'
        )

    @commands.command(name="myquotes")
    async def myquotes(self, ctx: commands.Context):
        user = ctx.author.name.lower()
        # Quotes are attributed by "user" field, case-insensitive, ignore leading @ if present
        user_quotes = {
            qid: q for qid, q in self.quotes.items()
            if q.get("user", "").lstrip("@").lower() == user
        }

        total = len(user_quotes)
        if total == 0:
            await ctx.send(f"📭 No quotes found for {ctx.author.name}.")
            return

        # If 15 or fewer, show all; else, show a random sample of 15 IDs
        sample_count = min(15, total)
        if total <= 15:
            sample_ids = sorted(user_quotes.keys(), key=lambda x: int(x))
        else:
            sample_ids = random.sample(list(user_quotes.keys()), sample_count)
            sample_ids = sorted(sample_ids, key=lambda x: int(x))

        formatted_ids = ", ".join(sample_ids)
        await ctx.send(f'📘 {ctx.author.name}, you have {total} quotes, including: {formatted_ids}')

def prepare(bot: commands.Bot):
    print("🧠 Preparing QuoteCommand cog...")
    if bot.get_cog("QuoteCommand"):
        print("⚠️ QuoteCommand already loaded, skipping.")
        return
    bot.add_cog(QuoteCommand(bot))