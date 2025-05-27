import importlib
import pkgutil

def load_all_cogs(bot):
    package = __package__
    for _, module_name, is_pkg in pkgutil.iter_modules(__path__):
        if is_pkg or module_name.startswith("_"):
            continue
        module = importlib.import_module(f"{package}.{module_name}")
        if hasattr(module, "prepare"):
            module.prepare(bot)