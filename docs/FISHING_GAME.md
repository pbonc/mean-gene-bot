# MeanGene Fishing Game

## Architecture

Fishing is one persistent game with two read-only browser presentations. `FishingService` is the sole authority for random rolls, weather, catches, progression, inventory, records, and cooldowns. The Twitch cog translates the `!fish` command tree into service calls. The existing overlay server sends service snapshots and events to every connected OBS browser source.

Opening or closing either page has no gameplay side effect. Both pages may be connected at once. A backend event has a UUID `event_id`; renderers deduplicate it locally and never generate catches.

## Storage

The default database is `data/fishing.db` (SQLite, WAL mode).

- `anglers`: identity, opt-in, Fishing Points, lifetime Gold, boat, colors, bait, rare inventory, aggregate totals, action schedule, and cooldown.
- `species_stats`: per-angler/species catches, medal counts, and personal best.
- `lake_records`: the durable winner and weight for each species.
- `fishing_meta`: global weather and its last-change time.

Transient renderer coordinates are deliberately absent. Each renderer derives stable positions from Twitch user IDs in its own coordinate system.

## WebSocket contract

Clients connect to `/ws` and send:

```json
{"type":"request_fishing_state"}
```

The server replies with `fishing_state` version 1 containing `server_time`, `weather`, active opted-in `anglers`, and `lake_records`. Authoritative changes are broadcast once as:

```json
{
  "type": "fishing_event",
  "version": 1,
  "event_id": "uuid",
  "occurred_at": 0,
  "kind": "catch",
  "payload": {}
}
```

Current event kinds are `angler_joined`, `angler_left`, `angler_moved`, `angler_activity`, `angler_redeployed`, `appearance_changed`, `bait_changed`, `bait_unlocked`, `boat_unlocked`, `weather_changed`, `no_catch`, `catch`, `junk`, `treasure`, `gun_cache`, `boat_sunk`, and `steve_attack`.

## Commands

`!fish` is the only root command. Moderator/broadcaster commands `!fish on` and `!fish off` are the persistent global power switch. Power-off empties the lake and clears all active opt-ins; reopening does not automatically redeploy anyone. `!fish join` is rejected while closed. Each join starts a configured 45–90 minute outing, after which the angler leaves and must join again. Viewer commands are `join`, `stop`, `move`, `bait [species]`, `boat`, `boatcolor`, `shirt`, `sink`, `stats`, `records`, and `record`. Species names accept aliases such as `bass`, `northern`, `eye`, and `sunny`.

Every new outing has 15 minutes of persistent Steve immunity. After immunity, Steve has a configured 0.05% chance per due angler action and causes a configured 2–4 minute repair cooldown. Steve cannot strike either of his two most recent targets. After strikes on A, B, and C, the next target may be A or anybody other than B and C. This rolling target history persists across bot restarts and resets when the lake is powered off.
Using `!fish join` during a Steve or player-sink repair cannot bypass or reset the cooldown; it reports the reason and remaining automatic-redeployment time. Personal overall stats include the persistent number of Steve strikes suffered.
Player-caused `!fish sink` attacks use a separate configured two-minute hull-repair cooldown.
AFK initial placement and both autonomous/manual movement use renderer-side waypoint routing around an expanded collision boundary for the central island. This changes presentation coordinates only; the backend remains authoritative for the movement event.

Routine Bronze catches stay off chat unless they set a PB or record. Higher medals, rare loot, Steve attacks, and sinks are announced. The AFK page also presents these as large banners.

## OBS and local operation

Start MeanGeneBot normally. Its overlay server defaults to port 8080.

- Compact normal-stream source: `http://127.0.0.1:8080/fishing`, browser size 1920 x 1080. The canvas is transparent except for a 14px grounding ripple beneath the hulls. Weather is represented by a small icon rather than text.
- Full-screen AFK source: `http://127.0.0.1:8080/fishing-afk`, browser size 1920 x 1080.

Do not enable OBS's “Shutdown source when not visible” expecting it to control the game; visibility is presentation-only. Scene changes cannot reset or advance the simulation.

Run the focused tests with:

```powershell
python -m unittest tests.test_fishing_service -v
```

The tuning tables for species, bait, boats, and weather live in `bot/fishing/config.py`.

Fishing Points and lifetime Gold are separate. Fish award configured base points multiplied by medal, plus configured PB and lake-record bonuses. Fishing Points permanently unlock bait at 0/3,000/10,000/25,000/50,000/100,000. Treasure awards Gold; lifetime Gold automatically unlocks boats at 0/150/500/1,250. Crossing either threshold emits a one-time backend unlock event. The yacht's second line has a configured 12% chance after a successful bite and cannot recurse.

The AFK renderer adds presentation-only ambient life: ducks, swimming fish silhouettes, shoreline trees, docks, islands, reeds, a boathouse, clouds, wind streaks, rain, sun, moon, and stars. These visuals consume authoritative weather snapshots but never affect game state or catch rolls.
Night changes only the AFK sky palette; the lake, shoreline, boats, structures, and ambient activity retain normal brightness.

Every normal MeanGeneBot ticker pass includes one randomly selected species lake record and one randomly selected angler summary. The AFK renderer also displays the global fishing power state and shows `Type !fish join to launch your boat` while fishing is on.
The AFK weather panel is hidden while fishing is off. While active, it lists every species whose configured catch weight is improved by the current condition.

Medals use a separate data-driven rarity roll rather than uniform weight across a species' full range: Bronze 80%, Silver 17%, Gold 2.8%, and Diamond 0.2% (about 1 in 500 successful fish catches). A species-valid weight is generated inside the selected medal range afterward.
