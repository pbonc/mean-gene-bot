"""Tunable fishing game data. No renderer-specific values belong here."""

SPECIES = {
    "bluegill": {"name": "Bluegill", "min": .2, "max": 2.1, "tiers": (.75, 1.15, 1.55), "points": 10},
    "crappie": {"name": "Crappie", "min": .4, "max": 3.0, "tiers": (1.0, 1.55, 2.1), "points": 14},
    "bass": {"name": "Largemouth Bass", "min": .7, "max": 10.0, "tiers": (2.5, 4.5, 6.5), "points": 22},
    "walleye": {"name": "Walleye", "min": .8, "max": 14.0, "tiers": (3.0, 6.0, 9.0), "points": 30},
    "pike": {"name": "Northern Pike", "min": 1.5, "max": 25.0, "tiers": (5.0, 10.0, 16.0), "points": 38},
    "muskie": {"name": "Muskie", "min": 8.0, "max": 45.0, "tiers": (18.0, 28.0, 36.0), "points": 60},
}

SPECIES_ALIASES = {
    "bluegill": "bluegill", "sunny": "bluegill", "crappie": "crappie",
    "bass": "bass", "largemouth": "bass", "largemouth bass": "bass",
    "walleye": "walleye", "eye": "walleye", "pike": "pike",
    "northern": "pike", "northern pike": "pike", "muskie": "muskie", "musky": "muskie",
}

BAITS = [
    {"id": "worms", "label": "Worms", "target": "bluegill", "unlock": 0},
    {"id": "minnow", "label": "Minnows", "target": "crappie", "unlock": 3000},
    {"id": "soft_plastic", "label": "Soft Plastic", "target": "bass", "unlock": 10000},
    {"id": "jig_minnow", "label": "Jig + Minnow", "target": "walleye", "unlock": 25000},
    {"id": "spoon", "label": "Spoon", "target": "pike", "unlock": 50000},
    {"id": "bucktail", "label": "Bucktail", "target": "muskie", "unlock": 100000},
]

BOATS = [
    {"tier": 1, "name": "Wooden Raft", "unlock": 0, "catch_bonus": 0.0},
    {"tier": 2, "name": "Skiff", "unlock": 150, "catch_bonus": .03},
    {"tier": 3, "name": "Party Barge Pontoon", "unlock": 500, "catch_bonus": .06},
    {"tier": 4, "name": "Yacht", "unlock": 1250, "catch_bonus": .08, "second_line_chance": .12},
]

MEDAL_MULTIPLIERS = {"bronze": 1.0, "silver": 1.5, "gold": 2.5, "diamond": 5.0}
PERSONAL_BEST_BONUS = 25
LAKE_RECORD_BONUS = 100

BAIT_CATCH_WEIGHTS = {
    "worms": {"bluegill": 98, "crappie": .05, "bass": .05, "walleye": .05, "pike": .05, "muskie": .05},
    "minnow": {"crappie": 98, "bluegill": .05, "bass": .05, "walleye": .05, "pike": .05, "muskie": .05},
    "soft_plastic": {"bass": 98, "bluegill": .05, "crappie": .05, "walleye": .05, "pike": .05, "muskie": .05},
    "jig_minnow": {"walleye": 98, "crappie": .05, "bass": .05, "bluegill": .05, "pike": .05, "muskie": .05},
    "spoon": {"pike": 98, "walleye": .05, "bass": .05, "crappie": .05, "bluegill": .05, "muskie": .05},
    "bucktail": {"muskie": 98, "pike": .05, "walleye": .05, "bass": .05, "crappie": .05, "bluegill": .05},
}

TREASURE_CHANCE = 1 / 100
GUN_CACHE_CHANCE = 1 / 300
CHEST_TIERS = (
    {"id": "common", "chance": .70, "gold_min": 8, "gold_max": 18},
    {"id": "good", "chance": .23, "gold_min": 20, "gold_max": 35},
    {"id": "rare", "chance": .06, "gold_min": 40, "gold_max": 65},
    {"id": "jackpot", "chance": .01, "gold_min": 100, "gold_max": 150},
)
JUNK_CATCHES = ("Old Boot", "Shopping Cart", "1998 Ford Taurus Hubcap")

STEVE_JOIN_IMMUNITY_SECONDS = 15 * 60
STEVE_ATTACK_CHANCE = 0.0005
STEVE_REPAIR_MIN_SECONDS = 2 * 60
STEVE_REPAIR_MAX_SECONDS = 4 * 60
PLAYER_SINK_REPAIR_SECONDS = 2 * 60

WEATHER = {
    "sunny": {"bite": .96, "species": {"bluegill": 1.10, "crappie": .88, "bass": 1, "walleye": .72, "pike": 1, "muskie": .78}},
    "cloudy": {"bite": 1.08, "species": {"bluegill": 1.05, "crappie": 1.18, "bass": 1.12, "walleye": 1.28, "pike": 1.08, "muskie": 1.30}},
    "windy": {"bite": 1.10, "species": {"bluegill": .92, "crappie": 1.02, "bass": 1.12, "walleye": 1.25, "pike": 1.18, "muskie": 1.38}},
    "rainy": {"bite": 1.08, "species": {"bluegill": .86, "crappie": 1.12, "bass": 1.10, "walleye": 1.30, "pike": 1.10, "muskie": 1.42}},
    "night": {"bite": .94, "species": {"bluegill": .22, "crappie": 1.28, "bass": .88, "walleye": 1.58, "pike": .92, "muskie": 1.20}},
}

PALETTE = ("#d46b32", "#3b82f6", "#22c55e", "#a855f7", "#ef4444", "#eab308", "#06b6d4", "#f97316", "#ec4899", "#64748b")

# Medal rarity is rolled independently from species. Weight is then generated
# inside that species' medal range. Diamond is intentionally about 1 in 500
# successful fish catches, before any future special-event modifiers.
TIER_CHANCES = (
    ("diamond", 0.002),
    ("gold", 0.028),
    ("silver", 0.170),
    ("bronze", 0.800),
)
