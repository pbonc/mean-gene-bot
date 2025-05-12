import sys
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
from pathlib import Path

# Ensure project root is in sys.path for proper module imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    print(f"🛠️ Adding project root to sys.path: {project_root}")
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Create Discord client with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True

# Subclass Bot to override setup_hook
class MeanGeneClient(commands.Bot):
    async def setup_hook(self):
        print("🧠 setup_hook() triggered")
        base_dir = os.path.join(os.path.dirname(__file__), "commands")
        print(f"📁 Scanning for cogs in: {base_dir}")

        if not os.path.isdir(base_dir):
            print("❌ Cogs directory not found:", base_dir)
            return

        files = os.listdir(base_dir)
        print(f"📄 Files found in commands/: {files}")

        for filename in files:
            if filename.endswith(".py") and not filename.startswith("_"):
                module = f"bot.commands.{filename[:-3]}"
                print(f"🔍 Preparing to load: {module}")
                try:
                    await self.load_extension(module)
                    print(f"✅ Loaded: {module}")
                except Exception as e:
                    print(f"❌ Failed to load {module}: {e}")
                    import traceback
                    traceback.print_exc()

# Instantiate the bot
DISCORD_CLIENT = MeanGeneClient(command_prefix="!", intents=intents)

@DISCORD_CLIENT.event
async def on_ready():
    print(f"✅ Discord bot connected as: {DISCORD_CLIENT.user}")
    for guild in DISCORD_CLIENT.guilds:
        print(f"🔎 Connected to guild: {guild.name} (ID: {guild.id})")
        for channel in guild.text_channels:
            print(f"🔍 Found text channel: #{channel.name} (ID: {channel.id})")
            if channel.name in ["dwf-backstage", "dwf-commissioner", "dwf-promos"]:
                try:
                    await channel.send("🤖 Bot is now online and ready!")
                    print(f"✅ Sent startup message to #{channel.name}")
                except Exception as e:
                    print(f"⚠️ Could not send message to #{channel.name}: {e}")

@DISCORD_CLIENT.event
async def on_message(message):
    await DISCORD_CLIENT.process_commands(message)

async def mgb_on_ready():
    print("📡 mgb_dwf.mgb_on_ready() called")

async def start_discord():
    print("🧪 Calling DISCORD_CLIENT.start()...")
    try:
        await DISCORD_CLIENT.start(TOKEN)
    except Exception as e:
        print(f"❌ Discord bot failed to start: {e}")

# Utility functions (if still needed elsewhere)
def load_wrestlers():
    roster_path = Path(__file__).parent / "data" / "wrestlers.json"
    if roster_path.exists():
        try:
            with open(roster_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("⚠️ Failed to decode wrestlers.json")
    return {}

def save_wrestlers(data):
    roster_path = Path(__file__).parent / "data" / "wrestlers.json"
    try:
        with open(roster_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"❌ Failed to save wrestlers.json: {e}")

def announce_new_wrestler(name):
    print(f"📢 New wrestler registered: {name}")