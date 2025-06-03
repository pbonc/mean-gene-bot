from functools import wraps

def mod_only(func):
    @wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        if not (hasattr(ctx.author, "is_mod") and ctx.author.is_mod):
            await ctx.send("❌ Only mods can use this command.")
            return
        return await func(self, ctx, *args, **kwargs)
    return wrapper