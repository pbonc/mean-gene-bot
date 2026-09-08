"""Offline import and composition regressions; never import the application entrypoint."""
import ast
import asyncio
import importlib
import importlib.abc
import os
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "bot.commands.walkin", "bot.commands.media_overlay",
    "bot.commands.song_request_simple", "bot.commands.song_cog",
    "bot.audio_manager",
)


def isolated_probe(target, compose=False, violation=None):
    # A fresh interpreter plus an import trap catches even attempted main imports.
    class BlockMain(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in {"bot.main", "__main__.bot"}:
                raise AssertionError("Reusable code attempted to import bot.main")

    sys.meta_path.insert(0, BlockMain())
    os.environ.clear()
    os.environ["APPDATA"] = str(ROOT / "offline-unused")
    attempts = []

    def audit(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = os.fsdecode(args[0]).replace("\\", "/").lower()
            if ("/data/" in path or path.startswith("data/") or
                    path.endswith((".env", "user.md", ".db", "cookies.txt")) or
                    "/logs/" in path):
                attempts.append(event)
                raise AssertionError("Forbidden file access during offline test")
        if event in {"socket.connect", "socket.bind", "subprocess.Popen", "os.system"}:
            attempts.append(event)
            raise AssertionError("Runtime resource attempted during offline test")

    sys.addaudithook(audit)
    # Real modules execute; only device/backend boundaries are substituted.
    pygame = Mock()
    playback = Mock()
    def profile(frame, event, arg):
        if event == "call":
            name = frame.f_code.co_name
            owner = frame.f_locals.get("self")
            if (name == "__init__" and type(owner).__name__ in {"AudioManager", "SimpleSongManager"}) or name in {"_init_pygame", "_start_sfx_worker", "start_worker"}:
                attempts.append(name)
                raise AssertionError("Audio constructor or worker attempted during reusable import")
    sys.setprofile(profile)
    with patch.dict(sys.modules, {"pygame": pygame, "playsound3": SimpleNamespace(playsound=playback)}), \
            patch("threading.Thread.start") as threads, \
            patch("asyncio.BaseEventLoop.create_task") as tasks:
        importlib.import_module(target)
        if violation == "main":
            importlib.import_module("bot.main")
        elif violation == "constructor":
            importlib.import_module("bot.audio_manager").AudioManager()
        elif violation == "pygame":
            pygame.init()
        elif violation == "mixer":
            pygame.mixer.init()
        elif violation == "playback":
            playback("forbidden.wav")
        elif violation == "thread":
            import threading
            threading.Thread(target=lambda: None).start()
        elif violation == "task":
            asyncio.BaseEventLoop.create_task(None, None)
        elif violation == "worker":
            importlib.import_module("bot.commands.song_request_simple").DownloadQueue.start_worker(None)
        assert "bot.main" not in sys.modules
        threads.assert_not_called()
        tasks.assert_not_called()
        assert not pygame.mock_calls
        playback.assert_not_called()
        assert not attempts, attempts
    sys.setprofile(None)
    if compose:
        with patch.dict(sys.modules, {"pygame": pygame, "playsound3": SimpleNamespace(playsound=playback)}):
            check_composition()
    assert not attempts, attempts


def check_composition():
    song = importlib.import_module("bot.commands.song_request_simple")
    walkin = importlib.import_module("bot.commands.walkin")
    media = importlib.import_module("bot.commands.media_overlay")
    display = importlib.import_module("bot.commands.song_cog")
    # Execute the real composition function and Bot constructor, excluding the
    # entrypoint's unrelated logging, environment and provider initialization.
    tree = ast.parse((ROOT / "bot/main.py").read_text(encoding="utf-8"))
    factory = next(n for n in tree.body if getattr(n, "name", None) == "create_bot")
    bot_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Bot")
    init = next(n for n in bot_class.body if getattr(n, "name", None) == "__init__")
    bot_class.body = [init]
    bot_class.decorator_list = []
    class OfflineBot:
        def __init__(self, **kwargs):
            self.cogs = {}
        def get_cog(self, name):
            return self.cogs.get(name)
        def add_cog(self, cog):
            self.cogs[type(cog).__name__] = cog
    ns = {n.id: Mock() for n in ast.walk(init) if isinstance(n, ast.Name)}
    ns.pop("super", None)
    ns.update(commands=SimpleNamespace(Bot=OfflineBot), AudioManager=Mock(), __name__="offline_composition")
    exec(compile(ast.Module(body=[bot_class, factory], type_ignores=[]), "bot/main.py", "exec"), ns)
    # Preserve the real song constructor and injected identity while disabling
    # its existing state I/O, workers and backend initialization.
    with patch.object(song.SimpleSongManager, "load_quarters", return_value={}), \
            patch.object(song.SimpleSongManager, "load_playlist_cache", return_value=[]), \
            patch.object(song.SimpleSongManager, "_load_autoplay_state"), \
            patch.object(song.SimpleSongManager, "_log_cache_status"), \
            patch.object(song.DownloadQueue, "start_worker"), \
            patch.object(song, "PYGAME_AVAILABLE", False), \
            patch.object(song.os, "makedirs"), \
            patch("concurrent.futures.ThreadPoolExecutor"), \
            patch.object(song, "SimpleSongManager", wraps=song.SimpleSongManager) as song_factory:
        bot = ns["create_bot"]()
        ns["AudioManager"].assert_called_once_with(music_volume=0.3, sfx_volume=0.6, duck_volume=0.1)
        audio = ns["AudioManager"].return_value
        song_factory.assert_called_once_with(audio)
        assert bot.audio_manager is audio
        assert bot.song_manager.audio_manager is audio
        song.prepare(bot)
        song.prepare(bot)
        song_factory.assert_called_once()
        assert bot.cogs["SongRequestCog"].manager is bot.song_manager
    with patch.object(walkin, "_load_store", return_value={"users": {}}), \
            patch.object(walkin, "_save_store"):
        walkin.prepare(bot)
    with patch.object(media.MediaOverlayCog, "_load_ytmode_state", return_value=False), \
            patch.object(media, "ThreadPoolExecutor"):
        def disable_task(coro):
            coro.close()
            return Mock()
        bot.loop = SimpleNamespace(create_task=disable_task)
        media.prepare(bot)
    display.prepare(bot)

    async def exercise():
        # Execute executor callbacks inline: no real worker threads.
        async def inline(executor, callback, *args):
            return callback(*args)
        ctx = SimpleNamespace(send=AsyncMock())
        loop = SimpleNamespace(run_in_executor=inline)
        with patch("asyncio.get_event_loop", return_value=loop):
            await bot.cogs["WalkinCog"]._play_sfx_entry(("offline.wav", "flat", None))
        audio.play_sfx.assert_called_once_with("offline.wav")
        assert media.playsound is media.playsound_with_volume
        media.bind_audio_manager(None)
        try:
            media.playsound("unbound.wav")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Unbound playback must fail clearly")
        media.bind_audio_manager(audio)
        media.playsound("legacy.wav")
        audio.play_sfx.assert_called_with("legacy.wav")
        audio.set_sfx_volume.assert_not_called()
        media.playsound("helper.wav", 0.4)
        audio.set_sfx_volume.assert_called_once_with(0.4)
        audio.play_sfx.assert_called_with("helper.wav")
        override = Mock()
        media.playsound("override.wav", volume=0.2, audio_manager=override)
        override.set_sfx_volume.assert_called_once_with(0.2)
        override.play_sfx.assert_called_once_with("override.wav")
        cog = bot.cogs["MediaOverlayCog"]
        assert cog.bot.audio_manager is audio
        cog.media_commands = {"sample": {"sfx": ("media.wav", "flat", None)}}
        with patch("asyncio.get_event_loop", return_value=loop):
            await media.MediaOverlayCog.randomsfx._callback(cog, ctx)
        audio.play_sfx.assert_called_with("media.wav")
        # Both song cogs see mutations on the composed manager.
        bot.song_manager.is_playing = False
        await display.SongCog.now_playing._callback(bot.cogs["SongCog"], ctx)
        assert "No song currently playing" in ctx.send.call_args.args[0]
    coroutine = exercise()
    try:
        coroutine.send(None)
    except StopIteration:
        pass
    else:
        coroutine.close()
        raise AssertionError("Offline callbacks unexpectedly suspended")
    # Ensure the application startup actually uses the tested composition path.
    main = next(n for n in tree.body if getattr(n, "name", None) == "main")
    calls = [n.func.id for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert calls.count("create_bot") == 1
    assert "Bot" not in calls


class AudioDependencyTests(unittest.TestCase):
    def run_probe(self, module, compose=False):
        result = subprocess.run(
            [sys.executable, "-X", "utf8", "-B", "-c",
             f"from tests.test_audio_dependencies import isolated_probe; isolated_probe({module!r}, {compose!r})"],
            cwd=ROOT, capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_each_reusable_import_is_inert_in_fresh_interpreter(self):
        for module in MODULES:
            with self.subTest(module=module):
                self.run_probe(module)

    def test_probe_rejects_deliberate_runtime_violations(self):
        for violation in ("main", "constructor", "pygame", "mixer", "playback", "thread", "task", "worker"):
            with self.subTest(violation=violation):
                result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c",
                    "from tests.test_audio_dependencies import isolated_probe; "
                    f"isolated_probe('bot.audio_manager', violation={violation!r})"],
                    cwd=ROOT, capture_output=True, text=True, timeout=45)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("AssertionError", result.stderr)

    def test_guarded_main_import_is_cached(self):
        result = subprocess.run([sys.executable, "-X", "utf8", "-B", "-c",
            "from tests.offline_main import load_main_offline; "
            "first = load_main_offline(); "
            "assert load_main_offline() is first; "
            "import bot.main; assert bot.main is first"],
            cwd=ROOT, capture_output=True, text=True, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_startup_composes_and_commands_share_services(self):
        self.run_probe("bot.commands.song_request_simple", compose=True)


if __name__ == "__main__":
    unittest.main()
