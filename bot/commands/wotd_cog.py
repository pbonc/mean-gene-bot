import json
import os
import random
import re
from twitchio.ext import commands
from bot.overlay_server import broadcast_overlay_message

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

WOTD_STATE_FILE = os.path.join(DATA_DIR, "wotd_state.json")
WOTD_GENERIC_FILE = os.path.join(DATA_DIR, "wotd_generic_library.json")
WOTD_STREAM_FILE = os.path.join(DATA_DIR, "wotd_stream_terms.json")
EMOTES_FILE = os.path.join(DATA_DIR, "channel_emotes.json")
WOTD_SHOWER_COUNT = 1260
WOTD_SHOWER_DURATION_MS = 15000
WOTD_SHOWER_EMOJIS = [
    "🎉", "✨", "🔥", "💥", "🌟", "⚡", "🎊", "🎈", "💫", "🪩",
    "🥳", "😎", "🤖", "👑", "🚀", "🧨", "🌈", "🍀", "💎", "🔔",
    "🦄", "🎯", "🕹️", "🎵", "🌊", "🍕", "🍩", "🍿", "🧃", "🐉",
]


class WOTDState:
    def __init__(self):
        self.is_active = False
        self.current_word = None
        self.prize_value = 5
        self.stream_bias_percent = 15
        self.winner = None
        self.last_word = None
        self.last_entries = None
        self.load()

    def load(self):
        """Load state from file"""
        if os.path.exists(WOTD_STATE_FILE):
            with open(WOTD_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.is_active = data.get("is_active", False)
            self.current_word = data.get("current_word", None)
            self.prize_value = data.get("prize_value", 5)
            self.stream_bias_percent = data.get("stream_bias_percent", 15)
            self.winner = data.get("winner", None)
            self.last_word = data.get("last_word", None)
            self.last_entries = data.get("last_entries", None)
        else:
            self.save()

    def save(self):
        """Save state to file"""
        data = {
            "is_active": self.is_active,
            "current_word": self.current_word,
            "prize_value": self.prize_value,
            "stream_bias_percent": self.stream_bias_percent,
            "winner": self.winner,
            "last_word": self.last_word,
            "last_entries": self.last_entries
        }
        with open(WOTD_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def load_generic_terms(self):
        """Load generic library terms"""
        if os.path.exists(WOTD_GENERIC_FILE):
            with open(WOTD_GENERIC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("terms", [])
        return []

    def load_stream_terms(self):
        """Load stream-specific terms"""
        if os.path.exists(WOTD_STREAM_FILE):
            with open(WOTD_STREAM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("terms", [])
        return []

    def save_stream_terms(self, terms):
        """Save stream-specific terms"""
        data = {"terms": terms}
        with open(WOTD_STREAM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def add_stream_term(self, term):
        """Add a term to stream library"""
        terms = self.load_stream_terms()
        term_lower = term.lower()
        if term_lower not in [t.lower() for t in terms]:
            terms.append(term)
            self.save_stream_terms(terms)
            return True, f"Added '{term}' to stream term library."
        return False, f"'{term}' already exists in stream library."

    def remove_stream_term(self, term):
        """Remove a term from stream library"""
        terms = self.load_stream_terms()
        term_lower = term.lower()
        original_count = len(terms)
        terms = [t for t in terms if t.lower() != term_lower]
        if len(terms) < original_count:
            self.save_stream_terms(terms)
            return True, f"Removed '{term}' from stream library."
        return False, f"'{term}' not found in stream library."

    def select_word(self):
        """Select a word from the stream-specific library only"""
        stream_terms = self.load_stream_terms()
        if not stream_terms:
            raise ValueError("No stream terms available")

        word = random.choice(stream_terms)
        source = "stream"

        self.current_word = word
        self.is_active = True
        self.winner = None
        self.save()
        return word, source

    def check_message_for_word(self, message):
        """Check if message contains the word (case insensitive, whole word match)"""
        if not self.is_active or not self.current_word:
            return False
        
        # Use word boundary regex for whole word matching
        pattern = r'\b' + re.escape(self.current_word) + r'\b'
        return bool(re.search(pattern, message, re.IGNORECASE))

    def award_winner(self, username):
        """Award the winner and deactivate WOTD"""
        if not self.is_active:
            return False, None
        
        word = self.current_word
        prize = self.prize_value
        self.last_word = word
        self.last_entries = prize
        
        self.winner = username
        self.is_active = False
        self.current_word = None
        self.prize_value = 5  # Reset prize
        self.stream_bias_percent = 15  # Reset bias
        self.save()
        
        return True, (word, prize)

    def close_without_winner(self):
        """Close WOTD without winner, increase prize and bias"""
        if not self.is_active:
            return False, None
        
        word = self.current_word
        old_prize = self.prize_value
        self.last_word = word
        self.last_entries = old_prize
        
        self.is_active = False
        self.current_word = None
        self.prize_value += 5  # Increase for next time
        self.stream_bias_percent = min(100, self.stream_bias_percent + 10)  # Increase bias, cap at 100%
        self.winner = None
        self.save()
        
        return True, (word, old_prize, self.prize_value)

    def reset_for_stream_start(self):
        """Clear the prior WOTD and add five entries to its carried prize."""
        carried_prize = max(self.prize_value, self.last_entries or 0)
        previous = {
            "word": self.current_word or self.last_word,
            "entries": carried_prize,
            "was_active": self.is_active,
        }
        self.is_active = False
        self.current_word = None
        self.prize_value = carried_prize + 5
        self.stream_bias_percent = 15
        self.winner = None
        self.last_word = None
        self.last_entries = None
        self.save()
        previous["next_entries"] = self.prize_value
        return previous


class WOTDCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = WOTDState()

    def load_emotes(self):
        """Load emotes from channel_emotes.json"""
        if os.path.exists(EMOTES_FILE):
            try:
                with open(EMOTES_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("all_emotes", [])
            except Exception as e:
                print(f"[WOTD] Error loading emotes: {e}")
        return []

    def generate_emote_shower_tokens(self, count=60):
        """Generate hardcoded non-Twitch emoji tokens for on-screen shower effect."""
        safe_count = max(60, min(3000, int(count)))
        tokens = [random.choice(WOTD_SHOWER_EMOJIS) for _ in range(safe_count)]
        return tokens if tokens else None

    @commands.command(name="wotdtest")
    async def wotdtest_command(self, ctx):
        """Trigger the WOTD overlay emote shower for testing."""
        if not ctx.author.is_mod:
            await ctx.send("❌ Only mods can use this command.")
            return

        emote_tokens = self.generate_emote_shower_tokens(count=WOTD_SHOWER_COUNT)
        if not emote_tokens:
            await ctx.send("No emotes available for WOTD effect test.")
            return

        await broadcast_overlay_message({
            "type": "emote_shower",
            "emotes": emote_tokens,
            "count": WOTD_SHOWER_COUNT,
            "duration": WOTD_SHOWER_DURATION_MS,
        })
        await ctx.send("WOTD overlay effect test fired.")

    @commands.command(name="wotd")
    async def wotd_command(self, ctx, *args):
        """Word of the Day commands"""
        if not args:
            # Show status
            if self.state.is_active:
                await ctx.send(f"📖 Word of the Day is ACTIVE! First to say it wins {self.state.prize_value} raffle entries!")
            else:
                await ctx.send(f"📖 Word of the Day is not active. Next prize: {self.state.prize_value} entries.")
            return

        subcommand = args[0].lower()

        # Mod-only commands
        if subcommand == "add":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can add terms.")
                return
            
            if len(args) < 2:
                await ctx.send("Usage: !wotd add \"term or phrase\"")
                return
            
            term = " ".join(args[1:]).strip('"').strip("'")
            success, msg = self.state.add_stream_term(term)
            await ctx.send(msg)
            return

        if subcommand == "remove":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can remove terms.")
                return
            
            if len(args) < 2:
                await ctx.send("Usage: !wotd remove \"term\"")
                return
            
            term = " ".join(args[1:]).strip('"').strip("'")
            success, msg = self.state.remove_stream_term(term)
            await ctx.send(msg)
            return

        if subcommand == "list":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can view the term list.")
                return
            
            terms = self.state.load_stream_terms()
            if not terms:
                await ctx.send("No custom stream terms added yet.")
            else:
                term_list = ", ".join(f'"{t}"' for t in terms[:10])
                if len(terms) > 10:
                    term_list += f" ... and {len(terms) - 10} more"
                await ctx.send(f"Stream terms ({len(terms)} total): {term_list}")
            return

        if subcommand == "start":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can start WOTD.")
                return
            
            if self.state.is_active:
                await ctx.send("❌ Word of the Day is already active! Use !wotd close to end it first.")
                return
            
            try:
                word, source = self.state.select_word()
            except ValueError:
                await ctx.send("❌ No stream WOTD terms are available. Add some with !wotd add \"term\" first.")
                return
            print(f"[WOTD] Selected: \"{word}\" ({source} library) - Prize: {self.state.prize_value} entries")
            await ctx.send(f"📖 Word of the Day is now ACTIVE! First to say it wins {self.state.prize_value} raffle entries!")
            return

        if subcommand == "close":
            if not ctx.author.is_mod:
                await ctx.send("❌ Only mods can close WOTD.")
                return
            
            if not self.state.is_active:
                await ctx.send("❌ Word of the Day is not active.")
                return
            
            success, result = self.state.close_without_winner()
            if success:
                word, old_prize, new_prize = result
                await ctx.send(f"📖 Nobody found the Word of the Day: \"{word}\". Prize increases from {old_prize} to {new_prize} entries for next WOTD!")
            return

        await ctx.send("Usage: !wotd [add/remove/list/start/close] or just !wotd for status")

    @commands.Cog.event()
    async def event_message(self, message):
        """Listen for the word in chat"""
        if message.echo:
            return
        
        if not self.state.is_active:
            return
        
        username = message.author.name
        content = message.content
        
        if self.state.check_message_for_word(content):
            success, result = self.state.award_winner(username)
            if success:
                word, prize = result
                # Award raffle entries
                raffle_cog = self.bot.get_cog("RaffleCog")
                if raffle_cog:
                    raffle_cog.state.add_entries(username, prize)

                # Send main announcement
                await message.channel.send(f"🎉 @{username} found the Word of the Day: \"{word}\"! +{prize} raffle entries!")

                # Trigger overlay emote shower instead of chat spam
                emote_tokens = self.generate_emote_shower_tokens(count=70)
                if emote_tokens:
                    await broadcast_overlay_message({
                        "type": "emote_shower",
                        "emotes": emote_tokens,
                        "count": WOTD_SHOWER_COUNT,
                        "duration": WOTD_SHOWER_DURATION_MS,
                    })

                print(f"[WOTD] Winner: {username} found \"{word}\" - Awarded {prize} entries + OVERLAY EMOTE SHOWER!")


def prepare(bot):
    if not bot.get_cog("WOTDCog"):
        bot.add_cog(WOTDCog(bot))
