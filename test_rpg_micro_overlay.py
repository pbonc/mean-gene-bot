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

    def test_demo_includes_initial_classes_enemies_and_phases(self):
        script = (MICRO_DIR / "micro.js").read_text(encoding="utf-8")

        for name in ("warrior", "mage", "healer", "ranger", "slime", "goblin", "ogre"):
            self.assertIn(f'"{name}"', script)
        for phase in ("wander", "arrival", "victory", "loot"):
            self.assertIn(f'"{phase}"', script)


if __name__ == "__main__":
    unittest.main()
