import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.coup_service import CoupService


class Clock:
    def __init__(self): self.value = datetime(2026, 8, 19, 12, tzinfo=timezone.utc)
    def __call__(self): return self.value


def person(name, user_id=None):
    return {"id": user_id or name.casefold(), "login": name.casefold(), "display": name}


class FixedRng:
    def __init__(self, value): self.value = value
    def random(self): return self.value


class CoupServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.clock = Clock()
        self.service = CoupService(os.path.join(self.temp.name, "coup.json"), self.clock)
        self.service.begin_stream()

    def tearDown(self): self.temp.cleanup()

    def enter_rally(self, name):
        self.assertTrue(self.service.enter(person(name))[0]); self.assertTrue(self.service.rally(name)[0])

    def test_initial_installation_and_persistence(self):
        snap = self.service.snapshot()
        self.assertEqual("Tankahdelphia", snap["currentCommissioner"]["display"])
        self.assertEqual("building", snap["phase"])
        self.enter_rally("BigE")
        self.assertTrue(self.service._rallied(self.service._candidate("BigE")))
        restored = CoupService(self.service.path, self.clock)
        self.assertEqual("BigE", restored.snapshot()["candidates"][0]["display"])
        self.assertFalse(restored.snapshot()["candidates"][0]["rally_active"])
        self.assertIsNone(restored._candidate("BigE")["rally_session_id"])

    def test_rally_is_required_each_stream_without_consuming_failed_vote(self):
        self.enter_rally("BigE"); self.service.begin_stream()
        ok, message = self.service.support(person("Viewer"), "BigE")
        self.assertFalse(ok); self.assertIn("rally this stream", message)
        self.service.rally("BigE")
        self.assertTrue(self.service.support(person("Viewer"), "BigE")[0])

    def test_challenger_may_vote_for_self_but_never_gets_graft(self):
        self.enter_rally("BigE"); self.service.rng = FixedRng(0.0)
        ok, message = self.service.support(person("BigE"), "BigE")
        self.assertTrue(ok); self.assertNotIn("GRAFT", message)
        self.assertEqual(1, self.service.total(self.service._candidate("BigE")))
        self.assertEqual(1, self.service.state["votes"][-1]["points"])

    def test_successful_vote_has_persistent_twelve_hour_cooldown(self):
        self.enter_rally("BigE"); self.enter_rally("Nate")
        self.assertFalse(self.service.support(person("iAmDar"), "BigE")[0])
        self.assertTrue(self.service.support(person("Viewer", "42"), "BigE")[0])
        self.assertFalse(self.service.support(person("Viewer", "42"), "Nate")[0])
        self.service.begin_stream()
        self.service.rally("Nate")
        self.assertFalse(self.service.support(person("Viewer", "42"), "Nate")[0])
        restored = CoupService(self.service.path, self.clock)
        restored.rally("Nate")
        self.assertFalse(restored.support(person("Viewer", "42"), "Nate")[0])
        self.clock.value += timedelta(hours=12)
        restored.rally("Nate")
        self.assertTrue(restored.support(person("Viewer", "42"), "Nate")[0])

    def test_vote_cooldown_expires_during_same_stream(self):
        self.enter_rally("BigE"); self.enter_rally("Nate")
        self.assertTrue(self.service.support(person("Viewer", "42"), "BigE")[0])
        self.clock.value += timedelta(hours=12)
        self.assertTrue(self.service.support(person("Viewer", "42"), "Nate")[0])

    def test_iamdar_can_never_vote_even_if_set_as_commissioner(self):
        self.enter_rally("BigE")
        self.service.state["commissioner"] = person("iAmDar")
        self.service.graft_chance = 1.0
        ok, message = self.service.support(person("iAmDar"), "BigE")
        self.assertFalse(ok); self.assertIn("cannot cast", message)
        self.assertEqual(0, self.service.total(self.service._candidate("BigE")))

    def test_commissioner_vote_sometimes_receives_two_point_graft(self):
        self.enter_rally("BigE")
        self.service.rng = FixedRng(0.0)
        ok, message = self.service.support(person("Tankahdelphia"), "BigE")
        self.assertTrue(ok); self.assertIn("COMMISSIONER GRAFT", message)
        self.assertEqual(2, self.service.total(self.service._candidate("BigE")))
        self.assertEqual(2, self.service.state["votes"][-1]["points"])

    def test_commissioner_vote_is_normally_one_point(self):
        self.enter_rally("BigE")
        self.service.rng = FixedRng(0.99)
        self.assertTrue(self.service.support(person("Tankahdelphia"), "BigE")[0])
        self.assertEqual(1, self.service.total(self.service._candidate("BigE")))

    def test_challenger_at_200_sends_top_two_directly_to_runoff(self):
        self.enter_rally("BigE"); self.enter_rally("Tankahdelphia")
        self.service.adjust("Tankahdelphia", 120); self.service.adjust("BigE", 199)
        self.assertTrue(self.service.support(person("Viewer"), "BigE")[0])
        self.assertEqual("runoff", self.service.state["phase"])
        self.assertFalse(self.service.enter(person("Late"))[0])
        self.assertEqual(["bige", "tankahdelphia"], self.service.state["finalists"])
        self.assertEqual(120, self.service.total(self.service._candidate("tankahdelphia")))

    def test_commissioner_at_200_retains_office_without_runoff(self):
        self.enter_rally("Tankahdelphia"); self.enter_rally("BigE")
        self.service.adjust("Tankahdelphia", 199)
        self.service.rng = FixedRng(0.99)
        self.assertTrue(self.service.support(person("Tankahdelphia"), "Tankahdelphia")[0])
        self.assertEqual("protected", self.service.state["phase"])
        self.assertEqual([], self.service.state["finalists"])
        self.assertEqual("tankahdelphia", self.service.state["history"][-1]["winner"])

    def test_both_runoff_finalists_must_rally_each_stream(self):
        self.enter_rally("BigE"); self.enter_rally("Tankahdelphia")
        self.service.adjust("Tankahdelphia", 120); self.service.adjust("BigE", 199)
        self.service.support(person("Viewer"), "BigE")
        self.service.begin_stream()
        self.assertFalse(self.service.support(person("Other"), "Tankahdelphia")[0])
        self.assertTrue(self.service.rally("Tankahdelphia")[0])
        self.assertTrue(self.service.support(person("Tankahdelphia"), "Tankahdelphia")[0])
        self.assertEqual(121, self.service.total(self.service._candidate("Tankahdelphia")))

    def test_top_two_runoff_eliminates_others_and_throw_rounds_down(self):
        for name, points in (("BigE", 199), ("Nate", 153), ("Karnave", 118)):
            self.enter_rally(name); self.service.adjust(name, points)
        self.service.support(person("Viewer"), "BigE")
        self.assertEqual(["bige", "nate"], self.service.state["finalists"])
        ok, message = self.service.throw("Karnave", "BigE")
        self.assertTrue(ok); self.assertIn("+11", message)
        self.assertEqual(211, self.service.total(self.service._candidate("BigE")))
        self.assertFalse(self.service.throw("Karnave", "Nate")[0])

    def test_resolution_term_starts_next_stream_and_uses_calendar_months(self):
        self.enter_rally("Tankahdelphia"); self.service.adjust("Tankahdelphia", 199)
        self.service.rng = FixedRng(0.99)
        self.service.support(person("Tankahdelphia"), "Tankahdelphia")
        self.assertTrue(self.service.state["term_pending_start"])
        self.clock.value = datetime(2026, 8, 31, 12, tzinfo=timezone.utc); self.service.begin_stream()
        self.assertEqual("2026-11-30", self.service.state["term_expires"][:10])
        self.clock.value = datetime(2026, 11, 30, 12, tzinfo=timezone.utc)
        self.assertEqual("eligible", self.service.snapshot()["phase"])


class CoupOverlayContractTests(unittest.TestCase):
    def test_election_central_and_routes_exist(self):
        root = os.path.dirname(os.path.dirname(__file__))
        html = Path(root, "bot", "overlay_static", "coup_overlay.html").read_text(encoding="utf-8")
        server = Path(root, "bot", "overlay_server.py").read_text(encoding="utf-8")
        self.assertIn("Election Central", html); self.assertIn("request_coup_state", html)
        self.assertIn('runoff?300:200', html)
        self.assertIn('class=runner', html)
        self.assertIn('type==="coup_state"', html)
        self.assertIn('setInterval(refresh,15000)', html)
        self.assertIn('"/election-central"', server); self.assertIn('"/api/coup"', server)


if __name__ == "__main__": unittest.main()
