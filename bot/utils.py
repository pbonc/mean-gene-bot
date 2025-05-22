# bot/utils.py

import discord

async def safe_get_guild(bot: discord.Client, guild_id: int) -> discord.Guild | None:
    """Attempts to get a guild by ID, falling back to fetch if needed."""
    guild = bot.get_guild(guild_id)
    if guild:
        return guild
    try:
        return await bot.fetch_guild(guild_id)
    except Exception as e:
        print(f"⚠️ Could not retrieve guild {guild_id}: {e}")
        return None

async def safe_get_channel(bot: discord.Client, guild: discord.Guild, name=None, channel_id=None):
    """Attempts to get a text channel by name or ID, using local and API lookup."""
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            return channel
        try:
            return await bot.fetch_channel(channel_id)
        except Exception as e:
            print(f"⚠️ Could not fetch channel {channel_id}: {e}")
            return None

    if name:
        for ch in guild.text_channels:
            if ch.name == name:
                return ch

    print(f"⚠️ Channel not found by name='{name}' or id='{channel_id}'")
    return None
