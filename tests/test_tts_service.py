import asyncio
import os
import tempfile
import threading
import time
import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path

from bot.tts_service import DectalkProcessBackend, TokenStore, TtsConfig, TtsService
from bot.commands.tts_cog import TtsCog


class FakeBackend:
    name = "fake-dectalk"
    def __init__(self, ok=True): self.ok = ok; self.calls = []
    def available(self): return True
    def speak(self, text, timeout): self.calls.append((text, timeout)); return self.ok, None if self.ok else "malformed"


class ConcurrencyBackend:
    name = "concurrency-check"
    def __init__(self): self.lock = threading.Lock(); self.active = 0; self.max_active = 0; self.order = []
    def available(self): return True
    def speak(self, text, timeout):
        with self.lock:
            self.active += 1; self.max_active = max(self.max_active, self.active); self.order.append(text)
        time.sleep(.02)
        with self.lock: self.active -= 1
        return True, None


class Clock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now


class TokenStoreTests(unittest.TestCase):
    def test_additive_tokens_persist_and_migrate_to_twitch_id(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, "tokens.json")
            store = TokenStore(path); self.assertEqual(1, store.grant("Viewer")); self.assertEqual(2, store.grant("viewer"))
            restored = TokenStore(path); self.assertEqual(2, restored.balance("42", "viewer"))
            self.assertTrue(restored.consume("42", "viewer")); self.assertEqual(1, restored.balance("42", "viewer"))
            self.assertTrue(restored.consume("42", "viewer")); self.assertEqual(0, restored.balance("42", "viewer"))


class DectalkBackendTests(unittest.TestCase):
    def test_inline_commands_are_passed_unchanged_as_one_argument(self):
        executable = r"C:\dev\perfect-paul\build\us\release\say.exe"
        backend = DectalkProcessBackend(executable, "{text}", "paul", True)
        text = "[:rate 300] [:np] [dah<300,30>]"
        self.assertEqual(
            [executable, "-pre", "[:phoneme on]", text],
            backend._command(text),
        )

    def test_phoneme_prefix_can_be_disabled(self):
        backend = DectalkProcessBackend("say.exe", "{text}", "paul", False)
        text = "[:dial67589340] hello"
        self.assertEqual(["say.exe", text], backend._command(text))

    def test_wave_output_options_precede_untouched_viewer_text(self):
        backend = DectalkProcessBackend("say.exe", "{text}", "paul", True)
        text = "[:rate 500] [dah<300,30>]"
        self.assertEqual(
            ["say.exe", "-pre", "[:phoneme on]", "-w", r"C:\temp\speech.wav", text],
            backend._command(text, r"C:\temp\speech.wav"),
        )

    def test_configuration_defaults_phoneme_mode_on(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = TtsConfig.from_env()
            self.assertTrue(config.dectalk_phoneme_mode)
            self.assertFalse(config.dectalk_wave_mode)
            self.assertEqual(20, config.max_synthesis_seconds)
            self.assertEqual(60, config.max_playback_seconds)


class TtsServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.clock = Clock(); self.backend = FakeBackend()
        self.config = TtsConfig(global_cooldown_seconds=5, user_cooldown_seconds=30, max_queue_depth=2, max_input_length=80, max_playback_seconds=3)
        self.service = TtsService(self.config, self.backend, TokenStore(Path(self.temp.name, "tokens.json")), self.clock)

    async def asyncTearDown(self):
        if self.service.worker_task:
            self.service.worker_task.cancel()
            try: await self.service.worker_task
            except asyncio.CancelledError: pass
        self.temp.cleanup()

    async def test_queue_preserves_inline_syntax_and_runs_sequentially(self):
        text = "[:pitch 90] John Madden [:rate 250]"
        ok, _ = self.service.accept("id:1", "mod", "Mod", text, True)
        self.assertTrue(ok); await asyncio.wait_for(self.service.queue.join(), 1)
        self.assertEqual((text, 3), self.backend.calls[0])

    async def test_cooldown_and_validation_rejections_do_not_touch_tokens(self):
        self.service.tokens.grant("viewer", 2)
        self.assertFalse(self.service.accept("id:2", "viewer", "Viewer", "x" * 81, False)[0])
        self.assertEqual(2, self.service.tokens.balance("2", "viewer"))
        self.assertTrue(self.service.accept("id:2", "viewer", "Viewer", "hello", False)[0])
        self.assertTrue(self.service.tokens.consume("2", "viewer"))
        self.assertFalse(self.service.accept("id:2", "viewer", "Viewer", "again", False)[0])
        self.assertEqual(1, self.service.tokens.balance("2", "viewer"))

    async def test_cooldowns_expire_and_mod_bypass_is_configurable(self):
        self.assertTrue(self.service.accept("id:1", "one", "One", "first", True)[0])
        self.assertTrue(self.service.accept("id:2", "two", "Two", "second", True)[0])
        await asyncio.wait_for(self.service.queue.join(), 1)
        self.clock.now += 31
        self.assertTrue(self.service.accept("id:1", "one", "One", "third", False)[0])

    async def test_requests_finish_sequentially_in_queue_order(self):
        backend = ConcurrencyBackend()
        service = TtsService(replace(self.config, max_queue_depth=3), backend, TokenStore(Path(self.temp.name, "serial_tokens.json")), self.clock)
        for number in range(3):
            self.assertTrue(service.accept(f"id:{number}", f"user{number}", f"User{number}", f"message {number}", True)[0])
        await asyncio.wait_for(service.queue.join(), 2)
        self.assertEqual(["message 0", "message 1", "message 2"], backend.order)
        self.assertEqual(1, backend.max_active)
        service.worker_task.cancel()
        try: await service.worker_task
        except asyncio.CancelledError: pass

    async def test_reset_clears_stale_user_ownership_and_queued_requests(self):
        self.assertTrue(self.service.accept("id:1", "one", "One", "first", True)[0])
        self.assertTrue(self.service.accept("id:2", "two", "Two", "second", True)[0])
        discarded = self.service.reset()
        await asyncio.sleep(0)
        self.assertEqual(2, discarded)
        self.assertEqual(set(), self.service.pending_users)
        self.assertEqual(0, self.service.queue.qsize())
        self.assertTrue(self.service.accept("id:1", "one", "One", "retry", True)[0])


class Author:
    def __init__(self, name, user_id, mod=False):
        self.name = name; self.display_name = name; self.id = user_id
        self.is_mod = mod; self.is_broadcaster = False


class Context:
    def __init__(self, author): self.author = author; self.messages = []
    async def send(self, message): self.messages.append(message)


class CommandService:
    def __init__(self, store): self.tokens = store; self.accepted = True; self.calls = []
    def accept(self, *args): self.calls.append(args); return (self.accepted, "rejected")


class TtsCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_token_grants_are_additive_and_accepted_use_consumes_one(self):
        with tempfile.TemporaryDirectory() as temp:
            service = CommandService(TokenStore(Path(temp, "tokens.json")))
            cog = TtsCog(object(), service)
            mod = Context(Author("Mod", "1", True))
            await TtsCog.tts._callback(cog, mod, "token", "@Viewer")
            await TtsCog.tts._callback(cog, mod, "token", "@Viewer")
            self.assertEqual(2, service.tokens.balance(None, "viewer"))
            viewer = Context(Author("Viewer", "42"))
            await TtsCog.tts._callback(cog, viewer, "[:rate", "300]", "John", "Madden")
            self.assertEqual(1, service.tokens.balance("42", "viewer"))
            self.assertEqual("[:rate 300] John Madden", service.calls[-1][3])

    async def test_rejected_request_does_not_consume_token_and_mod_never_needs_one(self):
        with tempfile.TemporaryDirectory() as temp:
            service = CommandService(TokenStore(Path(temp, "tokens.json"))); service.tokens.grant("viewer")
            cog = TtsCog(object(), service); service.accepted = False
            viewer = Context(Author("Viewer", "42"))
            await TtsCog.tts._callback(cog, viewer, "hello")
            self.assertEqual(1, service.tokens.balance("42", "viewer"))
            mod = Context(Author("Mod", "1", True)); service.accepted = True
            await TtsCog.tts._callback(cog, mod, "hello")
            self.assertEqual(0, service.tokens.balance("1", "mod"))


if __name__ == "__main__": unittest.main()
