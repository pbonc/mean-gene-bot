"""Execute the real entrypoint under preinstalled offline boundaries."""
import importlib
import sys
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch


def load_main_offline():
    def forbidden(*args, **kwargs):
        raise AssertionError("Runtime startup during offline main import")

    with ExitStack() as stack:
        stack.enter_context(patch.dict("os.environ", {}, clear=True))
        modules = {
            "dotenv": SimpleNamespace(load_dotenv=Mock(return_value=False)),
            "bot.audio_manager": SimpleNamespace(AudioManager=Mock(side_effect=forbidden)),
            "pygame": Mock(),
            "playsound3": SimpleNamespace(playsound=Mock(side_effect=forbidden)),
            "bot.overlay_server": SimpleNamespace(start_overlay_server=forbidden,
                                                   broadcast_overlay_message=Mock()),
            "bot.oauth_refresh": SimpleNamespace(auto_refresh_if_needed=forbidden),
            "bot.dependency_manager": SimpleNamespace(DependencyManager=Mock(
                return_value=SimpleNamespace(get_dependency_status=lambda: {"core": {}, "optional": {}}))),
        }
        # Restore only substituted entries; patch.dict would also evict the
        # freshly imported main and TwitchIO modules, causing unsafe reimports.
        for name, replacement in modules.items():
            previous = sys.modules.get(name)
            sys.modules[name] = replacement
            def restore(name=name, previous=previous):
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
            stack.callback(restore)
        for target in ("logging.basicConfig", "os.makedirs"):
            stack.enter_context(patch(target))
        stack.enter_context(patch("os.listdir", return_value=[]))  # pruning sees no files
        stack.enter_context(patch("platform.system", return_value="Windows"))
        guards = []
        for target in ("os.remove", "threading.Thread.start", "_thread.start_new_thread",
                       "asyncio.BaseEventLoop.create_task", "subprocess.Popen",
                       "socket.socket.connect", "socket.socket.bind",
                       "twitchio.ext.commands.Bot.__init__", "discord.Client.__init__",
                       "aiohttp.ClientSession", "bot.hermes_bridge.HermesRunClient"):
            guards.append(stack.enter_context(patch(target, side_effect=forbidden)))
        def profile(frame, event, arg):
            if event == "call" and (
                frame.f_code.co_name in {"start_worker", "_start_sfx_worker", "_init_pygame"}
                or (frame.f_code.co_name == "__init__" and
                    type(frame.f_locals.get("self")).__name__ == "SimpleSongManager")
            ):
                forbidden()
        previous_profile = sys.getprofile()
        stack.callback(sys.setprofile, previous_profile)
        sys.setprofile(profile)
        module = importlib.import_module("bot.main")
        for guard in guards:
            guard.assert_not_called()
        modules["bot.audio_manager"].AudioManager.assert_not_called()
        assert not modules["pygame"].mock_calls
        return module
