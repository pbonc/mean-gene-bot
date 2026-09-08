"""Sanitized, observable-only flight recorder for Twitch-origin Hermes runs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

import aiohttp

from bot.lore_store import LoreRecord


DiscordSender = Callable[[list[str]], Awaitable[None]]

# Include stale legacy credentials defensively even though Discord runtime and
# configuration consume only DISCORD_TOKEN.
DEFENSIVE_SECRET_ENV_NAMES = (
    "HERMES_API_KEY",
    "HERMES_DEBUG_DISCORD_WEBHOOK_URL",
    "TWITCH_OAUTH_TOKEN",
    "TWITCH_CLIENT_SECRET",
    "DISCORD_TOKEN",
    "DISCORD_BOT_TOKEN",
)


def defensive_secrets_from_env() -> tuple[str, ...]:
    return tuple(os.getenv(name, "") for name in DEFENSIVE_SECRET_ENV_NAMES)


@dataclass(frozen=True)
class HermesDebugSettings:
    enabled: bool = False
    log_file: str = "logs/hermes_debug.jsonl"
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    max_evidence_chars: int = 1200

    @classmethod
    def from_env(cls) -> "HermesDebugSettings":
        def truthy(name: str) -> bool:
            return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            enabled=truthy("HERMES_DEBUG_ENABLED"),
            log_file=os.getenv("HERMES_DEBUG_LOG_FILE", cls.log_file).strip() or cls.log_file,
            discord_enabled=truthy("HERMES_DEBUG_DISCORD_ENABLED"),
            discord_webhook_url=os.getenv("HERMES_DEBUG_DISCORD_WEBHOOK_URL", "").strip(),
            max_evidence_chars=max(
                100,
                min(10000, int(os.getenv("HERMES_DEBUG_MAX_EVIDENCE_CHARS", "1200"))),
            ),
        )


@dataclass
class HermesFlight:
    timestamp: str
    twitch_username: str
    original_request: str
    final_prompt: str
    lore_records: list[dict]
    request_started_at: str
    run_id: str = ""
    events: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    research_required: bool = False
    research_category: Optional[str] = None
    research_rule: Optional[str] = None
    temporal_context: dict = field(default_factory=lambda: {"matched": False})
    current_attempt: str = "initial"
    attempts: dict[str, dict] = field(default_factory=dict)
    recovery_attempted: bool = False
    search_requirement_satisfied: bool = False
    delivered_attempt: str = ""
    recovery_result: str = "not_attempted"
    stage_b: dict = field(default_factory=lambda: {"enabled": False})
    evidence_sufficiency: dict = field(default_factory=dict)


class HermesFlightRecorder:
    """Write one isolated JSONL record per Hermes run and optionally notify Discord."""

    _ASSIGNMENT_SECRET_RE = re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization)"
        r"(\s*[=:]\s*)([^\s,;]+)"
    )
    _BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
    _OAUTH_RE = re.compile(r"(?i)\boauth:[A-Za-z0-9._~+/=-]+")
    _COOKIE_RE = re.compile(r"(?i)\b(cookie|set-cookie)(\s*[:=]\s*)([^\r\n]+)")
    _WEBHOOK_RE = re.compile(r"https://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/[^\s\"']+", re.I)

    def __init__(
        self,
        settings: Optional[HermesDebugSettings] = None,
        discord_sender: Optional[DiscordSender] = None,
        secrets: tuple[str, ...] = (),
    ):
        self.settings = settings or HermesDebugSettings.from_env()
        self._discord_sender = discord_sender
        self._secrets = tuple(secret for secret in secrets if secret)
        self._write_lock = asyncio.Lock()

    def set_discord_sender(self, sender: Optional[DiscordSender]) -> None:
        self._discord_sender = sender

    def start(
        self,
        *,
        username: str,
        original_request: str,
        final_prompt: str,
        lore_records: tuple[LoreRecord, ...],
    ) -> Optional[HermesFlight]:
        if not self.settings.enabled:
            return None
        now = self._iso_now()
        return HermesFlight(
            timestamp=now,
            twitch_username=self.redact(username),
            original_request=self.redact(original_request),
            final_prompt=self.redact(final_prompt),
            lore_records=[
                {
                    "id": record.id,
                    "subject": self.redact(record.subject),
                    "category": record.category,
                    "key": record.key,
                    "value": self.redact(record.value),
                }
                for record in lore_records
            ],
            request_started_at=now,
        )

    def observe(self, flight: Optional[HermesFlight], event: dict) -> None:
        if flight is None or not isinstance(event, dict):
            return
        event_type = str(event.get("event") or "")
        if event_type not in {"tool.started", "tool.completed"}:
            return
        run_id = str(event.get("run_id") or "")
        if flight.run_id and run_id and run_id != flight.run_id:
            return
        if run_id:
            flight.run_id = run_id
        observable = {
            "attempt": flight.current_attempt,
            "event": event_type,
            "run_id": run_id,
            "timestamp": event.get("timestamp"),
            "tool": self.redact(str(event.get("tool") or "")),
        }
        if event_type == "tool.started":
            preview = self.redact(str(event.get("preview") or ""))
            observable["preview"] = preview[: self.settings.max_evidence_chars]
            observable["preview_truncated_by_mgb"] = len(preview) > self.settings.max_evidence_chars
            if observable["tool"] == "web_search":
                observable["search_query_preview"] = observable["preview"]
            elif observable["tool"] == "web_extract":
                observable["extract_target_preview"] = observable["preview"]
        else:
            observable["duration_seconds"] = event.get("duration")
            observable["error"] = bool(event.get("error", False))
            if observable["tool"] in {"web_search", "web_extract"}:
                self._capture_evidence(flight, observable["tool"], event, observable)
        flight.events.append(observable)

    def set_research_policy(self, flight: Optional[HermesFlight], decision) -> None:
        if flight is None:
            return
        flight.research_required = bool(decision.research_required)
        flight.research_category = decision.category
        flight.research_rule = decision.rule
        flight.temporal_context = decision.temporal_context.as_dict()

    def start_attempt(self, flight: Optional[HermesFlight], name: str) -> None:
        if flight is None:
            return
        flight.current_attempt = name
        flight.run_id = ""
        flight.attempts.setdefault(name, {})
        if name == "recovery":
            flight.recovery_attempted = True

    def finish_attempt(self, flight: Optional[HermesFlight], name: str, observation) -> None:
        if flight is None:
            return
        flight.attempts[name] = {
            "run_id": observation.run_id or None,
            "terminal_status": observation.terminal_status or None,
            "event_stream_connected": observation.event_stream_connected,
            "event_stream_drained": observation.event_stream_drained,
            "successful_web_searches": observation.successful_web_searches,
            "successful_web_extracts": observation.successful_web_extracts,
            "successful_web_retrievals": observation.successful_web_retrievals,
            "failed_tool_completions": observation.failed_tool_completions,
        }

    def set_stage_b(self, flight: Optional[HermesFlight], *, enabled: bool,
                    stage_a_prose: str = "", collection=None, result=None) -> None:
        if flight is None:
            return
        data = {"enabled": enabled}
        if enabled:
            items = tuple(getattr(collection, "items", ()))
            data.update({
                "stage_a_prose": self.redact(stage_a_prose),
                "stage_a_prose_delivered": False,
                "evidence_ids_selected": [item.evidence_id for item in items],
                "evidence_provenance": [{
                    "evidence_id": item.evidence_id, "tool": item.tool,
                    "attempt": item.attempt, "run_id": item.run_id,
                    "title": self.redact(item.source_title), "domain": item.domain,
                    "url": self.redact(item.url), "truncated": item.truncated,
                } for item in items],
                "evidence_truncated": bool(getattr(collection, "any_truncated", False)),
                "normalization_failures": list(getattr(collection, "failures", ())),
            })
            if result is not None:
                data.update({
                    "retry_performed": len(result.attempts) > 1,
                    "failure_reasons": result.failure_reasons,
                    "final_delivery_source": "stage_b" if result.delivered else "deterministic_fallback",
                    "attempts": [{
                        "attempt": attempt.number,
                        "latency_seconds": round(attempt.latency_seconds, 3),
                        "raw_structured_result": self.redact(attempt.raw_result),
                        "parsed_supported": attempt.supported,
                        "parsed_answer": self.redact(attempt.answer),
                        "claimed_evidence": self._redact_value(attempt.claimed_evidence),
                        "validator_passed": attempt.validator_passed,
                        "validator_failures": attempt.failures,
                    } for attempt in result.attempts],
                })
            else:
                data.update({"final_delivery_source": "deterministic_fallback",
                             "failure_reasons": ["stage_b_exception"]})
        flight.stage_b = data

    def set_evidence_sufficiency(
        self, flight: Optional[HermesFlight], *, initial_date_sufficient,
        recovery_required: bool, recovery_reason: str,
        recovery_instruction: str = "",
    ) -> None:
        if flight is None:
            return
        flight.evidence_sufficiency = {
            "initial_evidence_addresses_resolved_date": initial_date_sufficient,
            "recovery_required": recovery_required,
            "recovery_reason": recovery_reason or None,
            "recovery_instruction": self.redact(recovery_instruction) if recovery_instruction else None,
        }

    def _capture_evidence(self, flight: HermesFlight, tool: str, event: dict, observable: dict) -> None:
        raw = event.get("result_preview", event.get("result", ""))
        if not isinstance(raw, str) or not raw.strip():
            return
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            return
        duration = observable.get("duration_seconds")
        if tool == "web_search":
            rows = payload.get("data", {}).get("web", []) if isinstance(payload, dict) else []
        else:
            rows = payload.get("results", []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            return
        used = sum(len(str(item.get("preview", ""))) for item in flight.evidence)
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or used >= self.settings.max_evidence_chars:
                break
            url = self.redact(str(row.get("url") or ""))[:300]
            text = row.get("description") if tool == "web_search" else row.get("content")
            clean = self.redact(" ".join(str(text or "").split()))
            remaining = self.settings.max_evidence_chars - used
            preview = clean[:remaining]
            used += len(preview)
            flight.evidence.append({
                "attempt": flight.current_attempt,
                "tool": tool,
                "rank": row.get("position", index + 1),
                "title": self.redact(str(row.get("title") or ""))[:160],
                "url": url,
                "domain": self._domain(url),
                "preview": preview,
                "preview_truncated_by_mgb": len(clean) > len(preview),
                "duration_seconds": duration,
                "error": self.redact(str(row.get("error") or ""))[:300],
            })

    async def finish(
        self,
        flight: Optional[HermesFlight],
        *,
        status: str,
        latency_seconds: float,
        raw_answer: str = "",
        twitch_messages: tuple[str, ...] = (),
        error: str = "",
        search_requirement_satisfied: Optional[bool] = None,
        delivered_attempt: str = "",
        recovery_result: str = "",
    ) -> None:
        if flight is None:
            return
        if search_requirement_satisfied is not None:
            flight.search_requirement_satisfied = search_requirement_satisfied
        if delivered_attempt:
            flight.delivered_attempt = delivered_attempt
        if recovery_result:
            flight.recovery_result = recovery_result
        initial = flight.attempts.get("initial", {})
        recovery = flight.attempts.get("recovery", {})
        record = {
            "timestamp": flight.timestamp,
            "hermes_run_id": flight.run_id or None,
            "twitch_username": flight.twitch_username,
            "original_twitch_request": flight.original_request,
            "final_prompt_sent_to_hermes": flight.final_prompt,
            "injected_lore_records": flight.lore_records,
            "request_started_at": flight.request_started_at,
            "request_finished_at": self._iso_now(),
            "total_latency_seconds": round(float(latency_seconds), 3),
            "observable_events": flight.events,
            "observable_tool_result_evidence": flight.evidence,
            "research_required": flight.research_required,
            "research_category": flight.research_category,
            "research_rule": flight.research_rule,
            "temporal_context": flight.temporal_context,
            "attempts": flight.attempts,
            "initial_run_id": initial.get("run_id"),
            "initial_successful_web_retrievals": initial.get("successful_web_retrievals", 0),
            "initial_answer_withheld": bool(flight.research_required and flight.recovery_attempted),
            "recovery_attempted": flight.recovery_attempted,
            "recovery_run_id": recovery.get("run_id"),
            "recovery_successful_web_retrievals": recovery.get("successful_web_retrievals", 0),
            "search_requirement_satisfied": flight.search_requirement_satisfied,
            "delivered_attempt": flight.delivered_attempt or None,
            "recovery_result": flight.recovery_result,
            "stage_b": flight.stage_b,
            "evidence_sufficiency": flight.evidence_sufficiency,
            "tool_result_evidence_note": (
                "Bounded, redacted web evidence captured from Hermes SSE."
                if flight.evidence else
                "Evidence payloads unavailable for this run."
            ),
            "run_status": status,
            "raw_final_hermes_answer": self.redact(raw_answer),
            "final_twitch_messages": [self.redact(message) for message in twitch_messages],
            "bridge_error": self.redact(error),
        }
        record = self._redact_value(record)
        async with self._write_lock:
            try:
                await asyncio.to_thread(self._append_jsonl, record)
            except Exception:
                logging.exception("[HERMES DEBUG] Failed to write flight record")
            if self.settings.discord_enabled:
                try:
                    await self._send_discord(self._discord_summary(record))
                except Exception as error:
                    logging.exception("[HERMES DEBUG] Discord telemetry delivery failed")
                    print(
                        "[HERMES DEBUG] Discord telemetry delivery failed: "
                        f"{self.redact(str(error))}"
                    )

    def redact(self, text: str) -> str:
        value = str(text or "")
        value = self._WEBHOOK_RE.sub("[REDACTED_DISCORD_WEBHOOK]", value)
        value = self._BEARER_RE.sub("Bearer [REDACTED]", value)
        value = self._OAUTH_RE.sub("oauth:[REDACTED]", value)
        value = self._COOKIE_RE.sub(r"\1\2[REDACTED]", value)
        value = self._ASSIGNMENT_SECRET_RE.sub(r"\1\2[REDACTED]", value)
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        return value

    def _redact_value(self, value):
        if isinstance(value, dict):
            return {key: self._redact_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        return self.redact(value) if isinstance(value, str) else value

    def _append_jsonl(self, record: dict) -> None:
        path = Path(self.settings.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    async def _send_discord(self, messages: list[str]) -> None:
        if self._discord_sender is not None:
            await self._discord_sender(messages)
            return
        webhook = self.settings.discord_webhook_url
        if not webhook:
            return
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for message in messages:
                async with session.post(webhook, json={"content": message}) as response:
                    if response.status not in {200, 204}:
                        raise RuntimeError(f"Discord webhook returned HTTP {response.status}")

    def _discord_summary(self, record: dict) -> list[str]:
        events = record["observable_events"]
        searches = [event for event in events if event.get("event") == "tool.started" and event.get("tool") == "web_search"]
        extracts = [event for event in events if event.get("event") == "tool.started" and event.get("tool") == "web_extract"]
        completions = [event for event in events if event.get("event") == "tool.completed"]
        lines = [
            "🧠 GENE FLIGHT RECORDER",
            f"User: @{record['twitch_username']}",
            f"Run: {record['hermes_run_id'] or 'unassigned'}",
            f"Request: {self._clip(record['original_twitch_request'], 500)}",
        ]
        temporal = record.get("temporal_context") or {}
        if temporal.get("matched"):
            lines.extend([
                f"Temporal expression: {temporal.get('phrase')}",
                f"Timezone: {temporal.get('timezone')}",
                f"Local request time: {temporal.get('local_datetime')}",
                f"Resolved requested date: {temporal.get('resolved_date')}",
            ])
        lines.append(f"Searched: {'yes' if searches else 'no'}")
        for event in searches:
            lines.append(f"🔍 web_search: {self._clip(event.get('search_query_preview', ''), 500)}")
        for event in extracts:
            lines.append(f"📄 web_extract: {self._clip(event.get('extract_target_preview', ''), 500)}")
        for event in completions:
            state = "ERROR" if event.get("error") else "OK"
            lines.append(f"{event.get('tool')}: {state} ({event.get('duration_seconds', 0)}s)")
        evidence = record.get("observable_tool_result_evidence") or []
        for item in evidence:
            source = item.get("title") or item.get("domain") or item.get("url") or "source"
            preview = self._clip(item.get("preview", ""), 350)
            lines.append(f"{item.get('rank', '?')}. [{self._clip(source, 100)}] — {preview}")
        if (searches or extracts) and not evidence:
            lines.append("Evidence payloads: unavailable from installed Hermes SSE API")
        result = " | ".join(record.get("final_twitch_messages") or [])
        if not result:
            result = record.get("bridge_error") or "(no Twitch answer)"
        lines.extend([
            f"Result: {self._clip(result, 900)}",
            f"Latency: {record['total_latency_seconds']:.1f}s",
            f"Status: {record['run_status']}",
        ])
        return self._split_discord("\n".join(lines))

    @staticmethod
    def _clip(value: str, limit: int) -> str:
        clean = " ".join(str(value or "").split())
        return clean if len(clean) <= limit else clean[: limit - 3] + "..."

    @staticmethod
    def _split_discord(text: str, limit: int = 1900) -> list[str]:
        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, limit + 1)
            if split_at <= 0:
                split_at = limit
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")
        return chunks

    @staticmethod
    def _domain(url: str) -> str:
        try:
            return urlsplit(url).hostname or ""
        except ValueError:
            return ""

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
