import unittest
from dataclasses import replace

from bot.research_synthesis import EvidenceItem, normalize_evidence, validate_response
from bot.sports_evidence import (
    ClosedSetValidation, NFLClosedSetEvidence, NFLPhaseScheduleSection,
    ScheduleCompleteness, SportsParticipationOutcome, SportsParticipationScope,
    SportsScheduleEvent, classify_nfl_participation,
    closed_set_validation_from_trusted_evidence,
)


TEAM = "Minnesota Vikings"
DATE = "2026-09-02"
PHASES = ("preseason", "regular_season")
SCOPE = SportsParticipationScope(TEAM, "2026", PHASES, DATE)


def section(phase, dates, start, end, **overrides):
    values = dict(
        authority="official_nfl",
        source_url=f"https://www.nfl.com/teams/vikings/schedule/2026/{phase}/",
        team=TEAM,
        season="2026",
        competition_phase=phase,
        completeness=ScheduleCompleteness.COMPLETE,
        published=True,
        coverage_start=start,
        coverage_end=end,
        events=tuple(SportsScheduleEvent(TEAM, "2026", phase, value) for value in dates),
    )
    values.update(overrides)
    return NFLPhaseScheduleSection(**values)


def fixture(*, sections=None, required=PHASES, team=TEAM, season="2026"):
    if sections is None:
        sections = (
            section("preseason", ("2026-08-15", "2026-08-29"), "2026-08-01", "2026-09-02"),
            section("regular_season", ("2026-09-10", "2026-09-20"), "2026-09-03", "2027-01-31"),
        )
    return NFLClosedSetEvidence(team, season, required, tuple(sections))


class SportsClosedSetEvidenceTests(unittest.TestCase):
    def test_multiphase_interphase_complete_no_match(self):
        self.assertIs(classify_nfl_participation(SCOPE, fixture()),
                      SportsParticipationOutcome.COMPLETE_NO_MATCH)

    def test_missing_required_phase_is_incomplete(self):
        self.assertIs(classify_nfl_participation(SCOPE, fixture(sections=fixture().sections[:1])),
                      SportsParticipationOutcome.INCOMPLETE)

    def test_explicit_coverage_gap_is_incomplete(self):
        preseason, regular = fixture().sections
        evidence = fixture(sections=(replace(preseason, coverage_end="2026-08-31"),
                                     replace(regular, coverage_start="2026-09-04")))
        self.assertIs(classify_nfl_participation(SCOPE, evidence), SportsParticipationOutcome.INCOMPLETE)

    def test_team_or_season_scope_mismatch_is_incomplete(self):
        preseason, regular = fixture().sections
        for changed in (replace(preseason, team="Chicago Bears"),
                        replace(preseason, season="2025")):
            with self.subTest(changed=changed):
                self.assertIs(classify_nfl_participation(
                    SCOPE, fixture(sections=(changed, regular))), SportsParticipationOutcome.INCOMPLETE)

    def test_empty_or_structurally_insufficient_evidence_is_incomplete(self):
        preseason, regular = fixture().sections
        for evidence in (
            fixture(sections=()), fixture(required=()),
            fixture(sections=(replace(preseason, events=()), regular)),
            fixture(sections=(replace(preseason, coverage_start="", coverage_end=""), regular)),
        ):
            with self.subTest(evidence=evidence):
                scope = replace(SCOPE, competition_phases=evidence.required_phases)
                self.assertIs(classify_nfl_participation(scope, evidence),
                              SportsParticipationOutcome.INCOMPLETE)

    def test_unresolved_abnormal_event_conflict_is_incomplete(self):
        preseason, regular = fixture().sections
        abnormal = replace(preseason, events=(SportsScheduleEvent(
            TEAM, "2026", "preseason", "2026-08-29", "rescheduled", False),))
        self.assertIs(classify_nfl_participation(SCOPE, fixture(sections=(abnormal, regular))),
                      SportsParticipationOutcome.INCOMPLETE)

    def test_any_incomplete_or_unpublished_section_is_incomplete(self):
        preseason, regular = fixture().sections
        for changed in (replace(preseason, completeness=ScheduleCompleteness.PARTIAL),
                        replace(preseason, published=False)):
            with self.subTest(changed=changed):
                self.assertIs(classify_nfl_participation(
                    SCOPE, fixture(sections=(changed, regular))), SportsParticipationOutcome.INCOMPLETE)

    def test_matching_structured_event_preserves_match_found(self):
        preseason, regular = fixture().sections
        matching = replace(preseason, events=preseason.events + (
            SportsScheduleEvent(TEAM, "2026", "preseason", DATE),))
        self.assertIs(classify_nfl_participation(SCOPE, fixture(sections=(matching, regular))),
                      SportsParticipationOutcome.MATCH_FOUND)

    def test_event_absence_without_explicit_coverage_is_incomplete(self):
        preseason, regular = fixture().sections
        evidence = fixture(sections=(replace(preseason, coverage_start="", coverage_end=""), regular))
        self.assertIs(classify_nfl_participation(SCOPE, evidence), SportsParticipationOutcome.INCOMPLETE)

    def test_single_phase_complete_no_match_remains_supported(self):
        one = section("preseason", ("2026-08-08", "2026-08-22"),
                      "2026-08-01", "2026-08-31")
        scope = SportsParticipationScope(TEAM, "2026", ("preseason",), "2026-08-15")
        self.assertIs(classify_nfl_participation(
            scope, fixture(sections=(one,), required=("preseason",))),
            SportsParticipationOutcome.COMPLETE_NO_MATCH)

    def test_fabricated_phase_and_untrusted_provider_are_incomplete(self):
        preseason, regular = fixture().sections
        synthetic = replace(preseason, competition_phase="between_phases")
        untrusted = replace(preseason, source_url="https://example.test/schedule")
        for changed in (synthetic, untrusted):
            with self.subTest(changed=changed):
                self.assertIs(classify_nfl_participation(
                    SCOPE, fixture(sections=(changed, regular))), SportsParticipationOutcome.INCOMPLETE)

    def test_negative_grounding_and_typed_stage_b_boundary(self):
        result = closed_set_validation_from_trusted_evidence(
            TEAM, DATE, fixture(), path="sports_temporal_participation")
        self.assertIsNotNone(result)
        self.assertTrue(result.permits_negative_grounding)
        self.assertIsNone(closed_set_validation_from_trusted_evidence(
            TEAM, DATE, fixture(), path="sports_result_or_update"))
        item = EvidenceItem(1, "web_extract", "initial", "r", "NFL schedule",
                            "nfl.com", "https://nfl.com/schedule", "Vikings schedule.", False)
        value = {"supported": True, "answer": "No, the Minnesota Vikings did not play.",
                 "evidence": [{"evidence_id": 1, "quote": "Vikings schedule."}]}
        self.assertEqual(validate_response(value, "did the Minnesota Vikings play yesterday?",
                                           {"resolved_date": DATE}, (item,), 440,
                                           closed_set=result), [])

    def test_generic_negative_validation_remains_rejected(self):
        item = EvidenceItem(1, "web_search", "", "", "Sports", "example.test",
                            "https://example.test", "The Vikings schedule lists August 8.", False)
        value = {"supported": True, "answer": "No, the Vikings did not play.",
                 "evidence": [{"evidence_id": 1, "quote": item.content}]}
        self.assertIn("negative_claim_not_explicitly_supported",
                      validate_response(value, "did they play?", {}, (item,), 440))


if __name__ == "__main__":
    unittest.main()
