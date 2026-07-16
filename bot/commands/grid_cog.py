import asyncio
import logging
import time
from twitchio.ext import commands
from bot.grid_state import GridManager, MAX_HITS
from bot.overlay_server import broadcast_overlay_message

LOGGER = logging.getLogger("grid")
COMMISSIONER_NAME = "tankadelphia"
TEST_REVEAL_USER = "iamdar"
ASSIGN_COOLDOWN_SECONDS = 30
IMPORT_CSV_FILENAME = "grid_import_starter.csv"
USAGE = "Usage: !grid set [hits] | !grid add <tier> <count> <description> | !grid import [replace] | !grid award @user | !grid status | !grid clear | !grid <tile#>"


class GridCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = GridManager()
        self._last_assign_time = 0.0
        self._pending_nuclear_request = None
        self._nuclear_request_ttl = 60
        try:
            bot.loop.create_task(self._broadcast_state())
        except Exception:
            LOGGER.exception("Failed to schedule grid startup broadcast")

    async def _broadcast_state(self):
        await asyncio.sleep(1)
        await broadcast_overlay_message(self.manager.get_payload())

    @commands.command(name="grid")
    async def grid_command(self, ctx):
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send(USAGE)
            return
        action = parts[1].lower()
        if action == "set":
            await self._handle_set(ctx, parts[2:])
        elif action == "award":
            await self._handle_award(ctx, parts[2:])
        elif action == "add":
            await self._handle_add(ctx, parts[2:])
        elif action in ("import", "importcsv", "csv"):
            await self._handle_import_csv(ctx, parts[2:])
        elif action == "clear":
            await self._handle_clear(ctx)
        elif action in ("status", "info"):
            await self._handle_status(ctx)
        elif action.lstrip("#").isdigit():
            await self._handle_reveal(ctx, action.lstrip("#"))
        else:
            await ctx.send(USAGE)

    async def _handle_set(self, ctx, args):
        if not getattr(ctx.author, "is_mod", False):
            await ctx.send("Only mods can set the grid.")
            return
        hits = 1
        if args:
            try:
                hits = max(1, min(MAX_HITS, int(args[0])))
            except ValueError:
                hits = 1
        try:
            self.manager.randomize_grid(hits=hits)
        except Exception as exc:
            LOGGER.exception("Failed to randomize grid", exc_info=exc)
            await ctx.send(f"Failed to set grid: {exc}")
            return
        payload = self.manager.get_payload(message=f"Grid randomized with {hits} hit(s)!")
        await broadcast_overlay_message(payload)
        await ctx.send(
            f"Grid locked with {hits} hit{'s' if hits != 1 else ''}. {self.manager.available_tiles_count()} tiles ready."
        )

    async def _handle_add(self, ctx, args):
        if not getattr(ctx.author, "is_mod", False):
            await ctx.send("Only mods can add prizes to the grid inventory.")
            return
        if len(args) < 3:
            await ctx.send("Usage: !grid add <tier> <count> <description>")
            return
        level = args[0]
        try:
            count = int(args[1])
        except ValueError:
            await ctx.send("Prize count must be a whole number.")
            return
        description = " ".join(args[2:]).strip()
        if not description:
            await ctx.send("Prize description cannot be empty.")
            return
        try:
            total = self.manager.add_prizes(level, count, description)
        except Exception as exc:
            await ctx.send(str(exc))
            return
        try:
            await broadcast_overlay_message(self.manager.get_payload())
        except Exception:
            LOGGER.exception("Failed to broadcast grid inventory update")
        await ctx.send(
            f"Added {count} {level} prize{'s' if count != 1 else ''} to inventory ({total} total)."
        )

    async def _handle_award(self, ctx, args):
        if not ctx.author or not (ctx.author.is_mod or ctx.author.name.lower() == COMMISSIONER_NAME):
            await ctx.send("Only mods can assign tiles via the grid.")
            return
        now = time.monotonic()
        elapsed = now - self._last_assign_time
        if elapsed < ASSIGN_COOLDOWN_SECONDS:
            remaining = int(ASSIGN_COOLDOWN_SECONDS - elapsed)
            await ctx.send(f"Assign command is on cooldown for {remaining} more second{'' if remaining == 1 else 's'}.")
            return
        if not args:
            await ctx.send("Usage: !grid award @user")
            return
        target_raw = args[0]
        target_display = target_raw.lstrip("@").strip()
        if not target_display:
            await ctx.send("Please supply a viewer to award.")
            return
        granted = self.manager.grant_pick_for(target_display)
        if not granted:
            await ctx.send("No tiles available to award. Run !grid set to refresh.")
            return
        self._last_assign_time = now
        message = (
            f"🔒 @{target_display} has 1 grid pick. They can reveal any tile with !grid <tile#>. "
            f"{self.manager.available_tiles_count()} tiles left • {self.manager.state.get('hits_remaining', 0)} hit(s) remain."
        )
        payload = self.manager.get_payload(message=message)
        await broadcast_overlay_message(payload)
        await ctx.send(message)

    async def _handle_import_csv(self, ctx, args):
        if not getattr(ctx.author, "is_mod", False):
            await ctx.send("Only mods can import grid prizes.")
            return
        replace = any(arg.lower() in ("replace", "reset", "overwrite", "--replace") for arg in args)
        try:
            row_count, total = self.manager.import_prizes_from_csv(IMPORT_CSV_FILENAME, replace=replace)
        except Exception as exc:
            await ctx.send(f"Import failed: {exc}")
            return
        try:
            import_sequence = self.manager.get_import_animation_sequence()
            await broadcast_overlay_message(
                self.manager.get_payload(
                    message="Import complete. Populating prize pool...",
                    import_sequence=import_sequence,
                )
            )
        except Exception:
            LOGGER.exception("Failed to broadcast grid inventory update after CSV import")
        mode = "replaced" if replace else "appended"
        await ctx.send(
            f"Import complete: {row_count} row(s) {mode}. Inventory now has {total} prize(s). Run !grid set to refresh tiles."
        )

    async def _handle_reveal(self, ctx, tile_arg):
        if not ctx.author:
            await ctx.send("Unable to identify who is revealing a tile.")
            return
        try:
            tile_num = int(tile_arg)
        except ValueError:
            await ctx.send("Usage: !grid # where # is the tile number you were awarded to reveal.")
            return
        tile_id = tile_num - 1
        bypass = ctx.author.name.lower() == TEST_REVEAL_USER
        tile, error = self.manager.reveal_tile(tile_id, ctx.author.name, bypass=bypass)
        if not tile:
            await ctx.send(error or "Unable to reveal that tile right now.")
            return
        reveal = {
            "tile_id": tile["id"],
            "name": tile["name"],
            "tier": tile.get("tier"),
            "flair": tile.get("flair"),
            "awarded_to": ctx.author.name,
        }
        message = (
            f"✨ @{ctx.author.name} selects tile #{tile_num}. "
            f"{self.manager.available_tiles_count()} tiles remaining • {self.manager.state.get('hits_remaining', 0)} hit(s) remain."
        )
        payload = self.manager.get_payload(reveal=reveal, message=message)
        await broadcast_overlay_message(payload)
        await ctx.send(message)

    async def _handle_clear(self, ctx):
        if not ctx.author:
            await ctx.send("Unable to identify who is requesting the nuclear key.")
            return
        author_key = ctx.author.name.lower()
        if author_key == TEST_REVEAL_USER:
            await self._execute_clear(ctx, "iamdar triggered the nuclear key.")
            return
        if not getattr(ctx.author, "is_mod", False):
            await ctx.send("Only mods can trigger the nuclear key.")
            return
        now = time.monotonic()
        if self._pending_nuclear_request:
            first_mod, timestamp = self._pending_nuclear_request
            if now - timestamp > self._nuclear_request_ttl:
                self._pending_nuclear_request = None
            elif first_mod != author_key:
                await self._execute_clear(ctx, f"Mods {first_mod} and {ctx.author.name} confirmed the nuclear key.")
                self._pending_nuclear_request = None
                return
            else:
                await ctx.send("A different mod must confirm the nuclear key within a minute.")
                return
        self._pending_nuclear_request = (author_key, now)
        await ctx.send(
            "Nuclear key primed—another moderator must confirm within 60 seconds to clear the grid."
        )

    async def _execute_clear(self, ctx, reason: str) -> None:
        try:
            self.manager.clear_inventory()
        except Exception:
            LOGGER.exception("Failed to clear grid inventory during nuclear reset")
        self.manager.reset()
        payload = self.manager.get_payload(message=f"Grid state cleared via nuclear key. {reason}")
        await broadcast_overlay_message(payload)
        await ctx.send("Nuclear key engaged: grid history wiped.")

    async def _handle_status(self, ctx):
        self.manager.reload()
        await ctx.send(self.manager.summary())


def prepare(bot):
    if not bot.get_cog("GridCog"):
        bot.add_cog(GridCog(bot))
