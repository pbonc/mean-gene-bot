# Audit Board - 2026-05-27

## Checkpoint Status

- Branch: `feature/factions-v1`
- Safety commit: `b11e270`
- Safety commit message: `WIP checkpoint before audit (49 changes)`
- Pushed to origin: Yes

This checkpoint is the rollback anchor for all follow-up cleanup and split commits.

## Bucket Triage (Current HEAD)

### A) Ship-ready feature code (coherent chunks)

- `bot/commands/faction_cog.py`
- `bot/faction_service.py`
- `bot/twitch_eligibility.py`
- `bot/commands/raffle_cog.py`
- `bot/commands/grid_cog.py`
- `bot/grid_state.py`
- `bot/commands/tts_cog.py`
- `bot/overlay_static/grid_overlay.html`
- `bot/overlay_static/nba_break_overlay.html`
- `tools/grid_inventory_from_csv.py`

### B) Needs verification before merge-to-main

- `bot/main.py`
- `bot/overlay_server.py`
- `bot/commands/song_cog.py`
- `bot/commands/song_request_simple.py`
- `bot/music_sheets_sync.py`
- `bot/playlist_sheets_sync.py`
- `bot/oauth_refresh.py`
- `bot/weather_utils.py`
- `bot/commands/wotd_cog.py`
- `bot/commands/media_overlay.py`

### C) Runtime/state/cache artifacts (track only if intentionally canonical)

- `data/factions.db`
- `data/grid_state.json`
- `data/grid_inventory.json`
- `data/autoplay_state.json`
- `data/playlist_cache.json`
- `data/user_quarters.json`
- `data/wheel_state.json`
- `data/wotd_state.json`

Notes:

- `data/grid_import_starter.csv` appears to be canonical seed input and is likely worth tracking.
- DB and state snapshots should generally be ignored or moved to seed fixtures.

### D) Temporary/debug/archive payload

- `tmp_find_lines.py`
- `tmp_grid_lines.py`
- `tmp_line_info.py`
- `tmp_line_numbers_script.py`
- `archive/rpg/rpg_cog.py`
- `archive/rpg/rpg_log.json`
- `archive/rpg/rpg_state.json`

Notes:

- Archive content may be intentionally retained, but should be reviewed for size and future maintenance cost.
- `tmp_*.py` should not stay in long-lived branch history after checkpoint.

## Command Discrepancy Snapshot

Decorator scan across `bot/commands` found no duplicate command names among declared `@commands.command(name=...)` entries.

Top-level command decorators outside `bot/commands` include:

- `weather` in `bot/weather_utils.py`

Manual review still required for:

- Alias collisions (`aliases=[...]`)
- Runtime-registered commands in media systems
- Usage text drift vs actual parser behavior

## Execution Plan From Here

1. Create split commits from checkpoint by concern:
   - `feat(factions): faction core + raffle coupling`
   - `feat(grid): grid cog + state manager + overlay`
   - `feat(tts): tts cog`
   - `chore(data): keep only canonical seed artifacts`
   - `chore(clean): remove temp scripts`

2. Decide policy for runtime files and encode it in `.gitignore`:
   - Ignore volatile state and cache files unless explicitly intended as seeds.

3. Produce a command catalog document:
   - Command, aliases, mod-only status, source file, usage string, verification status.

4. Run smoke validation pass:
   - Faction flow
   - Raffle integration
   - Grid flow
   - Overlay websocket updates

## Immediate Next Actions

- [ ] Confirm which `data/*.json` files are canonical seeds vs runtime state.
- [ ] Confirm whether `archive/rpg/*` should stay in active branch.
- [ ] Stage and commit cleanup pass (ignore + remove temp/runtime noise where approved).
- [ ] Open PR from checkpoint, then layer cleanup commits on top.
