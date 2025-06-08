import random
import logging
from twitchio.ext import commands

D20_RESPONSES = [
    "Fuck you, you weirdo!",
    "Even a broken clock would be ashamed to share your time zone.",
    "Your choices inspire regret in people who haven't even met you",
    "You are a walking cautionary tale. Entire civilizations would fall faster if they followed your example.",
    "You didn't just miss the mark—you vaporized the concept of aiming.",
    "A committee of raccoons in a trench coat would have done better!",
    "It’s impressive how confidently wrong you manage to be, consistently.",
    "There are storms with more emotional intelligence than you displayed.",
    "You meant well. Unfortunately, the execution was legally classified as a war crime.",
    "Honestly? Not the worst I’ve seen… but definitely memorable, in the way food poisoning is memorable.",
    "That was a bold choice. Not a good one—but bold.!",
    "You’re getting there! Just a couple dozen more attempts and you might even be proud of yourself.",
    "There was effort here. Flawed, chaotic effort—but it counts.",
    "You’ve got the right spirit—even if it looks like it drinks heavily.",
    "Honestly? You held your own. Not bad at all.",
    "Solid execution. There’s heart in it, and that matters.",
    "Graceful. Clever. Impactful. You brought something special",
    "Everyone in the room felt it—whatever it is, you’ve got it",
    "This wasn’t just good—it was inspiring. You lit a fire in the hearts of mortals.",
    "You are the golden standard by which all future actions will be judged. Legends will whisper your name with awe."
]

class D20Judgement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.logger = logging.getLogger("d20")

    @commands.command(name="d20")
    async def d20(self, ctx):
        roll = random.randint(1, 20)
        response = D20_RESPONSES[roll - 1]
        user = ctx.author.name
        msg = f"@{user}, you rolled a {roll}! {response}"
        await ctx.send(msg)
        self.logger.info(f"d20: {user} rolled {roll}")

def prepare(bot):
    if not bot.get_cog("D20Judgement"):
        bot.add_cog(D20Judgement(bot))