import os
from twitchio.ext import commands

# Change this to your actual current song file path
SONG_FILE = r"C:\Users\darji\AppData\Roaming\Streamlabs\Streamlabs Chatbot\Services\Twitch\Files\currentsong.txt"

class Song(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = SONG_FILE

    @commands.command(name="song")
    async def song_command(self, ctx: commands.Context):
        if not os.path.isfile(self.file_path):
            await ctx.send("Song : Song file not found.")
            return
        with open(self.file_path, "r", encoding="utf-8") as f:
            song = f.read().strip()
        if song:
            await ctx.send(f"Song : {song}")
        else:
            await ctx.send("Song : No song currently playing.")

def prepare(bot: commands.Bot):
    bot.add_cog(Song(bot))