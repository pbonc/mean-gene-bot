"""Tunable fishing game data. No renderer-specific values belong here."""

SPECIES = {
    "bluegill": {"name": "Bluegill", "min": .2, "max": 2.1, "tiers": (.75, 1.15, 1.55), "points": 10},
    "crappie": {"name": "Crappie", "min": .4, "max": 3.0, "tiers": (1.0, 1.55, 2.1), "points": 14},
    "trout": {"name": "Rainbow Trout", "min": .5, "max": 8.0, "tiers": (2.0, 3.5, 5.5), "points": 19},
    "bass": {"name": "Largemouth Bass", "min": .7, "max": 10.0, "tiers": (2.5, 4.5, 6.5), "points": 22},
    "catfish": {"name": "Channel Catfish", "min": 1.0, "max": 20.0, "tiers": (4.0, 8.0, 13.0), "points": 28},
    "walleye": {"name": "Walleye", "min": .8, "max": 14.0, "tiers": (3.0, 6.0, 9.0), "points": 30},
    "pike": {"name": "Northern Pike", "min": 1.5, "max": 25.0, "tiers": (5.0, 10.0, 16.0), "points": 38},
    "muskie": {"name": "Muskie", "min": 8.0, "max": 45.0, "tiers": (18.0, 28.0, 36.0), "points": 60},
    "sturgeon": {"name": "Lake Sturgeon", "min": 10.0, "max": 120.0, "tiers": (35.0, 60.0, 90.0), "points": 85},
}

SPECIES_ALIASES = {
    "bluegill": "bluegill", "sunny": "bluegill", "crappie": "crappie",
    "trout": "trout", "rainbow": "trout", "rainbow trout": "trout",
    "bass": "bass", "largemouth": "bass", "largemouth bass": "bass",
    "catfish": "catfish", "cat": "catfish", "channel catfish": "catfish",
    "walleye": "walleye", "eye": "walleye", "pike": "pike",
    "northern": "pike", "northern pike": "pike", "muskie": "muskie", "musky": "muskie",
    "sturgeon": "sturgeon", "lake sturgeon": "sturgeon",
}

BAITS = [
    {"id": "worms", "label": "Worms", "target": "bluegill", "unlock": 0},
    {"id": "minnow", "label": "Minnows", "target": "crappie", "unlock": 3000},
    {"id": "spinner", "label": "Inline Spinner", "target": "trout", "unlock": 7000},
    {"id": "soft_plastic", "label": "Soft Plastic", "target": "bass", "unlock": 15000},
    {"id": "stink_bait", "label": "Stink Bait", "target": "catfish", "unlock": 25000},
    {"id": "jig_minnow", "label": "Jig + Minnow", "target": "walleye", "unlock": 40000},
    {"id": "spoon", "label": "Spoon", "target": "pike", "unlock": 60000},
    {"id": "bucktail", "label": "Bucktail", "target": "muskie", "unlock": 85000},
    {"id": "sturgeon_rig", "label": "Sturgeon Rig", "target": "sturgeon", "unlock": 120000},
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
    bait["id"]: {species: (98 if species == bait["target"] else .05) for species in SPECIES}
    for bait in BAITS
}

TREASURE_CHANCE = 1 / 100
GUN_CACHE_CHANCE = 1 / 300
STEVE_CATCH_CHANCE = 1 / 1500
STEVE_CATCH_POINTS = 1000
STEVE_CATCH_GOLD = 100
STEVE_SAFE_SECONDS = 60 * 60
MK1220_CATCH_CHANCE = 1 / 2000
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
    "sunny": {"bite": .96, "species": {"bluegill": 1.10, "crappie": .88, "trout": 1.18, "bass": 1, "catfish": .78, "walleye": .72, "pike": 1, "muskie": .78, "sturgeon": .82}},
    "cloudy": {"bite": 1.08, "species": {"bluegill": 1.05, "crappie": 1.18, "trout": 1.10, "bass": 1.12, "catfish": 1.15, "walleye": 1.28, "pike": 1.08, "muskie": 1.30, "sturgeon": 1.18}},
    "windy": {"bite": 1.10, "species": {"bluegill": .92, "crappie": 1.02, "trout": 1.16, "bass": 1.12, "catfish": .94, "walleye": 1.25, "pike": 1.18, "muskie": 1.38, "sturgeon": 1.12}},
    "rainy": {"bite": 1.08, "species": {"bluegill": .86, "crappie": 1.12, "trout": 1.24, "bass": 1.10, "catfish": 1.42, "walleye": 1.30, "pike": 1.10, "muskie": 1.42, "sturgeon": 1.30}},
    "night": {"bite": .94, "species": {"bluegill": .22, "crappie": 1.28, "trout": .62, "bass": .88, "catfish": 1.55, "walleye": 1.58, "pike": .92, "muskie": 1.20, "sturgeon": 1.38}},
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
