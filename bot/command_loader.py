import os
import random
import re
import logging
from datetime import datetime, timezone
from twitchio.ext import commands
from twitchio.ext.commands.errors import CommandNotFound
from sfx_player import queue_sfx

SFX_ROOT = os.path.join(os.path.dirname(__file__), "sfx")
loaded_commands = set()
RESERVED_COMMANDS = {"sfxcount", "randomsfx"}

# Ensure logs folder exists
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Setup skipped command logging
SKIP_LOG_PATH = os.path.join(LOG_DIR, "skipped-commands.log")
skip_logger = logging.getLogger("skipped_commands")
skip_logger.setLevel(logging.INFO)

if not skip_logger.handlers:
    handler = logging.FileHandler(SKIP_LOG_PATH, mode='a', encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s - %(message)s')
    handler.setFormatter(formatter)
    skip_logger.addHandler(handler)

def is_valid_command_name(name):
    if name == "!!":
        return True
    return bool(re.fullmatch(r'[a-zA-Z0-9]+', name))

def log_skip(reason: str, user: str, attempted_command: str, created_at):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    account_age = created_at.strftime("%Y-%m-%d") if created_at else "unknown"
    message = f"{timestamp} - {user} skipped: {reason} for !{attempted_command} (account created: {account_age})"
    skip_logger.info(message)
    print(f"\u26d4 {message}")

def load_sfx_commands(bot: commands.Bot):
    @bot.event
    async def event_command_error(ctx, error):
        if isinstance(error, CommandNotFound):
            full_message = ctx.message.content.strip()
            if not full_message.startswith("!"):
                return  # not a command
            attempted = full_message[1:]
            user = ctx.author.name
            user_info = await bot.fetch_users(names=[user])
            created = user_info[0].created_at.replace(tzinfo=None) if user_info and user_info[0].created_at else None
            reason = "invalid characters in command" if not is_valid_command_name(attempted) else "command not found"
            log_skip(reason, user, attempted, created)

    # The rest of the function remains unchanged

    print("✅ event_command_error handler registered.")
