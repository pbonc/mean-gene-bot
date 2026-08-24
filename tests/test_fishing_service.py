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
                await self.service.set_bait("42", "Nate", "10")
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
        self.assertEqual([bait["unlock"] for bait in BAITS], [0, 3000, 7000, 15000, 25000, 40000, 60000, 85000, 120000])
        self.assertEqual([boat["unlock"] for boat in BOATS], [0, 150, 500, 1250])
        for bait in BAITS:
            weights = BAIT_CATCH_WEIGHTS[bait["id"]]
            self.assertEqual(weights[bait["target"]], 98)
            off_target = sum(weight for species, weight in weights.items() if species != bait["target"])
            self.assertAlmostEqual(off_target, .40)
        self.assertAlmostEqual(TREASURE_CHANCE, 1 / 100)
        self.assertAlmostEqual(GUN_CACHE_CHANCE, 1 / 300)

    def test_new_species_have_lures_aliases_and_weather_tuning(self):
        from bot.fishing.config import BAITS, SPECIES, SPECIES_ALIASES, WEATHER
        for species in ("trout", "catfish", "sturgeon"):
            self.assertIn(species, SPECIES)
            self.assertEqual(SPECIES_ALIASES[species], species)
            self.assertTrue(any(bait["target"] == species for bait in BAITS))
            self.assertTrue(all(species in condition["species"] for condition in WEATHER.values()))

    def test_steve_catch_awards_prizes_and_protects_lake_for_hour(self):
        class SteveCatchRng:
            def choices(self, population, weights=None, k=1):
                return ["__steve__"]

        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            await self.service.set_enabled("84", "Fal", True)
            before = __import__("time").time()
            with closing(self.service._connect()) as db:
                row = db.execute("SELECT * FROM anglers WHERE user_id='42'").fetchone()
                self.service.rng = SteveCatchRng()
                events = self.service._roll_successful_catch(db, row, "sunny")
                db.commit()
                safe_until = float(db.execute("SELECT value FROM fishing_meta WHERE key='steve_safe_until'").fetchone()["value"])
            angler = await self.service.angler("42")
            self.assertEqual([event["kind"] for event in events], ["steve_caught"])
            self.assertEqual(angler["steve_catches"], 1)
            self.assertEqual(angler["fishing_points"], 1000)
            self.assertEqual(angler["gold"], 100)
            self.assertGreaterEqual(safe_until, before + 3599)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET next_action_at=99999999999")
                db.execute("UPDATE anglers SET next_action_at=0,steve_immune_until=0 WHERE user_id='84'")
                db.commit()
            self.service.rng = random.Random(1)
            protected_events = await self.service.tick()
            self.assertNotIn("steve_attack", [event["kind"] for event in protected_events])
        asyncio.run(scenario())

    def test_mk1220_is_consumed_and_awards_exactly_five_fish(self):
        async def scenario():
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET mk1220=1 WHERE user_id='42'")
                db.commit()
            self.service.rng = random.Random(12)
            events = await self.service.launch_mk1220("42")
            self.assertEqual(events[0]["kind"], "mk1220_launched")
            self.assertEqual(len(events[0]["payload"]["catches"]), 5)
            self.assertTrue(all("species" in fish and "weight" in fish for fish in events[0]["payload"]["catches"]))
            self.assertEqual(sum(event["kind"] == "catch" for event in events), 5)
            angler = await self.service.angler("42")
            self.assertEqual(angler["mk1220"], 0)
            self.assertEqual(angler["total_catches"], 5)
        asyncio.run(scenario())

    def test_existing_angler_gold_grant_migration_is_idempotent(self):
        async def scenario():
            await self.service.set_enabled("1", "Viewer", True)
            await self.service.set_enabled("2", "iamdar", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET gold=5,boat_tier=1")
                db.execute("DELETE FROM fishing_meta WHERE key='gold_grant_2026_v1'")
                db.commit()
            restarted = FishingService(self.service.db_path)
            self.assertEqual((await restarted.angler("1"))["gold"], 150)
            self.assertEqual((await restarted.angler("1"))["boat_tier"], 2)
            self.assertEqual((await restarted.angler("2"))["gold"], 1250)
            self.assertEqual((await restarted.angler("2"))["boat_tier"], 4)
            with closing(restarted._connect()) as db:
                db.execute("UPDATE anglers SET gold=2000 WHERE user_id='1'")
                db.commit()
            FishingService(self.service.db_path)
            self.assertEqual((await restarted.angler("1"))["gold"], 2000)
        asyncio.run(scenario())

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

    def test_chat_alerts_only_unlocks_diamonds_personal_bests_and_lake_records(self):
        from bot.commands.fishing_cog import FishingCog

        ordinary = FishingService._event(
            "catch", display_name="Nate", species_name="Bass", weight=7.2,
            bait_label="Minnows", tier="gold", points=500,
            personal_best=False, lake_record=False, accidental_locked=False,
        )
        self.assertIsNone(FishingCog._chat_alert(ordinary))
        for kind, payload in (
            ("treasure", {"display_name": "Nate", "gold": 10}),
            ("steve_caught", {"display_name": "Nate", "points": 1000, "gold": 100}),
            ("angler_returned", {"display_name": "Nate"}),
        ):
            self.assertIsNone(FishingCog._chat_alert(FishingService._event(kind, **payload)))

        diamond = dict(ordinary)
        diamond["payload"] = dict(ordinary["payload"], tier="diamond")
        self.assertIn("Diamond", FishingCog._chat_alert(diamond))

    def test_mk1220_chat_summary_is_compact_unless_catch_is_noteworthy(self):
        from bot.commands.fishing_cog import FishingCog

        plain = FishingService._event("mk1220_launched", display_name="Nate", catches=[
            {"species": "Bass", "weight": 7.2, "tier": "gold", "personal_best": False, "lake_record": False}
        ] * 5)
        self.assertEqual("💥 Nate fired a Mk. 1220 and caught 5 fish.", FishingCog._chat_alert(plain))
        notable = FishingService._event("mk1220_launched", display_name="Nate", catches=[
            {"species": "Walleye", "weight": 12.3, "tier": "diamond", "personal_best": True, "lake_record": True}
        ])
        alert = FishingCog._chat_alert(notable)
        self.assertIn("12.3 lb Walleye", alert); self.assertIn("Diamond", alert)
        self.assertIn("PB", alert); self.assertIn("LR", alert)

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

    def test_diamond_leaderboard_returns_top_three_positive_totals(self):
        async def scenario():
            for user_id, name in (("1", "One"), ("2", "Two"), ("3", "Three"), ("4", "Zero"), ("5", "Five")):
                await self.service.set_enabled(user_id, name, True)
            with closing(self.service._connect()) as db:
                for user_id, species, diamonds in (("1", "bass", 2), ("1", "pike", 3), ("2", "bass", 8), ("3", "bass", 1), ("4", "bass", 0), ("5", "bass", 4)):
                    db.execute("INSERT INTO species_stats(user_id,species,diamond) VALUES(?,?,?)", (user_id, species, diamonds))
                db.commit()
            leaders = await self.service.diamond_leaders()
            self.assertEqual([(row["display_name"], row["diamond_count"]) for row in leaders], [("Two", 8), ("One", 5), ("Five", 4)])
            self.assertEqual((await self.service.snapshot())["diamond_leaderboard"], leaders)
        asyncio.run(scenario())

    def test_big_screen_separates_iamdar_from_competitive_leaderboards(self):
        async def scenario():
            await self.service.set_enabled("dar", "iAmDar", True)
            await self.service.set_enabled("42", "Nate", True)
            with closing(self.service._connect()) as db:
                db.execute("UPDATE anglers SET fishing_points=9999 WHERE user_id='dar'")
                db.execute("UPDATE anglers SET fishing_points=500 WHERE user_id='42'")
                db.execute("INSERT INTO species_stats(user_id,species,diamond) VALUES('dar','bass',12)")
                db.execute("INSERT INTO species_stats(user_id,species,diamond) VALUES('42','bass',2)")
                db.commit()
            snapshot = await self.service.snapshot()
            self.assertEqual("iAmDar", snapshot["iamdar_stats"]["display_name"])
            self.assertEqual(9999, snapshot["iamdar_stats"]["fishing_points"])
            self.assertEqual(12, snapshot["iamdar_stats"]["diamond_count"])
            self.assertNotIn("iamdar", [row["display_name"].casefold() for row in snapshot["points_leaderboard"]])
            self.assertNotIn("iamdar", [row["display_name"].casefold() for row in snapshot["diamond_leaderboard"]])
        asyncio.run(scenario())

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
        self.assertIn("renderDiamondLeaderboard", source)
        self.assertIn("renderDarFishingStats", source)
        self.assertIn("withoutDar", source)
        self.assertIn("mk1220_launched", source)
        self.assertIn("rocket-blast", source)
        self.assertIn("p.catches||[]", source)

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
        self.assertIn('id="darFishingStats"', page)
        self.assertIn(".dar-fishing-stats", css)
        self.assertIn(".afk .power-status { display:flex; position:absolute; right:35px; top:130px; z-index:800; width:310px; min-width:0", css)
        self.assertIn(".afk .dar-fishing-stats { display:block; position:absolute; right:35px; top:255px; z-index:800; width:310px", css)
        self.assertIn(".afk .points-leaderboard { display:block; position:absolute; right:35px; top:345px; z-index:800; width:310px", css)
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
        self.assertIn("boat-details", renderer)
        self.assertIn(".boat.tier-3 .boat-details", css)
        self.assertIn(".boat.tier-4 .boat-details", css)
        self.assertIn(".boat.tier-3 .boat-art { background:var(--boat-color)", css)
        self.assertIn(".boat.tier-4 .boat-art { background:var(--boat-color)", css)
        self.assertNotIn(".boat.tier-4 .boat-art { transform:scale(1.6); background:linear-gradient", css)
        self.assertIn(".boat.tier-3 .boat-art:before", css)
        self.assertIn("border-radius:2px", css)
        self.assertIn(".compact .boat.tier-4 .person { left:14px", css)
        self.assertIn(".boat.tier-4.fishing .rod", css)
        self.assertIn("@keyframes yachtCast", css)
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
