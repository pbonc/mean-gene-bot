"""Typed closed-set evidence for temporal NFL participation questions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class SportsParticipationOutcome(Enum):
    MATCH_FOUND = "MATCH_FOUND"
    COMPLETE_NO_MATCH = "COMPLETE_NO_MATCH"
    INCOMPLETE = "INCOMPLETE"


class ScheduleCompleteness(Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    UNPUBLISHED = "UNPUBLISHED"


ABNORMAL_STATUSES = frozenset({
    "postponed", "rescheduled", "suspended", "canceled", "cancelled",
    "abandoned", "delayed", "moved",
})
NFL_COMPETITION_PHASES = frozenset({"preseason", "regular_season", "postseason"})


@dataclass(frozen=True)
class SportsParticipationScope:
    team: str
    season: str
    competition_phases: tuple[str, ...]
    resolved_date: str

    @property
    def competition_phase(self) -> str:
        """Retain the serialized single-phase spelling for existing consumers."""
        return self.competition_phases[0] if len(self.competition_phases) == 1 else ""


@dataclass(frozen=True)
class SportsScheduleEvent:
    team: str
    season: str
    competition_phase: str
    event_date: str
    status: str = "scheduled"
    conflict_resolved: bool = False


@dataclass(frozen=True)
class NFLPhaseScheduleSection:
    authority: str
    source_url: str
    team: str
    season: str
    competition_phase: str
    completeness: ScheduleCompleteness
    published: bool
    coverage_start: str
    coverage_end: str
    events: tuple[SportsScheduleEvent, ...]


@dataclass(frozen=True)
class NFLClosedSetEvidence:
    team: str
    season: str
    required_phases: tuple[str, ...]
    sections: tuple[NFLPhaseScheduleSection, ...]


@dataclass(frozen=True)
class ClosedSetValidation:
    path: str
    outcome: SportsParticipationOutcome
    scope: SportsParticipationScope

    @property
    def permits_negative_grounding(self) -> bool:
        return (
            self.path == "sports_temporal_participation"
            and self.outcome is SportsParticipationOutcome.COMPLETE_NO_MATCH
        )


def _same(left: str, right: str) -> bool:
    return bool(left.strip()) and left.strip().casefold() == right.strip().casefold()


def _phase(value: str) -> str:
    return value.strip().casefold()


def _iso_date(value: str) -> Optional[date]:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.isoformat() == value else None


def _trusted_section(section: NFLPhaseScheduleSection) -> bool:
    return (
        section.authority.strip().casefold() == "official_nfl"
        and section.source_url.strip().casefold().startswith(
            ("https://nfl.com/", "https://www.nfl.com/")
        )
        and _phase(section.competition_phase) in NFL_COMPETITION_PHASES
    )


def classify_nfl_participation(
    scope: SportsParticipationScope,
    evidence: Optional[NFLClosedSetEvidence],
) -> SportsParticipationOutcome:
    """Apply the approved NFL closed-set rule, failing closed on uncertainty."""
    target = _iso_date(scope.resolved_date)
    required = tuple(_phase(value) for value in scope.competition_phases)
    if (
        evidence is None or target is None
        or not all((scope.team, scope.season, evidence.team, evidence.season))
        or not required or any(value not in NFL_COMPETITION_PHASES for value in required)
        or len(set(required)) != len(required)
        or len({_phase(value) for value in evidence.required_phases}) != len(required)
        or {_phase(value) for value in evidence.required_phases} != set(required)
        or not _same(scope.team, evidence.team)
        or not _same(scope.season, evidence.season)
        or not evidence.sections
    ):
        return SportsParticipationOutcome.INCOMPLETE

    sections_by_phase: dict[str, NFLPhaseScheduleSection] = {}
    for section in evidence.sections:
        phase = _phase(section.competition_phase)
        if (
            not _trusted_section(section)
            or phase not in required
            or phase in sections_by_phase
            or not _same(scope.team, section.team)
            or not _same(scope.season, section.season)
        ):
            return SportsParticipationOutcome.INCOMPLETE
        sections_by_phase[phase] = section
    if set(sections_by_phase) != set(required):
        return SportsParticipationOutcome.INCOMPLETE

    relevant: list[SportsScheduleEvent] = []
    coverage: list[tuple[date, date]] = []
    for phase, section in sections_by_phase.items():
        start, end = _iso_date(section.coverage_start), _iso_date(section.coverage_end)
        if (
            not section.published
            or section.completeness is not ScheduleCompleteness.COMPLETE
            or not section.events
            or start is None or end is None or start > end
        ):
            return SportsParticipationOutcome.INCOMPLETE
        coverage.append((start, end))
        for event in section.events:
            if (
                not _same(scope.team, event.team)
                or not _same(scope.season, event.season)
                or _phase(event.competition_phase) != phase
                or _iso_date(event.event_date) is None
            ):
                return SportsParticipationOutcome.INCOMPLETE
            relevant.append(event)

    if any(
        event.status.strip().casefold() in ABNORMAL_STATUSES and not event.conflict_resolved
        for event in relevant
    ):
        return SportsParticipationOutcome.INCOMPLETE
    if any(event.event_date == scope.resolved_date for event in relevant):
        return SportsParticipationOutcome.MATCH_FOUND

    if any(start <= target <= end for start, end in coverage):
        return SportsParticipationOutcome.COMPLETE_NO_MATCH
    return SportsParticipationOutcome.INCOMPLETE


def closed_set_validation_from_trusted_evidence(
    queried_team: str,
    resolved_date: str,
    evidence: Optional[NFLClosedSetEvidence],
    *,
    path: str,
) -> Optional[ClosedSetValidation]:
    """Cross the internal typed boundary; wire/search dictionaries are never accepted."""
    if (path != "sports_temporal_participation" or evidence is None
            or not queried_team.strip() or not resolved_date.strip()):
        return None
    scope = SportsParticipationScope(
        team=queried_team, season=evidence.season,
        competition_phases=evidence.required_phases, resolved_date=resolved_date,
    )
    return ClosedSetValidation(path, classify_nfl_participation(scope, evidence), scope)
