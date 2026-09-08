"""Offline regression tests: execute selected definitions without app imports."""
import ast
import builtins
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]


def definitions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec"), namespace)
    return namespace


class StartupTests(unittest.TestCase):
    def test_no_global_python_kill_and_targeted_cleanup_preserved(self):
        for path in ("bot/main.py", "start_bot.bat", "start_bot.sh"):
            text = (ROOT / path).read_text(encoding="utf-8").lower()
            self.assertNotIn("taskkill", text)
            self.assertNotIn("pkill", text)
            self.assertNotIn("killall", text)
        tree = ast.parse((ROOT / "bot/main.py").read_text(encoding="utf-8"))
        cleanup = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "shutdown_cleanup")
        source = ast.unparse(cleanup)
        for owned in ("await discord_bot.close()", "await bot.close()", "extra_task.cancel()", "await extra_task"):
            self.assertIn(owned, source)


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_uses_https_without_credentials_or_network(self):
        response = AsyncMock()
        response.status = 200
        response.json.return_value = {"current": {"condition": {"text": "Clear"}, "temp_f": 70, "temp_c": 21}, "location": {}}
        request = AsyncMock()
        request.__aenter__.return_value = response
        session = AsyncMock()
        session.get = Mock(return_value=request)
        context = AsyncMock()
        context.__aenter__.return_value = session
        ns = definitions("bot/weather_utils.py", {"fetch_weather", "get_weather_emoji"}, {
            "os": SimpleNamespace(getenv=lambda _: "offline-placeholder"),
            "aiohttp": SimpleNamespace(ClientSession=Mock(return_value=context)),
        })
        result = await ns["fetch_weather"]("Chicago")
        self.assertIn("Clear", result)
        session.get.assert_called_once_with("https://api.weatherapi.com/v1/current.json?key=offline-placeholder&q=Chicago&aqi=no")
        self.assertNotIn("http://api.weatherapi.com", (ROOT / "bot/weather_utils.py").read_text(encoding="utf-8"))


class OverlayLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tree = ast.parse((ROOT / "bot/overlay_server.py").read_text(encoding="utf-8"))
        self.runner = SimpleNamespace(setup=AsyncMock(), cleanup=AsyncMock())
        self.site = SimpleNamespace(start=AsyncMock())
        self.web = SimpleNamespace(Application=Mock(), AppRunner=Mock(return_value=self.runner), TCPSite=Mock(return_value=self.site))
        self.started = [asyncio.Event(), asyncio.Event()]
        self.stopped = [asyncio.Event(), asyncio.Event()]
        async def worker(index):
            self.started[index].set()
            try:
                await asyncio.Event().wait()
            finally:
                self.stopped[index].set()
        # Route handlers are never executed. Provide inert names for route registration.
        ns = {n.id: Mock() for n in ast.walk(tree) if isinstance(n, ast.Name) and not hasattr(builtins, n.id)}
        ns.update(asyncio=asyncio, web=self.web, os=SimpleNamespace(path=SimpleNamespace(isdir=lambda _: False, join=lambda *args: "unused")),
                  logging=logging, _runner=None, _background_tasks=set(), _lifecycle_lock=asyncio.Lock(),
                  RuntimeError=RuntimeError, as_overlay_task=lambda: worker(0), rpg_state_task=lambda: worker(1))
        self.ns = definitions("bot/overlay_server.py", {"start_overlay_server", "shutdown"}, ns)
        self.serving = None

    async def asyncTearDown(self):
        if self.serving:
            self.serving.cancel()
            await asyncio.gather(self.serving, return_exceptions=True)
        await self.ns["shutdown"]()

    async def start(self):
        self.serving = asyncio.create_task(self.ns["start_overlay_server"]())
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in self.started)), 1)

    async def test_retains_cancels_and_awaits_only_owned_tasks(self):
        unrelated = asyncio.create_task(asyncio.Event().wait())
        try:
            await self.start()
            self.assertIs(self.ns["_runner"], self.runner)
            owned = tuple(self.ns["_background_tasks"])
            self.assertEqual(len(owned), 2)
            await self.ns["shutdown"]()
            await self.ns["shutdown"]()
            self.runner.cleanup.assert_awaited_once()
            self.assertTrue(all(t.cancelled() for t in owned))
            self.assertTrue(all(e.is_set() for e in self.stopped))
            self.assertIsNone(self.ns["_runner"])
            self.assertFalse(self.ns["_background_tasks"])
            self.assertFalse(unrelated.done())
        finally:
            unrelated.cancel()
            await asyncio.gather(unrelated, return_exceptions=True)

    async def test_serving_cancellation_cleans_resources(self):
        await self.start()
        self.serving.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.serving
        self.runner.cleanup.assert_awaited_once()
        self.assertFalse(self.ns["_background_tasks"])

    async def test_setup_and_bind_failure_cleanup_and_retry(self):
        for failure in (self.runner.setup, self.site.start):
            failure.side_effect = OSError("offline startup failure")
            with self.assertRaises(OSError):
                await self.ns["start_overlay_server"]()
            self.assertIsNone(self.ns["_runner"])
            self.assertFalse(self.ns["_background_tasks"])
            failure.side_effect = None
        self.assertEqual(self.runner.cleanup.await_count, 2)
        await self.start()

    async def test_cancel_during_setup_cleans_partial_runner(self):
        entered = asyncio.Event()
        async def setup():
            entered.set()
            await asyncio.Event().wait()
        self.runner.setup.side_effect = setup
        self.serving = asyncio.create_task(self.ns["start_overlay_server"]())
        await asyncio.wait_for(entered.wait(), 1)
        self.serving.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.serving
        self.runner.cleanup.assert_awaited_once()
        self.assertIsNone(self.ns["_runner"])
        self.assertFalse(self.ns["_background_tasks"])

    async def test_failed_background_task_does_not_prevent_cleanup(self):
        await self.start()
        async def fail():
            raise RuntimeError("offline background failure")
        failed = asyncio.create_task(fail())
        self.ns["_background_tasks"].add(failed)
        await asyncio.sleep(0)
        await self.ns["shutdown"]()
        self.runner.cleanup.assert_awaited_once()
        self.assertFalse(self.ns["_background_tasks"])

    async def test_repeated_start_does_not_replace_or_clean_active_runner(self):
        await self.start()
        with self.assertRaises(RuntimeError):
            await self.ns["start_overlay_server"]()
        self.web.AppRunner.assert_called_once()
        self.runner.cleanup.assert_not_awaited()


class MediaWatcherTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tree = ast.parse((ROOT / "bot/commands/media_overlay.py").read_text(encoding="utf-8"))
        cog = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MediaOverlayCog")
        cog.bases = []
        cog.body = [n for n in cog.body if getattr(n, "name", None) in {"__init__", "cog_unload", "_watcher_done"}]
        ns = {"asyncio": asyncio, "logging": logging, "ThreadPoolExecutor": Mock()}
        exec(compile(ast.Module(body=[cog], type_ignores=[]), "media_overlay.py", "exec"), ns)
        self.cls = ns["MediaOverlayCog"]
        self.cls._load_ytmode_state = Mock(return_value=False)
        self.cls._cleanup_reserved_command_conflicts = Mock()
        self.cls._unregister_media_command = Mock()
        self.cls._watch_media_folders = lambda _: asyncio.Event().wait()

    async def test_retained_watcher_observed_and_only_owned_task_cancelled(self):
        cog = self.cls(SimpleNamespace(loop=asyncio.get_running_loop()))
        owned = cog._watcher_task
        unrelated = asyncio.create_task(asyncio.Event().wait())
        try:
            await asyncio.sleep(0)
            cog.cog_unload()
            cog.cog_unload()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            self.assertTrue(owned.cancelled())
            self.assertIsNone(cog._watcher_task)
            self.assertFalse(unrelated.done())
            cog.cog_unload()
        finally:
            unrelated.cancel()
            await asyncio.gather(unrelated, return_exceptions=True)

    async def test_partial_initialization_unload(self):
        cog = self.cls.__new__(self.cls)
        cog.cog_unload()
        cog.cog_unload()

    async def test_watcher_failure_is_observed_and_cleared(self):
        async def fail(_):
            raise RuntimeError("offline watcher failure")
        self.cls._watch_media_folders = fail
        cog = self.cls(SimpleNamespace(loop=asyncio.get_running_loop()))
        cog.logger = Mock()
        task = cog._watcher_task
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertTrue(task.done())
        self.assertIsNone(cog._watcher_task)
        cog.logger.exception.assert_called_once()
        cog.cog_unload()


if __name__ == "__main__":
    unittest.main()
