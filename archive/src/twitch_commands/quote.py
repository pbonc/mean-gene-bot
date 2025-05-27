import os
import json
import random
from datetime import datetime
from twitchio.ext import commands

QUOTES_FILE = "bot/data/quotes.json"

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
        print(f"🧪 !quote triggered by {ctx.author.name}")
        parts = ctx.message.content.strip().split(" ", 2)

        # Handle: !quote add <quote> <user>
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

        # Handle: !quote <id>
        if len(parts) > 1 and parts[1].isdigit():
            quote_id = parts[1]
            quote = self.quotes.get(quote_id)
            if not quote:
                await ctx.send(f"❌ Quote #{quote_id} not found.")
                return
        else:
            if not self.quotes:
                await ctx.send("📭 No quotes available.")
                return
            quote_id = random.choice(list(self.quotes.keys()))
            quote = self.quotes[quote_id]

        try:
            dt = datetime.strptime(quote["date"], "%m/%d/%Y")
            formatted_date = dt.strftime("%B %d, %Y")
        except ValueError:
            formatted_date = quote["date"]

        await ctx.send(f'Quote #{quote_id}: "{quote["text"]}" {quote["user"]} [{quote["context"]}] [{formatted_date}]')

    @commands.command(name="myquotes")
    async def myquotes(self, ctx: commands.Context):
        print(f"🧪 !myquotes triggered by {ctx.author.name}")
        user = ctx.author.name.lower()
        parts = ctx.message.content.strip().split(" ")

        try:
            user_quotes = {
                qid: q for qid, q in self.quotes.items()
                if q["user"].lstrip("@").lower() == user
            }

            if not user_quotes:
                await ctx.send(f"📭 No quotes found for {ctx.author.name}.")
                return

            if len(parts) > 1 and parts[1].lower() == "random":
                qid, quote = random.choice(list(user_quotes.items()))
                try:
                    dt = datetime.strptime(quote["date"], "%m/%d/%Y")
                    formatted_date = dt.strftime("%B %d, %Y")
                except ValueError:
                    formatted_date = quote["date"]

                await ctx.send(f'Quote #{qid}: "{quote["text"]}" {quote["user"]} [{quote["context"]}] [{formatted_date}]')
            else:
                total = len(user_quotes)
                sample_ids = random.sample(list(user_quotes.keys()), min(10, total))
                formatted_ids = ", ".join(sorted(sample_ids, key=lambda x: int(x)))
                await ctx.send(f'📘 {ctx.author.name}, you have {total} quotes including: {formatted_ids}')
        except Exception as e:
            print(f"❌ Error in !myquotes: {e}")
            await ctx.send("⚠️ Something went wrong while fetching your quotes.")

def prepare(bot: commands.Bot):
    print("🧠 Preparing QuoteCommand cog...")
    if bot.get_cog("QuoteCommand"):
        print("⚠️ QuoteCommand already loaded, skipping.")
        return
    bot.add_cog(QuoteCommand(bot))
