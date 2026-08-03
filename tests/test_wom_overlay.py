import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "bot" / "overlay_static" / "wom_overlay.html"
SERVER = ROOT / "bot" / "overlay_server.py"
AUDIO = ROOT / "bot" / "overlay_static" / "wom_audio" / "typewriter.wav"


class WomOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = OVERLAY.read_text(encoding="utf-8")

    def test_wom_route_and_audio_static_route_are_registered(self):
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn('app.router.add_get("/wom", wom_overlay)', server)
        self.assertIn("wom_overlay.html", server)
        self.assertIn("app.router.add_static('/wom_audio', wom_audio_dir)", server)

    def test_apple_iie_prototype_is_the_wom_page(self):
        self.assertIn("<title>Wheel of Misfortune IIe</title>", self.overlay)
        self.assertIn("MODEL WOM-1983", self.overlay)
        self.assertIn("REMOTE ORDERS RETRIEVAL SYSTEM", self.overlay)

    def test_four_order_panels_can_be_locked(self):
        self.assertIn("const fields=['mode','nation','br','mission']", self.overlay)
        for field in ("mode", "nation", "br", "mission"):
            self.assertIn(f'id="{field}Lock"', self.overlay)
        self.assertIn("LOCK STATUS: 0 / 4", self.overlay)
        self.assertIn("n!==4||state.busy", self.overlay)

    def test_plane_base_missions_are_available(self):
        self.assertIn("'Destroy an enemy base'", self.overlay)
        self.assertIn("'Damage an enemy base'", self.overlay)

    def test_printer_uses_the_existing_wom_audio_asset(self):
        self.assertIn(
            'id="printerAudio" preload="auto" src="/wom_audio/typewriter.wav"',
            self.overlay,
        )
        self.assertTrue(AUDIO.is_file())
        self.assertGreater(AUDIO.stat().st_size, 1000)

    def test_assign_mission_triggers_recorded_printer_audio_and_animation(self):
        self.assertIn("$('assign').addEventListener('click'", self.overlay)
        self.assertIn("playPrinter();t.classList.add('printing')", self.overlay)
        self.assertIn("function playPrinter()", self.overlay)

    def test_printer_has_no_synthesized_fallback(self):
        self.assertNotIn("fallbackPrinter", self.overlay)
        self.assertNotIn("fallbackPrinterTimer", self.overlay)
        play_printer = self.overlay.split("function playPrinter()", 1)[1].split(
            "function modes()", 1
        )[0]
        self.assertNotIn("beep(", play_printer)

    def test_prototype_uses_valid_em_dashes(self):
        self.assertIn('class="box-value">—</div>', self.overlay)
        self.assertNotIn("â€”", self.overlay)


if __name__ == "__main__":
    unittest.main()
