import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATTLE_DIR = ROOT / "bot" / "overlay_static" / "rpg_battle"


class RpgBattleOverlayTests(unittest.TestCase):
    def test_assets_and_full_screen_canvas_exist(self):
        for name in ("index.html", "battle.css", "battle.js"):
            self.assertTrue((BATTLE_DIR / name).is_file())
        css = (BATTLE_DIR / "battle.css").read_text(encoding="utf-8")
        self.assertIn("width: 100vw", css)
        self.assertIn("height: 100vh", css)

    def test_route_and_reconnect_snapshot_are_registered(self):
        server = (ROOT / "bot" / "overlay_server.py").read_text(encoding="utf-8")
        self.assertIn('app.router.add_get("/rpg-battle", rpg_battle_overlay)', server)
        self.assertIn("request_rpg_v2_battle", server)
        self.assertIn("latest_rpg_v2_battle", server)

    def test_renderer_is_dormant_without_battle_and_has_crowd_fixtures(self):
        html = (BATTLE_DIR / "index.html").read_text(encoding="utf-8")
        script = (BATTLE_DIR / "battle.js").read_text(encoding="utf-8")
        self.assertIn('class="battle dormant"', html)
        for size in ("small", "medium", "crowded"):
            self.assertIn(f'"{size}"', script)
        self.assertIn('type:"request_rpg_v2_battle"', script)
        self.assertIn("function layout(container, count)", script)
        self.assertIn('document.getElementById("friendly-action")', script)
        self.assertIn('document.getElementById("enemy-action")', script)

    def test_prompt_is_mobile_simple_and_renderer_uses_authoritative_hp(self):
        script = (BATTLE_DIR / "battle.js").read_text(encoding="utf-8")
        self.assertIn("TYPE 1, 2, OR 3 IN CHAT", script)
        self.assertIn("data.hp/data.max_hp", script)
        self.assertNotIn("data.hp -=", script)


if __name__ == "__main__":
    unittest.main()
