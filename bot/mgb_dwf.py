import sys
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import json
from pathlib import Path
import traceback

# --- Project Path Setup ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    print(f"🛠️ Adding project root to sys.path: {project_root}")
    sys.path.insert(0, project_root)

# --- Environment ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- Discord Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.guilds = True
intents.members = True

# --- Custom Bot Class ---
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
                    traceback.print_exc()

# --- Bot Instance ---
DISCORD_CLIENT = MeanGeneClient(command_prefix="!", intents=intents)
DISCORD_CLIENT._startup_announced = False  # Guard to prevent double startup messages

# --- Events ---
@DISCORD_CLIENT.event
async def on_ready():
    # Guard: only run startup actions once per process
    if getattr(DISCORD_CLIENT, "_startup_announced", False):
        return
    DISCORD_CLIENT._startup_announced = True

    print(f"✅ Discord bot connected as: {DISCORD_CLIENT.user}")

    try:
        DWF_CHANNELS = {"dwf-backstage", "dwf-commissioner", "dwf-promos"}
        for guild in DISCORD_CLIENT.guilds:
            print(f"🔎 Connected to guild: {guild.name} (ID: {guild.id})")
            for channel in guild.text_channels:
                if channel.name in DWF_CHANNELS:
                    print(f"✅ Found DWF channel: #{channel.name} (ID: {channel.id})")
                    try:
                        await channel.send("🤖 Bot is now online and ready!")
                        print(f"✅ Sent startup message to #{channel.name}")
                    except Exception as e:
                        print(f"⚠️ Could not send message to #{channel.name}: {e}")
    except Exception as e:
        print(f"💥 Exception during on_ready(): {e}")
        traceback.print_exc()

@DISCORD_CLIENT.event
async def on_resumed():
    print("🔄 Discord resumed connection (likely after disconnect)")

@DISCORD_CLIENT.event
async def on_message(message):
    if message.channel and message.channel.name == "dwf-commissioner":
        print(f"🧠 Saw message in commissioner: {message.content}")
    await DISCORD_CLIENT.process_commands(message)

# --- Startup Entrypoint ---
async def start_discord():
    print("🧪 Calling DISCORD_CLIENT.start()...")
    try:
        await DISCORD_CLIENT.start(TOKEN)
    except Exception as e:
        print(f"❌ Discord bot failed to start: {e}")
        traceback.print_exc()

# --- DWF Utilities ---
def get_wrestler_path():
    # Move one directory UP from 'bot' folder, then into dwf/
    path = Path(__file__).parent.parent / "dwf" / "wrestlers.json"
    print(f"📂 wrestler path: {path}")
    return path

def load_wrestlers():
    path = get_wrestler_path()
    print(f"Loading wrestlers from: {path}")
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                print(f"File content size: {len(content)} bytes")
                data = json.loads(content)
                print(f"Loaded {len(data)} wrestlers")
                return data
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to decode wrestlers.json: {e}")
        except Exception as e:
            print(f"⚠️ Failed to read wrestlers.json: {e}")
    else:
        print("⚠️ Wrestlers file does not exist!")
    return {}

def save_wrestlers(data):
    path = get_wrestler_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"💾 Saved wrestler data to: {path}")
    except Exception as e:
        print(f"❌ Failed to save wrestlers.json: {e}")

def announce_new_wrestler(name):
    print(f"📢 New wrestler registered: {name}")