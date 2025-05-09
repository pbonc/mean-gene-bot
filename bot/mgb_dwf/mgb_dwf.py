import os
import sys
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))

# Files
ROSTER_FILE = "wrestlers.json"
PROMO_FILE = "promos_pending.json"

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Debug Mode Setup ---
DEBUG_MODE = "-d" in sys.argv
if DEBUG_MODE:
    print("🛠️ Debug mode is ON")

# --- Helpers ---
def load_wrestlers():
    try:
        with open(ROSTER_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_wrestlers(data):
    with open(ROSTER_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --- Events ---
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    if payload.event_type != "REACTION_ADD":
        return

    guild = bot.get_guild(payload.guild_id)
    channel = guild.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    user = await bot.fetch_user(payload.user_id)

    if channel.name != "dwf-commissioner":
        return

    if str(payload.emoji) == "✅":
        print(f"✅ Approval received for message ID {payload.message_id} by {user.name}")
        wrestler_name = message.content.split('**')[1] if '**' in message.content else "Unknown"
        await user.send(f"✅ Your persona, {wrestler_name}, has been approved! Welcome to the DWF!")
        await message.delete()
    elif str(payload.emoji) == "❌":
        print(f"❌ Rejection received for message ID {payload.message_id} by {user.name}")
        await message.delete()
if DEBUG_MODE:
    print(f"🔐 DISCORD_TOKEN loaded: {'Yes' if TOKEN else 'No'}")
    print(f"🏷️ DISCORD_GUILD_ID: {GUILD_ID if GUILD_ID else 'Missing or invalid'}")
@bot.event
async def on_ready():
    print("📡 on_ready() triggered")
    print(f"✅ Logged in as: {bot.user.name}")
    if DEBUG_MODE:
        print(f"📶 Discord API latency: {round(bot.latency * 1000)}ms")
        print("📦 Registered bot commands:")
        for cmd in bot.commands:
            print(f" - !{cmd.name}")

    if not bot.guilds:
        print("❌ No guilds found. Bot may not be added to any server.")
        return

    for guild in bot.guilds:
        print(f"🏠 Guild: {guild.name} (ID: {guild.id})")
        if DEBUG_MODE:
            if not guild.text_channels:
                print("❗ No text channels available in this guild.")
            else:
                print("📃 Visible text channels:")
                for channel in guild.text_channels:
                    print(f" - #{channel.name} (ID: {channel.id})")

        backstage = discord.utils.get(guild.text_channels, name="dwf-backstage")
        commissioner = discord.utils.get(guild.text_channels, name="dwf-commissioner")
        promos = discord.utils.get(guild.text_channels, name="dwf-promos")

        if backstage:
            print(f"✅ Found #dwf-backstage (ID: {backstage.id})")
            await backstage.send("🎤 Mean Gene is in the building!")
        else:
            print("❌ Could not find #dwf-backstage")

        if commissioner:
            print(f"✅ Found #dwf-commissioner (ID: {commissioner.id})")
            async for msg in commissioner.history(limit=100):
                try:
                    if msg.author == bot.user:
                        await msg.delete()
                except discord.Forbidden:
                    print(f"⚠️ Could not delete a message (missing permissions): {msg.id}")
                except discord.HTTPException as e:
                    print(f"⚠️ Failed to delete message {msg.id}: {e}")
            await commissioner.send("🛠️ Mean Gene Bot (DWF) is online and ready to take contracts.")
        else:
            print("❌ Could not find #dwf-commissioner")

        if promos:
            print(f"✅ Found #dwf-promos (ID: {promos.id})")
            await promos.send("📢 Mean Gene is ready to broadcast your promos!")
        else:
            print("❌ Could not find #dwf-promos")
# --- Commands ---
@bot.command()
async def register(ctx, *, wrestler_name):
    print(f"📨 !register received from {ctx.author} in #{ctx.channel.name}")
    if ctx.channel.name != "dwf-backstage":
        return

    wrestlers = load_wrestlers()
    user_id = str(ctx.author.id)

    if user_id in wrestlers and "wrestler" in wrestlers[user_id]:
        await ctx.send("You’ve already registered a persona.")
        return

    if wrestler_name in [w.get('wrestler') for w in wrestlers.values() if 'wrestler' in w]:
        await ctx.send("That name is already taken.")
        return

    guild = ctx.guild
    comm_channel = discord.utils.get(guild.text_channels, name="dwf-commissioner")
    if not comm_channel:
        await ctx.send("Could not locate the commissioner channel.")
        return

    msg = await comm_channel.send(f"📝 `{ctx.author}` requests to register as **{wrestler_name}**. ✅ to approve, ❌ to reject.")
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    wrestlers[user_id] = {"pending": wrestler_name}
    save_wrestlers(wrestlers)

    await ctx.send("Registration request submitted for approval.")

print("🚀 Launching Discord bot...")
print(f"TOKEN loaded: {bool(TOKEN)}")
bot.run(TOKEN)
