"""Twitch adapter for the queued Moonbase/DECTalk-compatible TTS service."""

import logging

from twitchio.ext import commands

from bot.tts_service import get_tts_service

logger = logging.getLogger("tts")


def _is_mod(author):
    return bool(getattr(author, "is_mod", False) or getattr(author, "is_broadcaster", False))


def _identity(author):
    login = str(getattr(author, "name", "unknown"))
    user_id = str(getattr(author, "id", "") or "")
    display = str(getattr(author, "display_name", "") or login)
    return user_id, login.casefold(), display


async def _speak_text_with_voice(message: str, voice_index: int | None = None):
    """Compatibility adapter retained for GameWatch TTS calls."""
    service = get_tts_service()
    accepted, _ = service.accept("system:gamewatch", "gamewatch", "GameWatch", message, True)
    return accepted, service.backend.name, voice_index


class TtsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, service=None):
        self.bot = bot
        self.service = service or get_tts_service()

    @commands.command(name="tts")
    async def tts(self, ctx, *args):
        """Queue DECTalk-compatible speech or grant a viewer token."""
        user_id, login, display = _identity(ctx.author)
        moderator = _is_mod(ctx.author)
        if not args:
            await ctx.send("Usage: !tts <message> | !tts token @username")
            return

        if args[0].casefold() == "token":
            if not moderator:
                await ctx.send("Only moderators or the broadcaster can grant TTS tokens.")
                return
            if len(args) != 2 or not args[1].startswith("@") or len(args[1]) < 2:
                await ctx.send("Usage: !tts token @username")
                return
            target = args[1][1:].casefold()
            balance = self.service.tokens.grant(target)
            logger.info("[TTS] Token granted by=%s target=%s balance=%d", login, target, balance)
            await ctx.send(f"{args[1][1:]} has been granted 1 TTS token. Balance: {balance}.")
            return

        if args[0].casefold() in {"voices", "status"}:
            if not moderator:
                await ctx.send("TTS requires moderator access or a TTS token.")
                return
            await ctx.send(f"TTS backend: {self.service.backend.name} | Queue: {self.service.queue.qsize()}/{self.service.config.max_queue_depth}")
            return

        token_balance = self.service.tokens.balance(user_id, login)
        if not moderator and token_balance < 1:
            await ctx.send("TTS requires moderator access or a TTS token.")
            return

        # TwitchIO has already split command arguments; rejoining preserves all DECTalk
        # control tokens and phoneme syntax, without filtering or escaping them.
        message = " ".join(args).strip()
        user_key = f"id:{user_id}" if user_id else f"login:{login}"
        accepted, response = self.service.accept(user_key, login, display, message, moderator)
        if not accepted:
            await ctx.send(response)
            return
        if not moderator:
            if not self.service.tokens.consume(user_id, login):
                logger.error("[TTS] Accepted request had no consumable token user=%s", login)
            else:
                logger.info("[TTS] Token consumed user=%s remaining=%d", login, self.service.tokens.balance(user_id, login))
            await ctx.send(f"TTS queued. Tokens remaining: {self.service.tokens.balance(user_id, login)}.")


def prepare(bot: commands.Bot):
    if not bot.get_cog("TtsCog"):
        bot.add_cog(TtsCog(bot))
    print("[COG] TtsCog loaded")
