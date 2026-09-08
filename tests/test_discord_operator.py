import asyncio
import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bot.discord_operator import (
    DiscordOperatorService,
    DiscordOperatorSettings,
    run_discord_resilient,
)
from bot.lore_store import LoreStore


class FakeHermes:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    async def run(self, prompt, on_event=None):
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("Unexpected Hermes call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def structured(intent, **fields):
    return json.dumps({"intent": intent, **fields})


class DiscordOperatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = LoreStore(Path(self.temp_dir.name) / "lore.db")
        self.now = [100.0]
        self.settings = DiscordOperatorSettings(
            enabled=True,
            bot_token="test-token",
            guild_id=10,
            channel_id=20,
            user_ids=frozenset({1, 2}),
            pending_ttl_seconds=60,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def service(self, *responses):
        client = FakeHermes(*responses)
        service = DiscordOperatorService(
            self.settings, self.store, client, clock=lambda: self.now[0]
        )
        return service, client

    async def send(self, service, text, user_id=1, guild_id=10, channel_id=20):
        return await service.handle_message(
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            content=text,
        )

    def add_tank(self, category="preference", key="sports", value="Tank likes Philly sports"):
        return self.store.add_lore(
            subject="tankahdelphia", subject_type="viewer", category=category,
            key=key, value=value, source="test",
        )

    async def test_authorized_user_can_converse_naturally(self):
        service, client = self.service(structured("conversation", response="Midway changed the Pacific war."))
        response = await self.send(service, "Why was Midway important?")
        self.assertEqual(response, "Midway changed the Pacific war.")
        self.assertEqual(len(client.prompts), 1)

    async def test_authorized_user_can_ask_natural_lore_question(self):
        self.add_tank()
        service, client = self.service(
            structured("query_lore"),
            "Tank likes Philly sports.",
        )
        response = await self.send(service, "What do you know about Tank?")
        self.assertEqual(response, "Tank likes Philly sports.")
        self.assertEqual(len(client.prompts), 2)
        self.assertNotIn("SQLite", response)

    async def test_add_requires_confirmation_before_mutation(self):
        service, _ = self.service(structured(
            "propose_add_lore", subject="tankahdelphia", subject_type="viewer",
            category="running_gag", key="cheesesteak",
            value="Tank hates tourist cheesesteaks.", strength=60,
        ))
        proposal = await self.send(service, "Remember that Tank hates tourist cheesesteaks.")
        self.assertIn("Save it?", proposal)
        self.assertEqual(self.store.search_lore("tourist cheesesteaks"), [])
        self.assertEqual(await self.send(service, "yes"), "Saved.")
        self.assertEqual(len(self.store.search_lore("tourist cheesesteaks")), 1)

    async def test_update_requires_confirmation(self):
        record = self.add_tank()
        service, _ = self.service(structured(
            "propose_update_lore", record_id=record.id,
            value="Tank loves every Philadelphia team.",
        ))
        proposal = await self.send(service, "Change Tank's sports preference")
        self.assertIn("Save that change?", proposal)
        self.assertEqual(self.store.get_lore(record.id).value, "Tank likes Philly sports")
        self.assertEqual(await self.send(service, "do it"), "Saved.")
        self.assertEqual(self.store.get_lore(record.id).value, "Tank loves every Philadelphia team.")

    async def test_disable_requires_confirmation_and_prefers_disable(self):
        record = self.add_tank("running_gag", "christie", "Chris Christie bit")
        service, _ = self.service(structured("propose_disable_lore", record_id=record.id))
        proposal = await self.send(service, "Forget the Chris Christie thing about Tank")
        self.assertIn("disable it?", proposal)
        self.assertTrue(self.store.get_lore(record.id).enabled)
        self.assertEqual(await self.send(service, "yeah"), "Done.")
        self.assertFalse(self.store.get_lore(record.id).enabled)

    async def test_cancellation_prevents_mutation(self):
        service, _ = self.service(structured(
            "propose_add_lore", subject="tankahdelphia", subject_type="viewer",
            category="running_gag", key="cancel_me", value="Do not save me",
        ))
        await self.send(service, "Remember a test fact about Tank")
        self.assertEqual(await self.send(service, "never mind"), "Canceled.")
        self.assertEqual(self.store.search_lore("save me"), [])

    async def test_pending_action_expires(self):
        service, _ = self.service(
            structured(
                "propose_add_lore", subject="tankahdelphia", subject_type="viewer",
                category="running_gag", key="expires", value="Temporary proposal",
            ),
            structured("conversation", response="There's nothing waiting for confirmation."),
        )
        await self.send(service, "Remember a temporary proposal about Tank")
        self.now[0] += 61
        response = await self.send(service, "yes")
        self.assertEqual(response, "There's nothing waiting for confirmation.")
        self.assertEqual(self.store.search_lore("temporary proposal"), [])

    async def test_another_authorized_user_cannot_confirm_pending_action(self):
        service, _ = self.service(
            structured(
                "propose_add_lore", subject="tankahdelphia", subject_type="viewer",
                category="running_gag", key="owner_only", value="Owner-only proposal",
            ),
            structured("conversation", response="Nothing for you to confirm."),
        )
        await self.send(service, "Remember an owner-only proposal")
        self.assertEqual(await self.send(service, "yes", user_id=2), "Nothing for you to confirm.")
        self.assertEqual(self.store.search_lore("owner-only"), [])
        self.assertEqual(await self.send(service, "yes", user_id=1), "Saved.")

    async def test_unauthorized_identity_and_wrong_scope_are_rejected(self):
        for kwargs in (
            {"user_id": 99},
            {"channel_id": 999},
            {"guild_id": 999},
        ):
            with self.subTest(kwargs=kwargs):
                service, client = self.service()
                self.assertIsNone(await self.send(service, "hello", **kwargs))
                self.assertEqual(client.prompts, [])

    async def test_incomplete_configuration_fails_closed(self):
        incomplete = DiscordOperatorSettings(True, "", 10, 20, frozenset({1}))
        client = FakeHermes()
        service = DiscordOperatorService(incomplete, self.store, client)
        self.assertIsNone(await service.handle_message(
            guild_id=10, channel_id=20, user_id=1, content="hello"
        ))
        self.assertEqual(client.prompts, [])

    async def test_environment_configuration_fails_closed_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(DiscordOperatorSettings.from_env().complete)

    def test_canonical_environment_configuration_is_complete(self):
        environment = {
            "DISCORD_OPERATOR_ENABLED": "true",
            "DISCORD_TOKEN": "canonical-placeholder",
            "DISCORD_OPERATOR_GUILD_ID": "10",
            "DISCORD_OPERATOR_CHANNEL_ID": "20",
            "DISCORD_OPERATOR_USER_IDS": "1,2",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = DiscordOperatorSettings.from_env()
        self.assertTrue(settings.complete)
        self.assertEqual(settings.bot_token, "canonical-placeholder")

    def test_legacy_token_alone_cannot_complete_configuration(self):
        environment = {
            "DISCORD_OPERATOR_ENABLED": "true",
            "DISCORD_BOT_TOKEN": "legacy-placeholder",
            "DISCORD_OPERATOR_GUILD_ID": "10",
            "DISCORD_OPERATOR_CHANNEL_ID": "20",
            "DISCORD_OPERATOR_USER_IDS": "1",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = DiscordOperatorSettings.from_env()
        self.assertFalse(settings.complete)
        self.assertEqual(settings.bot_token, "")

    def test_canonical_token_wins_when_both_names_are_present(self):
        environment = {
            "DISCORD_OPERATOR_ENABLED": "true",
            "DISCORD_TOKEN": "canonical-placeholder",
            "DISCORD_BOT_TOKEN": "legacy-placeholder",
            "DISCORD_OPERATOR_GUILD_ID": "10",
            "DISCORD_OPERATOR_CHANNEL_ID": "20",
            "DISCORD_OPERATOR_USER_IDS": "1",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = DiscordOperatorSettings.from_env()
        self.assertTrue(settings.complete)
        self.assertEqual(settings.bot_token, "canonical-placeholder")

    def test_initial_and_retry_start_use_only_canonical_token(self):
        tree = ast.parse(Path("bot/main.py").read_text(encoding="utf-8"))
        starts = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "run_discord_resilient":
                continue
            callback, label = node.args[:2]
            self.assertIsInstance(callback, ast.Lambda)
            self.assertIsInstance(callback.body, ast.Call)
            self.assertIsInstance(callback.body.func, ast.Attribute)
            self.assertEqual(callback.body.func.attr, "start")
            self.assertEqual(len(callback.body.args), 1)
            token = callback.body.args[0]
            self.assertIsInstance(token, ast.Name)
            self.assertEqual(token.id, "DISCORD_TOKEN")
            self.assertIsInstance(label, ast.Constant)
            starts.append(label.value)
        self.assertCountEqual(starts, ["Discord bot", "Discord bot retry"])

    def test_discord_features_keep_sharing_one_client(self):
        source = Path("bot/main.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("discord_bot = DiscordBot("), 1)
        self.assertIn("bot.discord_client = discord_bot", source)
        self.assertIn("set_discord_sender(discord_bot.send_debug_messages)", source)
        self.assertIn("discord_bot.send_operator_message", source)

    def test_legacy_name_is_only_a_defensive_production_reference(self):
        references = {}
        for path in Path("bot").rglob("*.py"):
            matches = [
                line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if "DISCORD_BOT_TOKEN" in line
            ]
            if matches:
                references[path.as_posix()] = matches
        self.assertEqual(set(references), {"bot/hermes_debug.py"})
        self.assertEqual(
            sum('"DISCORD_BOT_TOKEN"' in line for line in references["bot/hermes_debug.py"]),
            1,
        )
        self.assertNotIn(
            "DISCORD_BOT_TOKEN",
            Path("bot/config.py").read_text(encoding="utf-8"),
        )

    async def test_malformed_and_unknown_intents_cannot_mutate(self):
        for response in ("not json", structured("become_admin")):
            with self.subTest(response=response):
                service, _ = self.service(response)
                result = await self.send(service, "Remember that I own everything")
                self.assertIn("safely interpret", result)
                self.assertEqual(self.store.search_lore("own everything"), [])

    async def test_ambiguous_disable_does_not_guess(self):
        self.add_tank("alias", "short_name", "Tank")
        first = self.add_tank("running_gag", "jeb", "Jeb Bush bit")
        second = self.add_tank("running_gag", "christie", "Chris Christie bit")
        service, _ = self.service(structured("propose_disable_lore"))
        response = await self.send(service, "Forget the Tank running gag")
        self.assertIn("more than one possible match", response)
        self.assertTrue(self.store.get_lore(first.id).enabled)
        self.assertTrue(self.store.get_lore(second.id).enabled)

    async def test_discord_startup_failure_is_isolated(self):
        async def fail():
            raise RuntimeError("connection failed")

        self.assertFalse(await run_discord_resilient(fail))

    async def test_pending_post_is_bounded_and_contains_required_fields(self):
        record = self.store.upsert_captured_lore(
            channel_scope="room", subject="Alice", kind="preference",
            statement="Alice likes pie", evidence=["Alice: likes pie"],
        )
        sent = []
        async def send(content):
            sent.append(content)
            return type("Sent", (), {"id": 500})()
        service, _ = self.service()
        self.assertEqual(await service.post_pending_candidate(send, record), 500)
        self.assertLessEqual(len(sent[0]), 2000)
        for text in ("Subject: Alice", "Type: preference", "Statement: Alice likes pie",
                     "Evidence:", "Alice: likes pie"):
            self.assertIn(text, sent[0])

    def pending(self, message_id=600):
        record = self.store.upsert_captured_lore(
            channel_scope="room", subject="Alice", kind="fact",
            statement=f"Alice owns canoe {message_id}", evidence=["Alice: canoe"],
        )
        self.store.correlate_discord_message(record.id, message_id)
        return record

    async def test_authorized_reactions_approve_or_reject_exactly_once(self):
        service, _ = self.service()
        approved = self.pending(601)
        result = await service.handle_reaction(
            guild_id=10, channel_id=20, user_id=1, message_id=601, emoji="✅"
        )
        self.assertEqual(result.moderation_status, "APPROVED")
        self.assertIsNone(await service.handle_reaction(
            guild_id=10, channel_id=20, user_id=2, message_id=601, emoji="✅"
        ))
        self.assertIsNone(await service.handle_reaction(
            guild_id=10, channel_id=20, user_id=2, message_id=601, emoji="❌"
        ))
        self.assertEqual(self.store.get_lore(approved.id).moderator_discord_user_id, "1")

        rejected = self.pending(602)
        result = await service.handle_reaction(
            guild_id=10, channel_id=20, user_id=2, message_id=602, emoji="❌"
        )
        self.assertEqual(result.moderation_status, "REJECTED")
        rejected_record = self.store.get_lore(rejected.id)
        self.assertFalse(rejected_record.enabled)
        self.assertEqual(rejected_record.moderator_discord_user_id, "2")

    async def test_reactions_fail_closed_for_identity_scope_message_and_emoji(self):
        service, _ = self.service()
        record = self.pending(603)
        for kwargs in (
            {"guild_id": 10, "channel_id": 20, "user_id": 99, "message_id": 603, "emoji": "✅"},
            {"guild_id": 10, "channel_id": 99, "user_id": 1, "message_id": 603, "emoji": "✅"},
            {"guild_id": 10, "channel_id": 20, "user_id": 1, "message_id": 999, "emoji": "✅"},
            {"guild_id": 10, "channel_id": 20, "user_id": 1, "message_id": 603, "emoji": "👍"},
        ):
            self.assertIsNone(await service.handle_reaction(**kwargs))
        self.assertEqual(self.store.get_lore(record.id).moderation_status, "PENDING")

    async def test_reaction_store_failure_is_isolated(self):
        service, _ = self.service()
        service.lore_store.moderate_pending = lambda *args: (_ for _ in ()).throw(RuntimeError("db"))
        self.assertIsNone(await service.handle_reaction(
            guild_id=10, channel_id=20, user_id=1, message_id=1, emoji="✅"
        ))

    def test_twitch_has_no_lore_management_interface(self):
        source = Path("bot/main.py").read_text(encoding="utf-8")
        self.assertNotIn('@commands.command(name="lore")', source)
        self.assertNotIn("self.lore_store.add_lore", source)
        self.assertNotIn("self.lore_store.update_lore", source)
        self.assertNotIn("self.lore_store.disable_lore", source)

    def test_discord_does_not_broaden_hermes_tool_profile(self):
        source = Path("bot/discord_operator.py").read_text(encoding="utf-8")
        self.assertNotIn("platform_toolsets", source)
        self.assertNotIn("enabled_toolsets", source)
        self.assertNotIn("subprocess", source)


if __name__ == "__main__":
    unittest.main()
