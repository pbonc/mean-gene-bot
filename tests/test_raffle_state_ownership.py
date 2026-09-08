"""Offline state tests: extract the model to avoid cog import side effects."""
import ast
import json
import os
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bot.raffle_state import SimpleRaffleState as RaffleProjection


def load_writer_class():
    source = Path(__file__).resolve().parents[1] / "bot/commands/raffle_cog.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    model = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                 and node.name == "SimpleRaffleState")
    namespace = {"json": json, "os": os, "random": random,
                 "RAFFLE_STATE_FILE": None}
    exec(compile(ast.Module(body=[model], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["SimpleRaffleState"]


RaffleWriter = load_writer_class()
UNION_STATE = {
    "entries": {"alice": 10}, "picks": {"007": "alice"},
    "prize": {"description": "Legacy prize"},
    "is_open": True, "entries_per_chat": 3, "winner": "bob",
    "giveaway_jail_user": "bob", "winning_number": "123",
    "chat_awarded": ["alice"], "first_chatter_awarded": True,
    "first_chatter_user": "alice", "ignored_users": ["ignored"],
    "bad_beat_jackpot": 50, "giveaway_amount": 20.5,
    "zap_active": True, "zap_start_time": 1000,
    "zap_target_seconds": 600, "zap_awarded_user": None,
    "zap_trigger_announced": True, "zap_trigger_type": "chat",
    "zap_announcement_sent": True,
    "future_field": {"nested": [1, None, {"enabled": True}]},
}


class RaffleOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "raffle.json"
        self.path.write_text(json.dumps(UNION_STATE), encoding="utf-8")

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_current_writer_read_consumers_remain_supported(self):
        before = self.path.read_bytes()
        writer = RaffleWriter(self.path)
        # Labels/analytics, follower awards, and raffle command reads.
        self.assertEqual(20.5, writer.get_giveaway_amount())
        self.assertEqual(50, writer.bad_beat_jackpot)
        self.assertTrue(writer.is_open)
        self.assertEqual(10, writer.user_entries("ALICE"))
        self.assertEqual(["007"], writer.user_picks("ALICE"))
        self.assertEqual(["ignored"], writer.get_ignored_users())
        self.assertEqual(before, self.path.read_bytes())

    def test_legacy_read_order_case_and_refresh_are_preserved(self):
        data = dict(UNION_STATE, picks={"100": "alice", "002": "alice"})
        self.path.write_text(json.dumps(data), encoding="utf-8")
        view = RaffleProjection(self.path)
        self.assertEqual(["002", "100"], view.user_picks("alice"))
        self.assertEqual([], view.user_picks("ALICE"))
        self.assertEqual(0, view.available_entries("ALICE"))
        self.assertEqual([("002", "alice"), ("100", "alice")], view.all_picks())
        data["picks"] = {"009": "bob"}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        view.load()
        self.assertEqual([("009", "bob")], view.all_picks())

    def test_actual_labels_read_consumers(self):
        source = Path(__file__).resolve().parents[1] / 'bot/labels_stats.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        names = {'get_raffle_prize', 'get_raffle_odds', 'get_raffle_encouragement'}
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in names]
        # Execute real consumer functions without importing sports/weather providers.
        path_api = SimpleNamespace(dirname=os.path.dirname, isfile=os.path.isfile,
                                   join=lambda *parts: str(self.path))
        namespace = {'os': SimpleNamespace(path=path_api), '__file__': str(source)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        before = self.path.read_bytes()
        with patch.dict('sys.modules', {'bot.commands.raffle_cog':
                        SimpleNamespace(SimpleRaffleState=RaffleWriter)}):
            self.assertEqual(20.5, namespace['get_raffle_prize']())
        self.assertEqual('Raffle Odds: 1/1000', namespace['get_raffle_odds']())
        self.assertEqual(before, self.path.read_bytes())

    def test_actual_analytics_read_and_write_consumers(self):
        source = Path(__file__).resolve().parents[1] / 'bot/stream_analytics.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        names = {'get_current_giveaway_amount', '_update_giveaway_amount'}
        nodes = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name in names]
        namespace = {'os': os}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        # The actual consumer uses raffle_state.json under its injected data_dir.
        consumer_path = self.path.parent / 'raffle_state.json'
        consumer_path.write_bytes(self.path.read_bytes())
        consumer = SimpleNamespace(analytics=SimpleNamespace(data_dir=str(self.path.parent)))
        before = consumer_path.read_bytes()
        with patch.dict('sys.modules', {'bot.commands.raffle_cog':
                        SimpleNamespace(SimpleRaffleState=RaffleWriter)}):
            self.assertEqual(20.5, namespace['get_current_giveaway_amount'](consumer))
            self.assertEqual(before, consumer_path.read_bytes())
            import asyncio
            asyncio.run(namespace['_update_giveaway_amount'](consumer, 75))
        self.assertEqual(dict(UNION_STATE, giveaway_amount=75.0),
                         json.loads(consumer_path.read_text()))

    def test_union_round_trip(self):
        RaffleWriter(self.path).save()
        self.assertEqual(UNION_STATE, self.read())

    def test_projection_has_no_write_capability(self):
        before = self.path.read_bytes()
        view = RaffleProjection(self.path)
        self.assertEqual(1, len(view.picks))
        self.assertEqual(10, view.available_entries("alice"))
        self.assertEqual(["007"], view.user_picks("alice"))
        self.assertEqual([("007", "alice")], view.all_picks())
        self.assertEqual(UNION_STATE["prize"], view.prize)
        for method in ("save", "set_prize", "add_entries", "use_entry", "pick_number", "reset"):
            self.assertFalse(hasattr(view, method))
        with self.assertRaises(TypeError):
            view.picks["008"] = "alice"
        with self.assertRaises(TypeError):
            view.entries["alice"] = 0
        # Even replacing local attributes or mutating a nested legacy prize
        # cannot write through this projection or alter the writer's snapshot.
        view.prize['description'] = 'local only'
        view.entries = {'alice': 0}
        view.picks = {'999': 'bob'}
        self.assertEqual(UNION_STATE['prize'], RaffleProjection(self.path).prize)
        self.assertEqual(before, self.path.read_bytes())

    def test_projection_then_authorized_update_preserves_fields(self):
        view = RaffleProjection(self.path)
        writer = RaffleWriter(self.path)
        self.assertTrue(writer.set_giveaway_amount(75))
        expected = dict(UNION_STATE, giveaway_amount=75.0)
        self.assertEqual(expected, self.read())
        view.load()
        self.assertEqual(UNION_STATE["picks"], dict(view.picks))
        self.assertEqual(expected, self.read())

    def test_missing_projection_does_not_create_state(self):
        path = Path(self.directory.name) / "missing.json"
        self.assertEqual({}, dict(RaffleProjection(path).picks))
        self.assertFalse(path.exists())

    def test_invalid_projection_does_not_repair_state(self):
        self.path.write_text("invalid json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            RaffleProjection(self.path)
        self.assertEqual("invalid json", self.path.read_text(encoding="utf-8"))
        self.assertEqual([self.path], list(Path(self.directory.name).iterdir()))

    def test_existing_pick_validation_and_awards(self):
        writer = RaffleWriter(self.path)
        before = self.path.read_bytes()
        self.assertFalse(writer.pick_numbers("alice", ["007"])[0])
        self.assertFalse(writer.pick_numbers("bob", ["008"])[0])
        self.assertFalse(writer.add_entries("ignored", 10))
        self.assertEqual(before, self.path.read_bytes())
        self.assertTrue(writer.pick_numbers("ALICE", ["008"])[0])
        self.assertEqual(9, writer.user_entries("alice"))
        self.assertEqual(["007", "008"], writer.user_picks("alice"))
        self.assertEqual(3, writer.award_chat_entry("carol"))
        self.assertEqual(0, writer.award_chat_entry("carol"))
        self.assertEqual(UNION_STATE["future_field"], self.read()["future_field"])

    def test_reset_preserves_balances_jackpot_and_unknown_fields(self):
        writer = RaffleWriter(self.path)
        writer.reset()
        persisted = self.read()
        self.assertEqual({}, persisted["picks"])
        self.assertEqual(UNION_STATE["entries"], persisted["entries"])
        self.assertEqual(50, persisted["bad_beat_jackpot"])
        self.assertEqual(0.0, persisted["giveaway_amount"])
        self.assertEqual(UNION_STATE["prize"], persisted["prize"])
        self.assertEqual(UNION_STATE["future_field"], persisted["future_field"])

    def test_load_refreshes_retained_fields(self):
        writer = RaffleWriter(self.path)
        self.path.write_text(json.dumps(dict(UNION_STATE, future_field="new")), encoding="utf-8")
        writer.load()
        writer.close_raffle()
        self.assertEqual("new", self.read()["future_field"])
        self.assertFalse(self.read()["is_open"])


if __name__ == "__main__":
    unittest.main()
