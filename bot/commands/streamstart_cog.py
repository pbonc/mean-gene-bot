"""Owner-only orchestration for beginning a stream cleanly after restarts."""

import asyncio
import logging
import os

from twitchio.ext import commands


LOGGER = logging.getLogger("streamstart")
OWNER_LOGIN = "iamdar"
OWNER_ID = (os.getenv("STREAMSTART_OWNER_ID") or "").strip()
STARTUP_SONGS = (33, 99, 6, 668)
ZAP_MINUTES = 20


def is_stream_owner(author):
    """Prefer an immutable configured Twitch ID, otherwise require iAmDar's login."""
    if OWNER_ID:
        return str(getattr(author, "id", "")) == OWNER_ID
    return str(getattr(author, "name", "")).casefold() == OWNER_LOGIN


class StreamStartCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._start_lock = asyncio.Lock()

    @commands.command(name="streamstart")
    async def streamstart_command(self, ctx, entries_per_chat=None):
        if not is_stream_owner(ctx.author):
            await ctx.send("This command is restricted to iAmDar.")
            return
        try:
            entries = int(entries_per_chat)
            if entries < 1 or entries > 100:
                raise ValueError
        except (TypeError, ValueError):
            await ctx.send("Usage: !streamstart <raffle_entries_per_chat> (1-100)")
            return
        if self._start_lock.locked():
            await ctx.send("Stream startup is already running.")
            return

        raffle_cog = self.bot.get_cog("RaffleCog")
        wotd_cog = self.bot.get_cog("WOTDCog")
        song_cog = self.bot.get_cog("SongRequestCog")
        missing = [
            label for label, cog in (
                ("raffle", raffle_cog), ("WOTD", wotd_cog), ("SRX", song_cog)
            ) if cog is None
        ]
        if missing:
            await ctx.send(f"Stream startup aborted; unavailable feature(s): {', '.join(missing)}.")
            return

        async with self._start_lock:
            # Restart rather than merely start so crash-persisted ZAP state cannot block it.
            raffle_cog.state.stop_zap()
            zap_success, _ = raffle_cog.state.start_zap(ZAP_MINUTES)
            if not zap_success:
                await ctx.send("Stream startup aborted because ZAP could not be reset.")
                return

            raffle_cog.state.open_raffle(entries)
            previous_wotd = wotd_cog.state.reset_for_stream_start()

            previous_word = previous_wotd.get("word")
            previous_entries = previous_wotd.get("entries", 5)
            if previous_word:
                wotd_summary = f'Previous WOTD was "{previous_word}" for {previous_entries} entries.'
            else:
                wotd_summary = f"No active previous WOTD; its carried prize was {previous_entries} entries."
            await ctx.send(
                f"Stream startup: ZAP reset to {ZAP_MINUTES} minutes. "
                f"Raffle opened at {entries} entr{'y' if entries == 1 else 'ies'} per chatter. "
                f"{wotd_summary} WOTD reset to 5 entries."
            )

            queued = []
            failed = []
            for number in STARTUP_SONGS:
                before = len(song_cog.manager.current_queue)
                try:
                    await song_cog._handle_playlist_request(ctx, number, ctx.author.name)
                    if len(song_cog.manager.current_queue) > before:
                        queued.append(number)
                    else:
                        failed.append(number)
                except Exception:
                    LOGGER.exception("Failed to request startup SRX song #%s", number)
                    failed.append(number)

            result = f"Stream startup complete. SRX queued: {', '.join('#' + str(n) for n in queued) or 'none'}."
            if failed:
                result += f" Not queued (see earlier response/log): {', '.join('#' + str(n) for n in failed)}."
            await ctx.send(result)


def prepare(bot):
    if not bot.get_cog("StreamStartCog"):
        bot.add_cog(StreamStartCog(bot))
