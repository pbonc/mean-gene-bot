"""Deterministic policy for Twitch requests that require external verification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from importlib import resources
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class TemporalContext:
    matched: bool = False
    phrase: Optional[str] = None
    timezone: Optional[str] = None
    captured_utc: Optional[str] = None
    local_datetime: Optional[str] = None
    local_date: Optional[str] = None
    resolved_date: Optional[str] = None

    def as_dict(self) -> dict:
        if not self.matched:
            return {"matched": False}
        return {
            "matched": True,
            "phrase": self.phrase,
            "timezone": self.timezone,
            "captured_utc": self.captured_utc,
            "local_datetime": self.local_datetime,
            "local_date": self.local_date,
            "resolved_date": self.resolved_date,
        }


@dataclass(frozen=True)
class ResearchDecision:
    research_required: bool
    category: Optional[str] = None
    rule: Optional[str] = None
    temporal_context: TemporalContext = field(default_factory=TemporalContext)
    queried_participant: Optional[str] = None


_EXPLICIT = re.compile(
    r"\b(?:search(?:\s+(?:the\s+)?web)?|look\s+up|check\s+online|verify|find\s+(?:me\s+)?a\s+source)\b",
    re.IGNORECASE,
)
_SPORT_SUBJECT = re.compile(
    r"\b(?:sports?|team|game|match|season|playoffs?|world\s+series|super\s+bowl|"
    r"mlb|nfl|nba|nhl|wnba|ncaa|phillies|twins|yankees|dodgers|mets|eagles|sixers|76ers|flyers)\b",
    re.IGNORECASE,
)
_SPORT_RESULT = re.compile(
    r"\b(?:who\s+won|score|result|standings|win-loss\s+record|schedule|record\s+(?:this|last|current)\s+season)\b",
    re.IGNORECASE,
)
_SPORT_TEMPORAL_PARTICIPATION = re.compile(
    r"^(?:"
    r"did\s+(?!i\b|you\b|we\b)[a-z0-9][a-z0-9 .&'-]{0,60}?\s+play|"
    r"who\s+did\s+[a-z0-9][a-z0-9 .&'-]{0,60}?\s+play|"
    r"are\s+[a-z0-9][a-z0-9 .&'-]{0,60}?\s+playing|"
    r"when\s+did\s+[a-z0-9][a-z0-9 .&'-]{0,60}?\s+play|"
    r"what\s+team\s+did\s+[a-z0-9][a-z0-9 .&'-]{0,60}?\s+play|"
    r"was\s+there\s+an?\s+[a-z0-9][a-z0-9 .&'-]{0,60}?\s+(?:game|matchup)"
    r")\s+(?:today|tonight|yesterday|last\s+night)[?.!]*$",
    re.IGNORECASE,
)

_DID_PLAY_PARTICIPANT = re.compile(
    r"^did\s+(?P<team>[a-z0-9][a-z0-9 .&'-]{0,60}?)\s+play"
    r"(?:\s+(?P<opponent>[a-z0-9][a-z0-9 .&'-]{0,60}?))?\s+"
    r"(?:today|tonight|yesterday|last\s+night)[?.!]*$",
    re.IGNORECASE,
)


def queried_sports_participant(text: str) -> Optional[str]:
    """Extract one unambiguous grammatical subject from a participation query."""
    match = _DID_PLAY_PARTICIPANT.match(" ".join(str(text or "").split()))
    if match is None:
        return None
    team = match.group("team").strip()
    # A dual subject is intentionally not reducible to either mentioned team.
    if re.search(r"\b(?:and|or|vs\.?|versus)\b|[/,]", team, re.IGNORECASE):
        return None
    return re.sub(r"^the\s+", "", team, flags=re.IGNORECASE).strip() or None
_RELATIVE_TIME = re.compile(
    r"\b(?:today|tonight|yesterday|last\s+night|right\s+now|currently|latest|recent(?:ly)?)\b",
    re.IGNORECASE,
)
_MARKET = re.compile(
    r"\b(?:stock|share|crypto|bitcoin|ethereum|market|exchange\s+rate|ticker|nasdaq|dow|s&p)\b",
    re.IGNORECASE,
)
_PRICE = re.compile(r"\b(?:price|quote|trading|worth|up|down)\b", re.IGNORECASE)
_CURRENT_EVENT = re.compile(
    r"\b(?:latest|current|today(?:'s)?|breaking|recent)\s+(?:news|headlines?|election\s+results?|events?)\b",
    re.IGNORECASE,
)
_EXCLUDED_CONTEXT = re.compile(
    r"\b(?:joke|movie|film|fiction|fictional|roleplay|role-play|pretend|imagine|story|poem|lyrics?)\b",
    re.IGNORECASE,
)
_PERSONAL_LAST_NIGHT = re.compile(r"\bwhat\s+did\s+(?:you|i|we)\s+do\s+last\s+night\b", re.IGNORECASE)
_SUPPORTED_TEMPORAL = re.compile(
    r"\b(?:last\s+night|yesterday|tonight|today)\b",
    re.IGNORECASE,
)


def _zone_info(timezone_name: str) -> ZoneInfo:
    """Load IANA data, using the already-required pytz database on Windows."""
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as original_error:
        parts = timezone_name.split("/")
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise original_error
        try:
            resource = resources.files("pytz").joinpath("zoneinfo", *parts)
            with resource.open("rb") as handle:
                return ZoneInfo.from_file(handle, key=timezone_name)
        except (FileNotFoundError, ModuleNotFoundError):
            raise original_error


def resolve_temporal_context(
    text: str,
    *,
    captured_utc: datetime,
    timezone_name: str,
) -> TemporalContext:
    """Resolve only the explicitly supported relative expressions."""
    match = _SUPPORTED_TEMPORAL.search(str(text or ""))
    if match is None:
        return TemporalContext()
    if captured_utc.tzinfo is None:
        raise ValueError("captured_utc must be timezone-aware")

    utc_instant = captured_utc.astimezone(timezone.utc)
    local_now = utc_instant.astimezone(_zone_info(timezone_name))
    phrase = " ".join(match.group(0).lower().split())
    day_offset = -1 if phrase in {"yesterday", "last night"} else 0
    resolved = local_now.date() + timedelta(days=day_offset)
    return TemporalContext(
        matched=True,
        phrase=phrase,
        timezone=timezone_name,
        captured_utc=utc_instant.isoformat(timespec="seconds").replace("+00:00", "Z"),
        local_datetime=local_now.isoformat(timespec="seconds"),
        local_date=local_now.date().isoformat(),
        resolved_date=resolved.isoformat(),
    )


def classify_research_request(
    text: str,
    *,
    temporal_context: Optional[TemporalContext] = None,
) -> ResearchDecision:
    """Return a deliberately narrow, auditable verification decision."""
    context = temporal_context or TemporalContext()
    value = " ".join(str(text or "").split())
    if not value:
        return ResearchDecision(False, temporal_context=context)

    if _EXPLICIT.search(value):
        return ResearchDecision(True, "explicit_research", "explicit_research_request", context)

    excluded = bool(_EXCLUDED_CONTEXT.search(value) or _PERSONAL_LAST_NIGHT.search(value))
    if not excluded and (_SPORT_TEMPORAL_PARTICIPATION.match(value)
                         or _DID_PLAY_PARTICIPANT.match(value)):
        return ResearchDecision(
            True, "current_sports_result", "sports_temporal_participation", context,
            queried_sports_participant(value),
        )

    if not excluded and _SPORT_SUBJECT.search(value) and _SPORT_RESULT.search(value):
        rule = "sports_result_plus_relative_date" if _RELATIVE_TIME.search(value) else "sports_result_or_update"
        return ResearchDecision(True, "current_sports_result", rule, context)

    if not excluded and _MARKET.search(value) and _PRICE.search(value) and _RELATIVE_TIME.search(value):
        return ResearchDecision(True, "current_market_price", "market_price_plus_current_time", context)

    if not excluded and _CURRENT_EVENT.search(value):
        return ResearchDecision(True, "current_events", "narrow_current_event_query", context)

    return ResearchDecision(False, temporal_context=context)
