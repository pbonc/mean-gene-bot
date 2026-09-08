import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bot.hermes_bridge import HermesChatBridge, HermesRunObservation, HermesSettings
from bot.hermes_debug import (
    DEFENSIVE_SECRET_ENV_NAMES,
    HermesDebugSettings,
    HermesFlightRecorder,
    defensive_secrets_from_env,
)
from bot.research_policy import ResearchDecision


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


class EventClient:
    def __init__(self, answer="**Gene:** final answer", delay=0, events=()):
        self.answer = answer
        self.delay = delay
        self.events = events

    async def run(self, prompt, on_event=None):
        if on_event:
            on_event("submitted", "run_debug")
            on_event("events.connected", "run_debug")
            on_event("running", "run_debug")
            for event in self.events:
                on_event(f"tool.{event.get('tool', '')}", "run_debug", event)
        await asyncio.sleep(self.delay)
        if on_event:
            on_event("completed", "run_debug")
        return self.answer


def message(content="@MeanGeneBot research this", user="iamdar"):
    return SimpleNamespace(
        content=content,
        author=SimpleNamespace(name=user, is_mod=True, is_broadcaster=True),
        channel=FakeChannel(),
        echo=False,
    )


def bridge_settings(**changes):
    values = dict(
        enabled=True,
        api_key="test-key",
        acknowledgment_delay_seconds=1,
        request_timeout_seconds=2,
        user_cooldown_seconds=0,
        global_cooldown_seconds=0,
    )
    values.update(changes)
    return HermesSettings(**values)


class HermesDebugTests(unittest.IsolatedAsyncioTestCase):
    async def test_research_recovery_metadata_and_attempt_evidence_are_separate(self):
        recorder = self.recorder()
        flight = recorder.start(username="dar", original_request="score?", final_prompt="p", lore_records=())
        recorder.set_research_policy(
            flight, ResearchDecision(True, "current_sports_result", "sports_result_plus_relative_date")
        )
        recorder.start_attempt(flight, "initial")
        recorder.observe(flight, {"event": "tool.completed", "run_id": "run_initial", "tool": "web_search", "error": True})
        initial = HermesRunObservation(run_id="run_initial", terminal_status="completed", event_stream_connected=True, event_stream_drained=True, failed_tool_completions=1)
        recorder.finish_attempt(flight, "initial", initial)
        recorder.start_attempt(flight, "recovery")
        recorder.observe(flight, {
            "event": "tool.completed", "run_id": "run_recovery", "tool": "web_search", "error": False,
            "result_preview": json.dumps({"data": {"web": [{"url": "https://sports.test", "description": "won"}]}}),
        })
        recovery = HermesRunObservation(run_id="run_recovery", terminal_status="completed", event_stream_connected=True, event_stream_drained=True, successful_web_searches=1)
        recorder.finish_attempt(flight, "recovery", recovery)
        await recorder.finish(
            flight, status="completed", latency_seconds=2, raw_answer="won",
            twitch_messages=("@dar won",), search_requirement_satisfied=True,
            delivered_attempt="recovery", recovery_result="searched_and_answered",
        )
        record = self.records()[0]
        self.assertTrue(record["research_required"])
        self.assertTrue(record["initial_answer_withheld"])
        self.assertEqual(record["initial_run_id"], "run_initial")
        self.assertEqual(record["recovery_run_id"], "run_recovery")
        self.assertEqual(record["delivered_attempt"], "recovery")
        self.assertEqual(record["observable_events"][0]["attempt"], "initial")
        self.assertEqual(record["observable_events"][1]["attempt"], "recovery")
        self.assertEqual(record["observable_tool_result_evidence"][0]["attempt"], "recovery")

    async def test_research_fallback_metadata_is_explicit_and_redacted(self):
        recorder = self.recorder()
        flight = recorder.start(username="dar", original_request="look up token=exact-secret", final_prompt="p", lore_records=())
        recorder.set_research_policy(flight, ResearchDecision(True, "explicit_research", "explicit_research_request"))
        recorder.start_attempt(flight, "initial")
        recorder.finish_attempt(flight, "initial", HermesRunObservation(run_id="one", terminal_status="completed", event_stream_drained=True))
        recorder.start_attempt(flight, "recovery")
        recorder.finish_attempt(flight, "recovery", HermesRunObservation(run_id="two", terminal_status="completed", event_stream_drained=False))
        await recorder.finish(
            flight, status="completed", latency_seconds=1,
            twitch_messages=("@dar safe fallback",), search_requirement_satisfied=False,
            delivered_attempt="deterministic_fallback", recovery_result="retrieval_requirement_failed",
        )
        serialized = self.log_path.read_text(encoding="utf-8")
        self.assertNotIn("exact-secret", serialized)
        record = self.records()[0]
        self.assertFalse(record["search_requirement_satisfied"])
        self.assertEqual(record["delivered_attempt"], "deterministic_fallback")
        self.assertEqual(record["recovery_result"], "retrieval_requirement_failed")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.temp_dir.name) / "debug.jsonl"

    def tearDown(self):
        self.temp_dir.cleanup()

    def recorder(self, **changes):
        values = dict(enabled=True, log_file=str(self.log_path), max_evidence_chars=1200)
        values.update(changes)
        return HermesFlightRecorder(HermesDebugSettings(**values), secrets=("exact-secret",))

    def records(self):
        if not self.log_path.exists():
            return []
        return [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]

    async def test_debug_disabled_leaves_existing_behavior_and_no_file(self):
        recorder = HermesFlightRecorder(HermesDebugSettings(enabled=False, log_file=str(self.log_path)))
        bridge = HermesChatBridge(bridge_settings(), EventClient(answer="answer"), debug_recorder=recorder)
        msg = message()
        self.assertTrue(bridge.submit(msg))
        await asyncio.gather(*bridge._tasks)
        self.assertEqual(msg.channel.sent, ["@iamdar answer"])
        self.assertFalse(self.log_path.exists())

    async def test_web_search_multiple_tools_and_final_twitch_answer_are_recorded(self):
        events = (
            {"event": "tool.started", "run_id": "run_debug", "timestamp": 1, "tool": "web_search", "preview": "Battle of Midway aircraft totals"},
            {"event": "tool.completed", "run_id": "run_debug", "timestamp": 2, "tool": "web_search", "duration": 1.25, "error": False},
            {"event": "tool.started", "run_id": "run_debug", "timestamp": 3, "tool": "web_extract", "preview": "https://history.example/midway"},
            {"event": "tool.completed", "run_id": "run_debug", "timestamp": 4, "tool": "web_extract", "duration": 0.5, "error": False},
        )
        bridge = HermesChatBridge(
            bridge_settings(), EventClient(events=events), debug_recorder=self.recorder()
        )
        msg = message("@MeanGeneBot how many aircraft were at Midway?")
        self.assertTrue(bridge.submit(msg))
        await asyncio.gather(*bridge._tasks)
        record = self.records()[0]
        self.assertEqual(record["hermes_run_id"], "run_debug")
        self.assertEqual(record["run_status"], "completed")
        self.assertEqual(record["final_twitch_messages"], ["@iamdar final answer"])
        self.assertEqual(len(record["observable_events"]), 4)
        self.assertEqual(record["observable_events"][0]["search_query_preview"], "Battle of Midway aircraft totals")
        self.assertEqual(record["observable_events"][2]["extract_target_preview"], "https://history.example/midway")
        self.assertEqual(record["observable_tool_result_evidence"], [])

    async def test_tool_failure_and_no_web_tool_runs(self):
        recorder = self.recorder()
        failed = recorder.start(username="one", original_request="q1", final_prompt="p1", lore_records=())
        recorder.observe(failed, {"event": "tool.started", "run_id": "run_fail", "tool": "web_search", "preview": "query"})
        recorder.observe(failed, {"event": "reasoning.available", "run_id": "run_fail", "text": "private reasoning"})
        recorder.observe(failed, {"event": "tool.completed", "run_id": "run_fail", "tool": "web_search", "duration": 2, "error": True})
        empty = recorder.start(username="two", original_request="q2", final_prompt="p2", lore_records=())
        empty.run_id = "run_empty"
        await recorder.finish(failed, status="failed", latency_seconds=2, error="tool failed")
        await recorder.finish(empty, status="completed", latency_seconds=1, raw_answer="hello", twitch_messages=("@two hello",))
        by_run = {record["hermes_run_id"]: record for record in self.records()}
        self.assertTrue(by_run["run_fail"]["observable_events"][1]["error"])
        self.assertNotIn("private reasoning", json.dumps(by_run["run_fail"]))
        self.assertEqual(by_run["run_empty"]["observable_events"], [])

    async def test_timeout_is_recorded(self):
        bridge = HermesChatBridge(
            bridge_settings(request_timeout_seconds=0.04, acknowledgment_delay_seconds=0.01),
            EventClient(delay=1),
            debug_recorder=self.recorder(),
            acknowledgment_picker=lambda choices: choices[0],
        )
        msg = message()
        self.assertTrue(bridge.submit(msg))
        await asyncio.gather(*bridge._tasks)
        record = self.records()[0]
        self.assertEqual(record["run_status"], "timeout")
        self.assertIn("timed out", record["bridge_error"])
        self.assertEqual(record["final_twitch_messages"][-1], "@iamdar Gene ran outta time. Try me again.")

    async def test_evidence_preview_truncation_and_secret_redaction(self):
        recorder = self.recorder(max_evidence_chars=100)
        flight = recorder.start(
            username="dar",
            original_request="token=exact-secret oauth:abcdef",
            final_prompt="Authorization: Bearer abc.def and password=hunter2",
            lore_records=(),
        )
        recorder.observe(flight, {
            "event": "tool.started", "run_id": "run_secret", "tool": "web_search",
            "preview": "x" * 200 + " exact-secret",
        })
        await recorder.finish(
            flight, status="completed", latency_seconds=1,
            raw_answer="https://discord.com/api/webhooks/123/secret",
            twitch_messages=("token=abc123",),
        )
        serialized = self.log_path.read_text(encoding="utf-8")
        self.assertNotIn("exact-secret", serialized)
        self.assertNotIn("hunter2", serialized)
        self.assertNotIn("abc.def", serialized)
        self.assertNotIn("/123/secret", serialized)
        event = self.records()[0]["observable_events"][0]
        self.assertEqual(len(event["preview"]), 100)
        self.assertTrue(event["preview_truncated_by_mgb"])

    async def test_search_and_extract_evidence_are_structured_and_bounded(self):
        recorder = self.recorder(max_evidence_chars=120)
        flight = recorder.start(username="dar", original_request="score?", final_prompt="prompt", lore_records=())
        recorder.observe(flight, {
            "event": "tool.started", "run_id": "run_evidence", "tool": "web_search",
            "preview": "Phillies score",
        })
        recorder.observe(flight, {
            "event": "tool.completed", "run_id": "run_evidence", "tool": "web_search",
            "duration": 1.5, "error": False,
            "result_preview": json.dumps({"success": True, "data": {"web": [
                {"position": 1, "title": "Box score", "url": "https://sports.example/game", "description": "Phillies won 7-1."},
                {"position": 2, "title": "Recap", "url": "https://news.example/recap", "description": "A" * 200},
            ]}}),
        })
        recorder.observe(flight, {
            "event": "tool.completed", "run_id": "run_evidence", "tool": "web_extract",
            "duration": .4, "error": False,
            "result_preview": json.dumps({"results": [
                {"title": "Game recap", "url": "https://sports.example/recap", "content": "Late scoring produced the final margin."},
            ]}),
        })
        await recorder.finish(flight, status="completed", latency_seconds=2, raw_answer="Phillies won.")
        evidence = self.records()[0]["observable_tool_result_evidence"]
        self.assertEqual([item["rank"] for item in evidence[:2]], [1, 2])
        self.assertEqual(evidence[0]["domain"], "sports.example")
        self.assertEqual(evidence[0]["preview"], "Phillies won 7-1.")
        self.assertLessEqual(sum(len(item["preview"]) for item in evidence), 120)
        self.assertTrue(evidence[1]["preview_truncated_by_mgb"])

    async def test_evidence_secrets_are_redacted_and_reasoning_is_ignored(self):
        recorder = self.recorder()
        flight = recorder.start(username="dar", original_request="q", final_prompt="p", lore_records=())
        recorder.observe(flight, {"event": "reasoning.available", "run_id": "run_safe", "text": "hidden chain"})
        recorder.observe(flight, {
            "event": "tool.completed", "run_id": "run_safe", "tool": "web_extract",
            "duration": 1, "error": False,
            "result_preview": json.dumps({"results": [{
                "url": "https://example.test/", "title": "Private",
                "content": "Authorization: Bearer abc.def Cookie: session=secret password=hunter2 exact-secret",
            }]}),
        })
        await recorder.finish(flight, status="completed", latency_seconds=1)
        serialized = self.log_path.read_text(encoding="utf-8")
        for secret in ("abc.def", "session=secret", "hunter2", "exact-secret", "hidden chain"):
            self.assertNotIn(secret, serialized)

    async def test_canonical_and_stale_legacy_discord_secrets_are_redacted_everywhere(self):
        canonical = "canonical-discord-placeholder"
        legacy = "stale-legacy-discord-placeholder"
        delivered = []

        async def capture_discord(messages):
            delivered.extend(messages)

        with patch.dict(os.environ, {
            "DISCORD_TOKEN": canonical,
            "DISCORD_BOT_TOKEN": legacy,
        }, clear=True):
            secrets = defensive_secrets_from_env()
        recorder = HermesFlightRecorder(
            HermesDebugSettings(
                enabled=True,
                log_file=str(self.log_path),
                discord_enabled=True,
            ),
            discord_sender=capture_discord,
            secrets=secrets,
        )
        flight = recorder.start(
            username="dar",
            original_request=f"canonical={canonical} legacy={legacy}",
            final_prompt=f"keep {canonical} and {legacy} private",
            lore_records=(),
        )
        await recorder.finish(
            flight,
            status="completed",
            latency_seconds=1,
            raw_answer=f"answer {canonical} {legacy}",
            twitch_messages=(f"result {canonical} {legacy}",),
        )

        jsonl = self.log_path.read_text(encoding="utf-8")
        discord_output = "\n".join(delivered)
        for secret in (canonical, legacy):
            self.assertNotIn(secret, jsonl)
            self.assertNotIn(secret, discord_output)
        self.assertIn("[REDACTED]", jsonl)
        self.assertIn("[REDACTED]", discord_output)
        self.assertIn("DISCORD_TOKEN", DEFENSIVE_SECRET_ENV_NAMES)
        self.assertIn("DISCORD_BOT_TOKEN", DEFENSIVE_SECRET_ENV_NAMES)

    async def test_discord_chunks_preserve_request_evidence_result_and_status(self):
        recorder = self.recorder()
        record = {
            "twitch_username": "dar", "hermes_run_id": "run_long",
            "original_twitch_request": "Who won?", "observable_events": [
                {"event": "tool.started", "tool": "web_search", "search_query_preview": "game score"},
            ],
            "observable_tool_result_evidence": [
                {"rank": 1, "title": "Source", "preview": "evidence " * 300},
            ],
            "final_twitch_messages": ["@dar They won."], "bridge_error": "",
            "total_latency_seconds": 2.3, "run_status": "completed",
        }
        chunks = recorder._discord_summary(record)
        self.assertTrue(all(len(chunk) <= 1900 for chunk in chunks))
        joined = "\n".join(chunks)
        for expected in ("Who won?", "game score", "1. [Source]", "@dar They won.", "Latency: 2.3s", "Status: completed"):
            self.assertIn(expected, joined)

    async def test_discord_failure_does_not_break_twitch_response(self):
        async def broken_sender(messages):
            raise RuntimeError("Discord unavailable")

        recorder = HermesFlightRecorder(
            HermesDebugSettings(
                enabled=True, log_file=str(self.log_path), discord_enabled=True,
            ),
            discord_sender=broken_sender,
        )
        bridge = HermesChatBridge(bridge_settings(), EventClient(answer="still delivered"), debug_recorder=recorder)
        msg = message()
        self.assertTrue(bridge.submit(msg))
        await asyncio.gather(*bridge._tasks)
        self.assertEqual(msg.channel.sent, ["@iamdar still delivered"])
        self.assertEqual(self.records()[0]["run_status"], "completed")

    async def test_concurrent_run_ids_remain_isolated(self):
        recorder = self.recorder()
        one = recorder.start(username="one", original_request="first", final_prompt="p1", lore_records=())
        two = recorder.start(username="two", original_request="second", final_prompt="p2", lore_records=())
        recorder.observe(one, {"event": "tool.started", "run_id": "run_one", "tool": "web_search", "preview": "alpha"})
        recorder.observe(two, {"event": "tool.started", "run_id": "run_two", "tool": "web_search", "preview": "beta"})
        await asyncio.gather(
            recorder.finish(one, status="completed", latency_seconds=1, raw_answer="A"),
            recorder.finish(two, status="completed", latency_seconds=1, raw_answer="B"),
        )
        by_run = {record["hermes_run_id"]: record for record in self.records()}
        self.assertEqual(by_run["run_one"]["observable_events"][0]["preview"], "alpha")
        self.assertEqual(by_run["run_two"]["observable_events"][0]["preview"], "beta")


if __name__ == "__main__":
    unittest.main()
