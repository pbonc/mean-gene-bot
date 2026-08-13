import asyncio
import logging
import shlex

from twitchio.ext import commands

from bot.giveaway_state import GiveawayState
from bot.overlay_server import broadcast_overlay_message


LOGGER = logging.getLogger("giveaway")
REMINDER_SECONDS = 300
USAGE = '!giveaway open "prize" "word or !sfx" | !giveaway close | !giveaway draw | !giveaway status'


def parse_giveaway_command(content):
    try:
        parts = shlex.split(str(content or ""))
    except ValueError as exc:
        raise ValueError("Prize and entry phrase must use matching quotes.") from exc
    if parts and parts[0].casefold().lstrip("!") == "giveaway":
        parts = parts[1:]
    return parts


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = GiveawayState()
        self.channel = None
        self.reminder_task = None
        if self.manager.state.get("is_open"):
            self._start_reminders()
        bot.loop.create_task(self._startup_broadcast())

    async def _startup_broadcast(self):
        await asyncio.sleep(1)
        await self._broadcast()

    async def _broadcast(self, animate=False):
        await broadcast_overlay_message(self.manager.payload(animate=animate))

    def _start_reminders(self):
        if self.reminder_task and not self.reminder_task.done():
            self.reminder_task.cancel()
        self.reminder_task = self.bot.loop.create_task(self._reminders())

    def _stop_reminders(self):
        if self.reminder_task and not self.reminder_task.done():
            self.reminder_task.cancel()
        self.reminder_task = None

    async def _reminders(self):
        while self.manager.state.get("is_open"):
            await asyncio.sleep(REMINDER_SECONDS)
            if not self.manager.state.get("is_open"):
                return
            channel = self.channel
            if not channel:
                channels = list(getattr(self.bot, "connected_channels", None) or [])
                channel = channels[0] if channels else None
            if channel:
                await channel.send(
                    f'Giveaway reminder: enter to win "{self.manager.state["prize"]}" by saying '
                    f'"{self.manager.state["entry_phrase"]}" in chat! '
                    f'{len(self.manager.state["entrants"])} entered so far.'
                )

    @commands.command(name="giveaway")
    async def giveaway_command(self, ctx):
        try:
            parts = parse_giveaway_command(ctx.message.content)
        except ValueError as exc:
            await ctx.send(str(exc))
            return
        action = parts[0].casefold() if parts else "status"
        if action in ("open", "close", "draw") and not (
            getattr(ctx.author, "is_mod", False) or getattr(ctx.author, "is_broadcaster", False)
        ):
            await ctx.send("Only moderators or the broadcaster can manage giveaways.")
            return
        try:
            if action == "open":
                if len(parts) != 3:
                    raise ValueError(USAGE)
                self.manager.open(parts[1], parts[2])
                self.channel = ctx.channel
                self._start_reminders()
                await self._broadcast()
                await ctx.send(
                    f'Giveaway open for "{parts[1]}"! Enter by saying "{parts[2]}" in chat. '
                    "One entry per person."
                )
            elif action == "close":
                self.manager.close()
                self._stop_reminders()
                await self._broadcast()
                await ctx.send(f'Giveaway closed with {len(self.manager.state["entrants"])} entrants. Use !giveaway draw.')
            elif action == "draw":
                winner = self.manager.draw()
                await self._broadcast(animate=True)
                await ctx.send(f'Drawing {len(self.manager.state["entrants"])} names for "{self.manager.state["prize"]}"...')
                await asyncio.sleep(8)
                await ctx.send(f'Congratulations @{winner}! You won "{self.manager.state["prize"]}"!')
            elif action in ("status", "info"):
                state = self.manager.state
                if not state.get("prize"):
                    await ctx.send("No giveaway is configured. " + USAGE)
                else:
                    status = "open" if state.get("is_open") else "closed"
                    await ctx.send(
                        f'Giveaway is {status}: "{state["prize"]}" | Enter with "{state["entry_phrase"]}" | '
                        f'{len(state["entrants"])} entrants' + (f' | Winner: @{state["winner"]}' if state.get("winner") else "")
                    )
            else:
                await ctx.send(USAGE)
        except ValueError as exc:
            await ctx.send(str(exc))

    @commands.Cog.event()
    async def event_message(self, message):
        if getattr(message, "echo", False) or not getattr(message, "author", None):
            return
        if self.manager.enter(message.author.name, message.content):
            self.channel = message.channel
            await self._broadcast()
            await message.channel.send(
                f'@{message.author.name}, you are entered to win "{self.manager.state["prize"]}"! '
                f'{len(self.manager.state["entrants"])} total entrants.'
            )

    def cog_unload(self):
        self._stop_reminders()


def prepare(bot):
    if not bot.get_cog("GiveawayCog"):
        bot.add_cog(GiveawayCog(bot))
