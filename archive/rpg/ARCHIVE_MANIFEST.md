# Legacy Stream RPG Archive Manifest

## Status

This directory is a read-only historical reference for Stream RPG v1. It is not an active Python package, runtime data directory, or source of imports for Stream RPG v2.

Do not:

- move `rpg_cog.py` back into `bot/commands/`
- import code or data structures from this directory into `bot/rpg_v2/`
- point active runtime paths at the archived state or log
- edit archived state in place as part of a migration

Any migration must read from a copy or open the archive read-only, write a new v2 record, be safe to run repeatedly, and emit a reviewable report.

## Archived files

| File | Purpose | v2 use |
|---|---|---|
| `rpg_cog.py` | Recovered monolithic v1 implementation | Behavioral and historical reference only |
| `rpg_state.json` | Snapshot of v1 players and session | Possible future identity/recognition migration input |
| `rpg_log.json` | v1 daily and battle history | Possible future legacy-title evidence |

## Concept decisions

| Legacy concept | Decision | v2 interpretation |
|---|---|---|
| Twitch viewer identity | Keep | Map to stable `viewer_id` and current display name |
| Historical participation | Reinterpret | Cosmetic legacy title or mark after explicit review |
| Lifetime wins or boss participation | Reinterpret | May qualify a viewer for a legacy cosmetic; never direct combat power |
| XP and level values | Retire from migration | Begin v2 progression at level 1 unless a later written policy changes this |
| Large class roster | Retire | Adventurer progresses into Warrior, Mage, Healer, or Ranger |
| Active battle/session | Retire | v2 always creates a fresh runtime snapshot |
| Salary and stream claims | Retire | No v2 equivalent |
| Gacha and token balances | Retire | No v2 equivalent |
| Referrals | Retire | No v2 equivalent |
| Revenant ownership/transfers | Retire | Possible future cosmetic reference only |
| Pets, summons, mechs, and transformations | Retire for launch | Reconsider only as cosmetic animation or reserve assist |
| Per-class cooldown fields | Retire | v2 engine state is encounter-scoped and class-agnostic at persistence boundaries |
| Battle report history | Reinterpret | Aggregate recognition only; do not copy raw reports into player records |
| Overlay snapshot/reconnect idea | Keep | Reimplemented through the v2 runtime and event contracts |

## Clean v2 boundaries

- Domain contracts: `bot/rpg_v2/contracts.py`
- Future pure engine: `bot/rpg_v2/engine.py`
- Future Twitch adapter: `bot/rpg_v2/commands.py`
- Future overlay assets: `bot/overlay_static/rpg_micro/`
- Future mutable data: `data/rpg_v2/`
- Product specification: `docs/RPG_V2_PRODUCT_SPEC.md`
- Execution roadmap: `roadmap.md`

The current contract version is `2`. Contract upgrades are explicit; version 1 prototype records and legacy RPG records are rejected rather than silently interpreted as current state.
