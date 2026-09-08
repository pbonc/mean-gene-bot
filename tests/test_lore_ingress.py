import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from bot.lore_capture import LoreCaptureService, LoreCaptureSettings
from bot.lore_store import LoreStore
from tests.offline_main import load_main_offline
Bot = load_main_offline().Bot


class Client:
    def __init__(self, result='{"lore":[]} ', error=None):
        self.result, self.error, self.prompts = result, error, []

    async def run(self, prompt, on_event=None):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.result


class Bridge:
    def __init__(self):
        self.messages = []

    def submit(self, message):
        self.messages.append(message)
        return False


def message(text="hello", author="human", *, echo=False, bot=False):
    return SimpleNamespace(
        content=text, echo=echo,
        author=SimpleNamespace(name=author, bot=bot),
        channel=SimpleNamespace(name="room"),
    )


class LoreIngressTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LoreStore(Path(self.tmp.name) / "lore.db")

    def tearDown(self):
        self.tmp.cleanup()

    def make_bot(self, client, poster=None, **settings):
        instance = Bot.__new__(Bot)
        instance._last_twitch_activity = 0
        instance.lore_capture = LoreCaptureService(
            self.store, client,
            LoreCaptureSettings(enabled=True, trigger_messages=1, cooldown_seconds=0,
                                **settings),
            moderation_poster=poster,
        )
        instance.hermes_bridge = Bridge()
        return instance

    async def ingress(self, instance, incoming):
        base = AsyncMock()
        with patch("bot.main.broadcast_overlay_message", new=AsyncMock()), \
             patch("bot.main.log_event"), \
             patch("twitchio.ext.commands.Bot.event_message", new=base):
            await Bot.event_message(instance, incoming)
        return base

    async def test_capture_eligibility_at_real_event_message_boundary(self):
        cases = [
            ("echo", message(echo=True), {}, False),
            ("configured id", message(author="MeanGeneBot"),
             {"own_usernames": frozenset({"meangenebot", "mean_gene_bot"})}, False),
            ("configured name", message(author="Mean_Gene_Bot"),
             {"own_usernames": frozenset({"meangenebot", "mean_gene_bot"})}, False),
            ("generic bot signal", message(author="AnyService", bot=True), {}, False),
            ("configured arbitrary username case-insensitively",
             message(author="CuStOmHeLpEr"),
             {"ignore_users": frozenset({"customhelper"})}, False),
            ("explicitly configured service name", message(author="NiGhTbOt"),
             {"ignore_users": frozenset({"nightbot"})}, False),
            ("unconfigured Nightbot is not special-cased", message(author="Nightbot"), {}, True),
            ("unconfigured Streamlabs is not special-cased", message(author="Streamlabs"), {}, True),
            ("command", message("!fish gps"), {}, False),
            ("eligible human", message("human conversation"), {}, True),
        ]
        for label, incoming, settings, eligible in cases:
            with self.subTest(label=label):
                client = Client()
                instance = self.make_bot(client, **settings)
                base = await self.ingress(instance, incoming)
                await asyncio.gather(*list(instance.lore_capture._active.values()))
                self.assertEqual(bool(client.prompts), eligible)
                base.assert_awaited_once_with(incoming)

    async def test_extraction_database_and_discord_failures_are_isolated_at_ingress(self):
        payload = json.dumps({"lore": [{
            "subject": "human", "kind": "fact", "statement": "Human likes pie",
            "aliases": [], "tags": [], "evidence": ["human: likes pie"],
            "confidence": 0.8, "observed_at": "2026-09-03T12:00:00+00:00",
        }]})
        scenarios = []
        scenarios.append(("extraction", Client(error=RuntimeError("offline")), None, None))
        scenarios.append(("database", Client(payload), None, RuntimeError("db offline")))

        async def failed_post(record):
            raise RuntimeError("discord offline")
        scenarios.append(("discord post", Client(payload), failed_post, None))

        for label, client, poster, database_error in scenarios:
            with self.subTest(label=label):
                instance = self.make_bot(client, poster=poster)
                incoming = message("likes pie")
                database_patch = (
                    patch.object(instance.lore_capture.store, "upsert_captured_lore",
                                 new=Mock(side_effect=database_error))
                    if database_error else patch("builtins.id", wraps=id)
                )
                with database_patch:
                    base = await self.ingress(instance, incoming)
                    await asyncio.gather(*list(instance.lore_capture._active.values()),
                                         return_exceptions=True)
                base.assert_awaited_once_with(incoming)


if __name__ == "__main__":
    unittest.main()
