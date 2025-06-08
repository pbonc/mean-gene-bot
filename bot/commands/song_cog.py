import os
from twitchio.ext import commands

# Path to the current song file (update this if your path changes)
SONG_FILE = r"C:\Users\darji\AppData\Roaming\Streamlabs\Streamlabs Chatbot\Services\Twitch\Files\currentsong.txt"

class SongCog(commands.Cog):
    """
    Cog for displaying the currently playing song using !song.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.file_path = SONG_FILE

    @commands.command(name="song", aliases=["currentsong"])
    async def song_cmd(self, ctx: commands.Context):
        """
        Display the currently playing song.
        Usage: !song
        """
        if not os.path.isfile(self.file_path):
            await ctx.send("Song: Song file not found.")
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                song = f.read().strip()
        except Exception as e:
            await ctx.send("Song: Error reading song file.")
            return

        if song:
            await ctx.send(f"Song: {song}")
        else:
            await ctx.send("Song: No song currently playing.")

def prepare(bot: commands.Bot):
    """
    Adds the SongCog to the bot.
    """
    if not bot.get_cog("SongCog"):
        bot.add_cog(SongCog(bot))