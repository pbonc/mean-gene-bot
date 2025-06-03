import importlib
import pkgutil

# Guard variable to prevent double-loading
_cogs_loaded = False

def load_all_cogs(bot):
    global _cogs_loaded
    if _cogs_loaded:
        print("[COG LOADER GUARD] Cogs already loaded, skipping!")
        return
    _cogs_loaded = True

    package = __package__
    print(f"[COG LOADER] Loading all cogs for package: {package}")
    # Load all cogs except message_router
    for _, module_name, is_pkg in pkgutil.iter_modules(__path__):
        print(f"[COG LOADER] Found module: {module_name} (is_pkg={is_pkg})")
        if is_pkg or module_name.startswith("_") or module_name == "message_router":
            print(f"[COG LOADER] Skipping module: {module_name}")
            continue
        module = importlib.import_module(f"{package}.{module_name}")
        print(f"[COG LOADER] Imported module: {package}.{module_name}")
        if hasattr(module, "prepare"):
            print(f"[COG LOADER] Calling prepare() in: {package}.{module_name}")
            module.prepare(bot)
        else:
            print(f"[COG LOADER] No prepare() in: {package}.{module_name}")

    # Now load message_router last
    print(f"[COG LOADER] Importing message_router last")
    module = importlib.import_module(f"{package}.message_router")
    if hasattr(module, "prepare"):
        print(f"[COG LOADER] Calling prepare() in: {package}.message_router")
        module.prepare(bot)
    else:
        print(f"[COG LOADER] No prepare() in: {package}.message_router")