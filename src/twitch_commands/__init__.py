import importlib
import pkgutil

def load_all_cogs(bot):
    package = __package__
    # Load all cogs except message_router
    for _, module_name, is_pkg in pkgutil.iter_modules(__path__):
        if is_pkg or module_name.startswith("_") or module_name == "message_router":
            continue
        module = importlib.import_module(f"{package}.{module_name}")
        if hasattr(module, "prepare"):
            module.prepare(bot)

    # Now load message_router last
    module = importlib.import_module(f"{package}.message_router")
    if hasattr(module, "prepare"):
        module.prepare(bot)