import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "bot" / "overlay_static" / "wotwom_overlay.html"
SERVER = ROOT / "bot" / "overlay_server.py"


class WotWomOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.overlay = OVERLAY.read_text(encoding="utf-8")
        cls.server = SERVER.read_text(encoding="utf-8")

    def test_separate_routes_leave_wom_available(self):
        self.assertIn('app.router.add_get("/wom", wom_overlay)', self.server)
        self.assertIn('app.router.add_get("/wotwom", wotwom_overlay)', self.server)
        self.assertIn('/api/wotwom/inventory', self.server)

    def test_required_modes_and_challenges_exist(self):
        self.assertIn("WORLD WAR II", self.overlay)
        self.assertIn("COLD WAR", self.overlay)
        for challenge in (
            "1 kill",
            "2 kills",
            "3 kills",
            "Win",
            "Win and survive",
            "Ammo rack an enemy",
            "Ram kill",
        ):
            self.assertIn(challenge, self.overlay)

    def test_inventory_loads_when_page_opens(self):
        self.assertIn("loadInventory()", self.overlay)
        self.assertIn("LOADING GARAGE DATA", self.overlay)
        self.assertIn('fetch("/api/wotwom/inventory"', self.overlay)

    def test_loading_terminal_is_inside_the_crt(self):
        crt_start = self.overlay.index('<div class="crt-shell"><div class="crt">')
        loading = self.overlay.index('id="loading"', crt_start)
        screen = self.overlay.index("GARAGE ORDERS RETRIEVAL SYSTEM", loading)
        self.assertLess(crt_start, loading)
        self.assertLess(loading, screen)
        self.assertIn(".loading{position:absolute", self.overlay)

    def test_data_rate_is_replaced_by_live_agent_terminal(self):
        self.assertNotIn("DATA RATE", self.overlay)
        self.assertNotIn('id="dataRateFilters"', self.overlay)
        self.assertIn('id="agentScreen"', self.overlay)
        self.assertIn('id="confirmAgent"', self.overlay)
        self.assertIn("CONFIRM AGENT", self.overlay)
        self.assertIn('payload.type!=="wotwom_chat_user"', self.overlay)
        self.assertIn('type:"request_wotwom_chat_roster"', self.overlay)

    def test_model_name_is_wotwom_iie(self):
        self.assertIn("MODEL WOTWOM IIe", self.overlay)
        self.assertNotIn("MODEL WOTWOM-01", self.overlay)

    def test_tier_era_and_class_filters_configure_download(self):
        self.assertIn('id="tierFilters"', self.overlay)
        self.assertIn('id="eraFilters"', self.overlay)
        self.assertIn('id="affiliationFilters"', self.overlay)
        self.assertIn('id="classFilters"', self.overlay)
        self.assertIn("state.tiers.has(Number(vehicle.tier))", self.overlay)
        self.assertIn("state.eras.has(Number(vehicle.era))", self.overlay)
        self.assertIn(
            'vehicle.mode==="wwii"?vehicle.nation:vehicle.faction',
            self.overlay,
        )
        for tank_class in (
            "Light Tank",
            "Medium Tank",
            "Heavy Tank",
            "Tank Destroyer",
            "Artillery",
        ):
            self.assertIn(f'"{tank_class}"', self.overlay)

    def test_mode_controls_disable_inapplicable_filters(self):
        self.assertIn("button.disabled=!wwii", self.overlay)
        self.assertIn("button.disabled=!coldWar", self.overlay)
        self.assertIn('button.dataset.gameMode==="wwii"?wwii:coldWar', self.overlay)
        self.assertIn('const artillery=button.dataset.class==="Artillery"', self.overlay)

    def test_primary_action_is_download(self):
        self.assertIn('id="download" class="download">DOWNLOAD</button>', self.overlay)
        self.assertNotIn('id="download" class="download">SPIN</button>', self.overlay)

    def test_nameplate_copy_and_centered_terminal_title(self):
        self.assertIn("<span>DARMUNIST M.O.D.</span>", self.overlay)
        self.assertIn("grid-template-columns:1fr auto 1fr", self.overlay)
        self.assertIn("TANK DESTROYER", self.overlay)

    def test_compact_modes_nations_factions_and_box_typography(self):
        self.assertIn('class="mode-grid"', self.overlay)
        self.assertIn("NATION / FACTION", self.overlay)
        self.assertIn('"Mercenary"', self.overlay)
        self.assertIn('"Western Alliance","Eastern Alliance","Independent"', self.overlay)
        self.assertIn("<span>VEHICLE</span>", self.overlay)
        self.assertNotIn("<span>GARAGE VEHICLE</span>", self.overlay)
        self.assertIn("font-size:clamp(19px,2.15vw,39px)", self.overlay)
        self.assertIn("font-size:clamp(10px,.9vw,16px)", self.overlay)

    def test_ticket_rows_align_with_striped_printer_paper(self):
        self.assertIn(".print-line{height:22px", self.overlay)
        self.assertIn("justify-content:center;text-align:center", self.overlay)
        self.assertIn(".ticket.printed{transform:translateY(0)}", self.overlay)
        self.assertIn(
            '<div class="print-line">FROM: DIRECTOR DARMUNIST M.O.D.</div>',
            self.overlay,
        )
        self.assertIn('<div class="print-line">CURRENT ORDERS</div>', self.overlay)
        self.assertIn('<div class="print-line print-rule" aria-hidden="true"></div>', self.overlay)
        self.assertIn("${field.toUpperCase()}: ${state.values[field].toUpperCase()}", self.overlay)

    def test_ticket_supports_agent_outcome_and_signature_submission(self):
        self.assertIn("AGENT: ${state.agent.toUpperCase()}", self.overlay)
        self.assertIn('id="resultPass"', self.overlay)
        self.assertIn('id="resultFail"', self.overlay)
        self.assertIn('id="signature"', self.overlay)
        self.assertIn('class="signature-ink"', self.overlay)
        self.assertIn('fetch("/api/wotwom/results"', self.overlay)
        self.assertIn('textContent="Dar"', self.overlay)

    def test_agent_crt_has_navigation_clear_and_hardware_sounds(self):
        self.assertIn('id="agentUp"', self.overlay)
        self.assertIn('id="agentDown"', self.overlay)
        self.assertIn('id="clearAgent"', self.overlay)
        self.assertIn("CLEAR AGENT", self.overlay)
        self.assertIn("function stepPanel(direction)", self.overlay)
        self.assertIn("scrollIntoView({block:\"nearest\"})", self.overlay)
        self.assertIn("function buttonBeep()", self.overlay)
        self.assertIn("function toggleBeep()", self.overlay)
        self.assertIn("toggleBeep();", self.overlay)
        self.assertIn(".agent-console{flex:1;min-height:0", self.overlay)

    def test_server_replays_recent_chatters_to_new_overlay_clients(self):
        self.assertIn("wotwom_chatters = OrderedDict()", self.server)
        self.assertIn("request_wotwom_chat_roster", self.server)
        self.assertIn('"type": "wotwom_chat_roster"', self.server)

    def test_coms_inventory_toggle_and_sold_status_controls_exist(self):
        self.assertIn('id="panelMode"', self.overlay)
        self.assertIn(">COMS</span>", self.overlay)
        self.assertIn(">INV</span>", self.overlay)
        self.assertIn('id="markSold"', self.overlay)
        self.assertIn("MARK SOLD", self.overlay)
        self.assertIn('fetch("/api/wotwom/sold"', self.overlay)
        self.assertIn("CLEAR STATUS", self.overlay)
        self.assertIn("!state.soldVehicles.has(Number(vehicle.tank_id))", self.overlay)
        self.assertIn('state.panelMode=event.target.checked?"inv":"coms"', self.overlay)

    def test_sold_status_routes_are_registered(self):
        self.assertIn('app.router.add_get("/api/wotwom/sold"', self.server)
        self.assertIn('app.router.add_post("/api/wotwom/sold"', self.server)


if __name__ == "__main__":
    unittest.main()
