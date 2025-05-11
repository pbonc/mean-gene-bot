from bot.data.command_loader import load_sfx_commands
from bot.commands.sfxrefresh import SFXRefresh
from bot.events import setup_events
import mgb_dwf

def load_all(bot):
    print("📦 Loading SFX commands...")
    load_sfx_commands(bot)

    print("🎮 Loading DWF commands...")
    if hasattr(mgb_dwf, "load_dwf_commands"):
        mgb_dwf.load_dwf_commands(bot)

    print("🧠 Registering internal cogs...")
    bot.add_cog(SFXRefresh(bot))

    print("🧬 Hooking up events...")
    setup_events(bot)
