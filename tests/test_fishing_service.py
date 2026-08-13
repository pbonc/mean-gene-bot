import asyncio
import json
import tempfile
import unittest
import random
from contextlib import closing
from pathlib import Path

from bot.fishing.service import FishingService


class FishingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.service = FishingService(str(Path(self.temp.name) / "fishing.db"))

    def tearDown(self):
        self.temp.cleanup()

    def run(self, result=None):
        return super().run(result)

    def test_opt_in_and_appearance_persist_in_snapshot(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            await self.service.set_color("42", "Nate", "boat_color", "#112233")
            first = await self.service.snapshot()
            restarted = FishingService(self.service.db_path)
            second = await restarted.snapshot()
            self.assertEqual(first["anglers"][0]["user_id"], "42")
            self.assertEqual(second["anglers"][0]["boat_color"], "#112233")
            self.assertEqual(first["version"], 1)
            self.assertIn("Bluegill", first["weather_boosted_species"])
        asyncio.run(scenario())

    def test_bait_unlock_and_color_validation_are_backend_rules(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with self.assertRaisesRegex(ValueError, "unlocks"):
                await self.service.set_bait("42", "Nate", "muskie")
            with self.assertRaisesRegex(ValueError, "hex"):
                await self.service.set_color("42", "Nate", "shirt_color", "red")
        asyncio.run(scenario())

    def test_bait_can_be_selected_by_stable_tier_number(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            first = await self.service.set_bait("42", "Nate", "1")
            self.assertEqual(first["id"], "worms")
            with self.assertRaisesRegex(ValueError, "unlocks at 3,000"):
                await self.service.set_bait("42", "Nate", "2")
            with self.assertRaisesRegex(ValueError, "Unknown species"):
                await self.service.set_bait("42", "Nate", "7")
        asyncio.run(scenario())

    def test_fish_award_points_not_gold_and_unlock_event_only_on_crossing(self):
        class FishRng:
            def choices(self, population, weights=None, k=1):
                return ["bluegill"]

            def random(self):
                return .5

            def uniform(self, low, high):
                return low

        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET fishing_points=2990,gold=0 WHERE user_id='42'")
                db.commit()
                row = db.execute("SELECT * FROM anglers WHERE user_id='42'").fetchone()
                self.service.rng = FishRng()
                first = self.service._roll_successful_catch(db, row, "sunny")
                db.commit()
                updated = db.execute("SELECT * FROM anglers WHERE user_id='42'").fetchone()
                second = self.service._roll_successful_catch(db, updated, "sunny")
                db.commit()
                final = db.execute("SELECT * FROM anglers WHERE user_id='42'").fetchone()
            self.assertEqual(final["gold"], 0)
            self.assertGreater(final["fishing_points"], 2990)
            self.assertEqual([e["kind"] for e in first].count("bait_unlocked"), 1)
            self.assertEqual([e["kind"] for e in second].count("bait_unlocked"), 0)
        asyncio.run(scenario())

    def test_balancing_tables_match_long_term_thresholds(self):
        from bot.fishing.config import BAITS, BAIT_CATCH_WEIGHTS, BOATS, GUN_CACHE_CHANCE, TREASURE_CHANCE
        self.assertEqual([bait["unlock"] for bait in BAITS], [0, 3000, 10000, 25000, 50000, 100000])
        self.assertEqual([boat["unlock"] for boat in BOATS], [0, 150, 500, 1250])
        for bait in BAITS:
            weights = BAIT_CATCH_WEIGHTS[bait["id"]]
            self.assertEqual(weights[bait["target"]], 98)
            off_target = sum(weight for species, weight in weights.items() if species != bait["target"])
            self.assertAlmostEqual(off_target, .25)
        self.assertAlmostEqual(TREASURE_CHANCE, 1 / 100)
        self.assertAlmostEqual(GUN_CACHE_CHANCE, 1 / 300)

    def test_ticker_returns_one_record_and_one_personal_summary(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET total_catches=7,fishing_points=345,gold=12 WHERE user_id='42'")
                db.execute("INSERT INTO species_stats(user_id,species,catches,gold,diamond,personal_best) VALUES('42','bluegill',7,2,1,1.8)")
                db.execute("INSERT INTO lake_records(species,user_id,display_name,weight,caught_at) VALUES('bluegill','42','Nate',1.8,0)")
                db.commit()
            messages = await self.service.ticker_messages()
            self.assertEqual(len(messages), 2)
            self.assertIn("Fishing Record — Bluegill", messages[0])
            self.assertIn("2 Gold, 1 Diamond", messages[1])
        asyncio.run(scenario())

    def test_events_have_unique_ids(self):
        one = self.service._event("catch")
        two = self.service._event("catch")
        self.assertNotEqual(one["event_id"], two["event_id"])

    def test_off_bait_record_alert_announces_pb_and_lake_record(self):
        from bot.commands.fishing_cog import FishingCog

        event = self.service._event(
            "catch", display_name="Nate", weight=12.3, species_name="Walleye",
            bait_label="Worms", tier="gold", points=200, personal_best=True,
            lake_record=True, accidental_locked=True,
        )
        alert = FishingCog._chat_alert(event)
        self.assertIn("New PB", alert)
        self.assertIn("NEW LAKE RECORD", alert)

    def test_personal_records_lists_each_species_biggest_catch(self):
        from bot.commands.fishing_cog import FishingCog

        target = {
            "display_name": "Nate",
            "species": [
                {"species": "bass", "personal_best": 7.4},
                {"species": "bluegill", "personal_best": 1.8},
            ],
        }
        text = FishingCog._personal_records_text(target)
        self.assertEqual(
            text,
            "🎣 Nate's biggest catches • Bluegill: 1.8 lb | Largemouth Bass: 7.4 lb",
        )
        self.assertIsNone(FishingCog._personal_records_text({"display_name": "Nate", "species": []}))

    def test_diamond_tier_is_very_rare_and_weights_match_tier(self):
        service = FishingService(str(Path(self.temp.name) / "rarity.db"), rng=random.Random(7231))
        from bot.fishing.config import SPECIES
        rolls = [service._roll_tier_and_weight(SPECIES["bluegill"]) for _ in range(50000)]
        diamonds = [weight for tier, weight in rolls if tier == "diamond"]
        self.assertLess(len(diamonds) / len(rolls), 0.004)
        self.assertGreater(len(diamonds), 40)
        self.assertTrue(all(weight >= SPECIES["bluegill"]["tiers"][2] for weight in diamonds))

    def test_global_power_blocks_join_and_hides_saved_anglers(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            await self.service.set_power(False)
            self.assertFalse((await self.service.snapshot())["enabled"])
            self.assertEqual((await self.service.snapshot())["anglers"], [])
            with self.assertRaisesRegex(ValueError, "powered off"):
                await self.service.set_enabled("84", "Fal", True)
            await self.service.set_power(True)
            snapshot = await self.service.snapshot()
            self.assertTrue(snapshot["enabled"])
            self.assertEqual(snapshot["anglers"], [])
            await self.service.set_enabled("42", "Nate", True)
            self.assertEqual([a["display_name"] for a in (await self.service.snapshot())["anglers"]], ["Nate"])
        asyncio.run(scenario())

    def test_silent_lurker_stays_until_twitch_part_and_join_brings_boat_back(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET last_chat_at=0 WHERE user_id='42'")
                db.commit()
            await self.service.tick()
            self.assertEqual([a["display_name"] for a in (await self.service.snapshot())["anglers"]], ["Nate"])
            departed = await self.service.note_viewer_part("NATE")
            self.assertEqual(departed["kind"], "angler_inactive")
            self.assertEqual((await self.service.snapshot())["anglers"], [])
            returned = await self.service.note_viewer_join("nate")
            self.assertEqual(returned["kind"], "angler_returned")
            self.assertEqual([a["display_name"] for a in (await self.service.snapshot())["anglers"]], ["Nate"])
        asyncio.run(scenario())

    def test_gps_targets_only_a_visible_active_boat(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("INSERT INTO species_stats(user_id,species,bronze,silver,gold,diamond) VALUES('42','bass',10,2,3,0)")
                db.commit()
            event = await self.service.gps("42")
            self.assertEqual(event["kind"], "angler_gps")
            self.assertEqual(event["payload"]["medal_tier"], "gold")
            self.assertEqual(event["payload"]["medal_count"], 3)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET away_since=1 WHERE user_id='42'")
                db.commit()
            with self.assertRaisesRegex(ValueError, "not currently on the lake"):
                await self.service.gps("42")
        asyncio.run(scenario())

    def test_new_outing_has_fifteen_minutes_of_steve_immunity(self):
        async def scenario():
            before = __import__("time").time()
            await self.service.set_enabled("42", "Nate", True)
            row = await self.service.angler("42")
            self.assertGreaterEqual(row["steve_immune_until"], before + 15 * 60 - 1)
        asyncio.run(scenario())

    def test_steve_is_configured_as_a_rare_hazard(self):
        from bot.fishing.config import STEVE_ATTACK_CHANCE, STEVE_JOIN_IMMUNITY_SECONDS
        self.assertEqual(STEVE_JOIN_IMMUNITY_SECONDS, 15 * 60)
        self.assertEqual(STEVE_ATTACK_CHANCE, .0005)

    def test_steve_strike_is_counted_and_join_reports_repair(self):
        class SteveRng:
            def choice(self, values):
                return values[0]

            def random(self):
                return 0.0

            def uniform(self, low, high):
                return (low + high) / 2

        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET next_action_at=0,steve_immune_until=0 WHERE user_id='42'")
                db.execute("UPDATE fishing_meta SET value=? WHERE key='weather_changed_at'", (str(__import__("time").time()),))
                db.commit()
            self.service.rng = SteveRng()
            events = await self.service.tick()
            self.assertIn("steve_attack", [event["kind"] for event in events])
            self.assertEqual((await self.service.angler("42"))["steve_strikes"], 1)
            waiting = await self.service.set_enabled("42", "Nate", True)
            self.assertEqual(waiting["kind"], "join_waiting")
            self.assertEqual(waiting["payload"]["cooldown_reason"], "steve")
        asyncio.run(scenario())

    def test_steve_excludes_his_two_most_recent_targets(self):
        class SteveRng:
            def choice(self, values):
                return values[0]

            def random(self):
                return 0.0

            def uniform(self, low, high):
                return low

        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            await self.service.set_enabled("43", "Alex", True)
            await self.service.set_enabled("44", "Sam", True)
            self.service.rng = SteveRng()

            async def force_attempt(user_id):
                with closing(self.service._connect()) as db:
                    db.execute("UPDATE anglers SET cooldown_until=NULL,cooldown_reason=NULL,next_action_at=99999999999")
                    db.execute("UPDATE anglers SET next_action_at=0,steve_immune_until=0 WHERE user_id=?", (user_id,))
                    db.execute("UPDATE fishing_meta SET value=? WHERE key='weather_changed_at'", (str(__import__("time").time()),))
                    db.commit()
                return await self.service.tick()

            first = await force_attempt("42")
            second = await force_attempt("43")
            blocked = await force_attempt("42")
            third = await force_attempt("44")
            eligible_again = await force_attempt("42")

            self.assertIn("steve_attack", [event["kind"] for event in first])
            self.assertIn("steve_attack", [event["kind"] for event in second])
            self.assertNotIn("steve_attack", [event["kind"] for event in blocked])
            self.assertIn("steve_attack", [event["kind"] for event in third])
            self.assertIn("steve_attack", [event["kind"] for event in eligible_again])
            with closing(self.service._connect()) as db:
                history = json.loads(db.execute("SELECT value FROM fishing_meta WHERE key='steve_recent_targets'").fetchone()["value"])
            self.assertEqual(history, ["44", "42"])

        asyncio.run(scenario())

    def test_simulation_starts_and_emits_autonomous_activity(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET next_action_at=0 WHERE user_id='42'")
                db.commit()
            self.service.rng = random.Random(0)
            events = await self.service.tick()
            self.assertIn("angler_activity", [event["kind"] for event in events])
            await self.service.start()
            self.assertTrue((await self.service.status())["task_running"])
            await self.service.stop()
        asyncio.run(scenario())

    def test_manual_move_broadcasts_event_without_reset_snapshot(self):
        async def scenario():
            messages = []

            async def capture(message):
                messages.append(message)

            self.service.set_broadcaster(capture)
            await self.service.set_enabled("42", "Nate", True)
            messages.clear()
            await self.service.move("42")
            self.assertEqual([message["type"] for message in messages], ["fishing_event"])
            self.assertEqual(messages[0]["kind"], "angler_moved")
        asyncio.run(scenario())

    def test_player_sink_uses_two_minute_repair(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            await self.service.set_enabled("84", "Fal", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET sink_tokens=1 WHERE user_id='42'")
                db.commit()
            before = __import__("time").time()
            event = await self.service.sink("42", "Fal")
            self.assertEqual(event["payload"]["repair_seconds"], 120)
            self.assertGreaterEqual(event["payload"]["cooldown_until"], before + 119)
        asyncio.run(scenario())


class FishingRendererContractTests(unittest.TestCase):
    def test_shared_renderer_never_rolls_gameplay(self):
        source = Path("bot/overlay_static/fishing/fishing.js").read_text(encoding="utf-8")
        self.assertNotIn("Math.random", source)
        self.assertIn("request_fishing_state", source)
        self.assertIn('m.type==="fishing_event"', source)
        self.assertIn("angler_inactive", source)
        self.assertIn("angler_returned", source)
        self.assertIn("angler_gps", source)
        self.assertIn("compactWander", source)
        self.assertIn("medal-badge", source)
        self.assertIn("renderPointsLeaderboard", source)

    def test_both_pages_use_shared_renderer(self):
        for name in ("fishing_overlay.html", "fishing_afk_overlay.html"):
            source = Path("bot/overlay_static", name).read_text(encoding="utf-8")
            self.assertIn("/fishing-assets/fishing.js", source)

    def test_afk_renderer_has_weather_driven_ambient_scenery(self):
        page = Path("bot/overlay_static/fishing_afk_overlay.html").read_text(encoding="utf-8")
        css = Path("bot/overlay_static/fishing/fishing.css").read_text(encoding="utf-8")
        renderer = Path("bot/overlay_static/fishing/fishing.js").read_text(encoding="utf-8")
        self.assertIn('id="scenery"', page)
        self.assertIn('id="ambient"', page)
        for token in ("fish-silhouette", "duck-ambient", "weather-cloud", "boathouse", "star"):
            self.assertIn(token, css)
        self.assertIn("clip-path:polygon", css)
        self.assertIn("shore-tree left", renderer)
        self.assertNotIn("shore-trees", renderer)
        self.assertIn("renderAfkWeather", renderer)
        self.assertIn("spawnAfkAmbient", renderer)
        self.assertIn("setSwimDirection", renderer)
        self.assertIn("swimRight", css)
        self.assertIn("swimLeft", css)
        self.assertIn("--swim-y", css)
        self.assertIn("--swim-drift", css)
        self.assertIn("ambientInt(400,950)", renderer)
        self.assertIn("spawnRain", renderer)
        self.assertIn("weather-rainy", css)
        self.assertIn("shore-tree mid-right", renderer)
        self.assertIn('value==="sunny"||value==="night"', renderer)
        self.assertIn("facing-left", renderer)
        self.assertIn("animateFishingLine", renderer)
        self.assertIn("fishing-line", css)
        self.assertIn("pathHitsIsland", renderer)
        self.assertIn("moveBoatTo", renderer)
        self.assertIn("centralIsland", renderer)
        self.assertIn(".island.two { left:720px; top:610px; transform:scale(.7); opacity:1; }", css)
        self.assertIn(".afk #lake.night", css)
        self.assertIn("#2876a8 31% 100%", css)
        self.assertNotIn("filter:brightness", css)
        self.assertIn("Type !fish join to launch your boat.", renderer)
        self.assertIn("Treasure Gold upgrades boats automatically.", renderer)
        self.assertIn("!fish boatcolor #RRGGBB", renderer)
        self.assertIn("Improved catch rates:", renderer)
        self.assertIn('label.style.display=msg.enabled===false?"none":""', renderer)

    def test_compact_canvas_has_only_a_shallow_grounding_ripple(self):
        css = Path("bot/overlay_static/fishing/fishing.css").read_text(encoding="utf-8")
        self.assertIn(".compact #lake { width:1920px; height:1080px; background:transparent; }", css)
        self.assertIn(".compact #water", css)
        self.assertIn("height:14px", css)
        self.assertIn(".compact #lake.night { background:transparent; filter:none; }", css)
        renderer = Path("bot/overlay_static/fishing/fishing.js").read_text(encoding="utf-8")
        self.assertIn('sunny:"☀️"', renderer)


if __name__ == "__main__":
    unittest.main()
