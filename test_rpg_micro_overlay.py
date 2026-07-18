import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MICRO_DIR = ROOT / "bot" / "overlay_static" / "rpg_micro"


class RpgMicroOverlayTests(unittest.TestCase):
    def test_overlay_assets_exist(self):
        self.assertTrue((MICRO_DIR / "index.html").is_file())
        self.assertTrue((MICRO_DIR / "micro.css").is_file())
        self.assertTrue((MICRO_DIR / "micro.js").is_file())

    def test_overlay_uses_transparent_1920_by_96_canvas(self):
        html = (MICRO_DIR / "index.html").read_text(encoding="utf-8")
        css = (MICRO_DIR / "micro.css").read_text(encoding="utf-8")

        self.assertIn('width="1920" height="96"', html)
        self.assertIn("background: transparent", css)
        self.assertIn("aspect-ratio: 20 / 1", css)
        self.assertIn("max-height: 96px", css)
        self.assertIn("bottom: 0", css)

    def test_strip_includes_expedition_classes_and_ambient_states(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        for name in ("adventurer", "warrior", "mage", "healer", "ranger"):
            self.assertIn(f'"{name}"', script)
        for ambient_state in ("journey", "treasure", "camp", "merchant", "encounter_ready"):
            self.assertIn(f'"{ambient_state}"', script)

    def test_strip_exposes_adaptive_roster_and_display_controls(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        self.assertIn("function layoutExpedition()", script)
        self.assertIn("function addMember(kind, name)", script)
        self.assertIn("function removeMember(actorId)", script)
        self.assertIn("function setMode(mode)", script)
        for mode in ("normal", "quiet", "hidden"):
            self.assertIn(f'"{mode}"', script)

    def test_live_strip_requests_and_applies_expedition_snapshots(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        self.assertIn('params.get("demo") === "1"', script)
        self.assertIn("function applyExpeditionSnapshot(payload)", script)
        self.assertIn('type: "request_rpg_v2_expedition"', script)
        self.assertIn('payload.type !== "rpg_v2_expedition"', script)
        self.assertIn("connectExpeditionSocket()", script)

        overlay_server = (ROOT / "bot" / "overlay_server.py").read_text(encoding="utf-8")
        self.assertIn("request_rpg_v2_expedition", overlay_server)
        self.assertIn("latest_rpg_v2_expedition", overlay_server)

    def test_strip_is_ambient_not_a_major_battle_demo(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        self.assertNotIn("SHIELD BASH", script)
        self.assertNotIn("damage(", script)
        self.assertIn("ENCOUNTER READY", script)

    def test_passive_scenery_moves_only_during_journey(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        for scenery in ("tree", "rock", "ruin"):
            self.assertIn(f'backgroundItem("{scenery}"', script)
        self.assertIn('state.ambient !== "journey"', script)
        self.assertIn("TRAVEL_SPEED_PX_PER_SECOND = 26", script)
        self.assertIn("EVENT_APPROACH_SECONDS = EVENT_APPROACH_DISTANCE / TRAVEL_SPEED_PX_PER_SECOND", script)
        self.assertIn("item.x -= TRAVEL_SPEED_PX_PER_SECOND * elapsedSeconds", script)

    def test_game_events_enter_stop_and_fade(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        self.assertIn("function drawEnteringEvent", script)
        self.assertIn("stopX + EVENT_APPROACH_DISTANCE - TRAVEL_SPEED_PX_PER_SECOND * age", script)
        self.assertIn("eventAge < EVENT_APPROACH_SECONDS", script)
        self.assertIn("drawEnteringEvent(age, 940", script)
        self.assertIn("drawEnteringEvent(age, 930", script)
        self.assertIn("Math.max(0, 1 - (age - fadeAt) / 0.6)", script)


if __name__ == "__main__":
    unittest.main()
