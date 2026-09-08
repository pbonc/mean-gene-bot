import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.lore_capture import LoreCaptureService, LoreCaptureSettings
from bot.lore_observability import startup_diagnostics
from bot.lore_store import LoreStore


def incoming(text="chat", author="viewer"):
    return SimpleNamespace(content=text, author=SimpleNamespace(name=author, bot=False),
                           echo=False, channel=SimpleNamespace(name="room"))


def payload(evidence="viewer: chat", statement="durable statement"):
    return json.dumps({"lore": [{"subject": "viewer", "kind": "fact",
        "statement": statement, "aliases": [], "tags": [], "evidence": [evidence],
        "confidence": .8, "observed_at": "2026-09-03T12:00:00+00:00"}]})


class Client:
    def __init__(self, result='{"lore":[]}', error=None, gate=None):
        self.result, self.error, self.gate, self.calls = result, error, gate, 0

    async def run(self, prompt, on_event=None):
        self.calls += 1
        if self.gate:
            await self.gate.wait()
        if self.error:
            raise self.error
        return self.result


class Events:
    def __init__(self): self.items = []
    def __call__(self, name, fields): self.items.append({"event_type": name, **fields})
    def named(self, name): return [x for x in self.items if x["event_type"] == name]


class LoreObservabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = LoreStore(Path(self.temp.name) / "lore.db")
        self.events = Events()

    def tearDown(self): self.temp.cleanup()

    def service(self, client, poster=None, trigger=1, cooldown=0, store=None):
        return LoreCaptureService(store or self.store, client, LoreCaptureSettings(
            enabled=True, trigger_messages=trigger, cooldown_seconds=cooldown),
            moderation_poster=poster, observer=self.events)

    async def run_once(self, service, text="chat"):
        service.capture(incoming(text))
        await asyncio.gather(*list(service._active.values()), return_exceptions=True)

    async def test_success_zero_empty_parse_schema_and_evidence_lifecycles(self):
        cases = [
            (payload(), {"lore.provider.completed", "lore.json.parse", "lore.schema.validation",
                         "lore.persistence.success", "lore.extraction.totals"}),
            ('{"lore":[]}', {"lore.provider.completed", "lore.json.parse",
                              "lore.schema.validation", "lore.extraction.totals"}),
            ("", {"lore.provider.empty"}),
            ("not-json", {"lore.json.parse"}),
            ('{"wrong":[]}', {"lore.schema.validation"}),
            (payload(evidence="absent evidence"), {"lore.candidate.rejected"}),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw[:12]):
                self.events.items.clear()
                await self.run_once(self.service(Client(raw)))
                self.assertTrue(expected.issubset({x["event_type"] for x in self.events.items}))
        self.assertEqual(self.events.named("lore.candidate.rejected")[0]["reason"], "evidence")

    async def test_timeout_failure_and_cancellation(self):
        await self.run_once(self.service(Client(error=asyncio.TimeoutError())))
        self.assertTrue(self.events.named("lore.provider.timed_out"))
        self.events.items.clear()
        await self.run_once(self.service(Client(error=RuntimeError("private details"))))
        self.assertTrue(self.events.named("lore.provider.failed"))
        self.events.items.clear()
        gate = asyncio.Event(); service = self.service(Client(gate=gate))
        service.capture(incoming()); await asyncio.sleep(0); await service.close()
        self.assertTrue(self.events.named("lore.provider.cancelled"))

    async def test_active_and_cooldown_suppression(self):
        gate = asyncio.Event(); service = self.service(Client(gate=gate))
        service.capture(incoming("one")); await asyncio.sleep(0); service.capture(incoming("two"))
        self.assertEqual(self.events.named("lore.capture.suppressed")[-1]["reason"], "active_extraction")
        gate.set(); await asyncio.gather(*list(service._active.values()))
        self.events.items.clear()
        service = self.service(Client(), cooldown=10)
        await self.run_once(service, "one"); service.capture(incoming("two"))
        self.assertEqual(self.events.named("lore.capture.suppressed")[-1]["reason"], "cooldown")

    async def test_persistence_totals_delivery_and_correlation_outcomes(self):
        async def post(record): return 42
        service = self.service(Client(payload()), poster=post)
        await self.run_once(service)
        totals = self.events.named("lore.extraction.totals")[-1]
        self.assertEqual((totals["candidates_returned"], totals["accepted"], totals["rejected"],
                          totals["deduplicated"], totals["stored_pending"], totals["suppressed"]),
                         (1, 1, 0, 0, 1, 0))
        self.assertTrue(self.events.named("lore.moderation.post_success"))
        self.assertTrue(self.events.named("lore.moderation.correlation_success"))
        self.events.items.clear(); await self.run_once(service)
        self.assertEqual(self.events.named("lore.extraction.totals")[-1]["deduplicated"], 1)

        self.events.items.clear()
        async def failed(record): raise RuntimeError("private delivery detail")
        await self.run_once(self.service(Client(payload(statement="different")), poster=failed))
        self.assertTrue(self.events.named("lore.moderation.post_failure"))

        self.events.items.clear()
        with patch.object(self.store, "correlate_discord_message", return_value=False):
            await self.run_once(self.service(Client(payload(statement="third")), poster=post))
        self.assertTrue(self.events.named("lore.moderation.correlation_failure"))

    async def test_persistence_failure_and_rejected_suppression(self):
        class BrokenStore:
            def upsert_captured_lore_observed(self, **kwargs): raise RuntimeError("private db detail")
        await self.run_once(self.service(Client(payload()), store=BrokenStore()))
        self.assertTrue(self.events.named("lore.persistence.failure"))

        candidate = self.store.upsert_captured_lore(channel_scope="room", subject="viewer", kind="fact",
            statement="durable statement", evidence=["viewer: chat"],
            observed_at="2026-09-03T12:00:00+00:00")
        self.store.correlate_discord_message(candidate.id, 9)
        with patch.object(self.store, "_now", return_value="2026-09-03T12:00:01+00:00"):
            self.store.moderate_pending(9, "REJECTED", 7)
        self.events.items.clear(); await self.run_once(self.service(Client(payload()), cooldown=90))
        self.assertEqual(self.events.named("lore.extraction.totals")[-1]["suppressed"], 1)

    def test_startup_summary_and_degraded_state(self):
        settings = LoreCaptureSettings(enabled=True)
        startup_diagnostics(settings, hermes_available=True, moderation_attached=False,
                            observer=self.events)
        summary = self.events.named("lore.startup.summary")[0]
        self.assertEqual((summary["trigger_messages"], summary["cooldown_seconds"],
                          summary["buffer_messages"], summary["input_messages"],
                          summary["input_characters"], summary["max_items"]),
                         (12, 90.0, 40, 24, 6000, 4))
        self.assertTrue(self.events.named("lore.startup.degraded"))

    async def test_privacy_sentinels_never_enter_diagnostics(self):
        sentinels = ["PRIVATE_USER_SENTINEL", "PRIVATE_CHAT_SENTINEL", "PRIVATE_PROMPT_SENTINEL",
                     "PRIVATE_STATEMENT_SENTINEL", "PRIVATE_EVIDENCE_SENTINEL",
                     "PRIVATE_RAW_SENTINEL", "PRIVATE_SECRET_SENTINEL"]
        raw = payload(evidence="PRIVATE_USER_SENTINEL: PRIVATE_CHAT_SENTINEL",
                      statement="PRIVATE_STATEMENT_SENTINEL")
        service = self.service(Client(raw))
        await self.run_once(service, "PRIVATE_CHAT_SENTINEL PRIVATE_PROMPT_SENTINEL")
        await self.run_once(self.service(Client("PRIVATE_RAW_SENTINEL")), "another message")
        await self.run_once(self.service(Client(error=RuntimeError(" ".join(sentinels)))))
        serialized = json.dumps(self.events.items, sort_keys=True)
        for sentinel in sentinels:
            self.assertNotIn(sentinel, serialized)
        allowed_strings = {"event_type", "reason", "outcome"}
        self.assertTrue(all(set(item) - allowed_strings <= {
            "buffer_count", "eligible_count", "message_characters", "input_messages",
            "input_characters", "candidates_returned", "accepted", "rejected",
            "deduplicated", "stored_pending", "suppressed"} for item in self.events.items))

    async def test_real_ingress_more_than_default_threshold(self):
        from tests.offline_main import load_main_offline
        Bot = load_main_offline().Bot
        instance = object.__new__(Bot)
        client = Client('{"lore":[]}')
        instance.lore_capture = LoreCaptureService(self.store, client,
            LoreCaptureSettings(enabled=True), observer=self.events)
        instance.hermes_bridge = SimpleNamespace(submit=lambda message: False)
        instance._touch_twitch_activity = lambda: None
        with patch("bot.main.log_event"), patch("bot.main.broadcast_overlay_message", new=AsyncMock()), \
             patch("twitchio.ext.commands.Bot.event_message", new=AsyncMock()):
            for number in range(13):
                await Bot.event_message(instance, incoming(f"eligible {number}"))
            await asyncio.gather(*list(instance.lore_capture._active.values()))
        self.assertEqual(client.calls, 1)
        self.assertTrue(self.events.named("lore.capture.threshold_reached"))


if __name__ == "__main__": unittest.main()
