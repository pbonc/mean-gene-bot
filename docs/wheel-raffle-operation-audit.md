# Universal unlocked invariant completion (2026-09-08)

This section supersedes historical Wheel policy and validation notes below.
Exact edited files: bot/wheel_state.py, bot/commands/wheel_cog.py,
tests/test_wheel_operations.py, docs/wheel-raffle-operation-audit.md.

Nonempty elimination spins require the existing wheel lock, validated in
WheelState.spin before selection/scoring/writing. Both flags retain one-slot
decrements while locked. Ordinary unlocked spins and empty spins are unchanged.
The command reports the validation detail, including !wheellock on. There is no
automatic locking or new wire action. Evidence: the model's two decrement
branches, existing locked decrement test, lock's existing entry restriction,
unlock's multiplier restoration, and reset's empty/unlocked/multiplier-one state.

Caller mapping: WheelCog.wheel_spin is the only production .spin() caller;
other Python calls are tests. It broadcasts spin/state only after success.
Overlay JavaScript displays spin events and sends only set_multiplier and
set_remove_on_win through apply_wheel_control. Twitch join/add/remove/color,
multiplier/flags/lock/reset use shared model operations; scores reload state.
Registry construction invokes load, overlay file payload lookup invokes load,
and every staged operation refreshes a private candidate through _load.

Legacy unlocked positive counts differing from multiplier are reconciled for
all remaining participants, including manual users. Locked counts are retained.
Public load atomically saves normalization before installing live state.
Operation refresh defers reconciliation persistence into the operation's commit,
including successful no-ops; later validation failure leaves disk unchanged.
Failed persistence preserves live containers, prior bytes, and registry state,
without success broadcasts. Unlock also saves reconciled counts before becoming
live. Unknown fields and manual membership survive reconciliation.

Tests replace the known-violation characterization with authoritative rejection
and command assertions for both flags, both together, and multiplier one/five.
They also cover every successful unlocked operation, ordinary spins, locked
elimination, unlock ordering/failure, legacy construction/reload/payload/no-op,
serialization/replacement failure, registry installation, and publication.

Validation (all exit 0):

```text
python -m unittest tests.test_wheel_operations tests.test_raffle_state_ownership tests.test_new_followers tests.test_streamstart
54 tests, OK
python -m unittest tests.test_storage_audit tests.test_wot_stats tests.test_research_policy tests.test_rpg_v2_engine tests.test_rpg_v2_contracts tests.test_research_synthesis tests.test_sports_evidence tests.test_temporal_context
93 tests, OK
python -m compileall -q bot tests
git diff --check
```

Direct whitespace scanning additionally covers all four edited files, including
the three untracked files. Non-data repository hashes verify only these four
files changed. Final Git status preserves the incoming path/status set. No
service startup, runtime-state access, commit, or unrelated edits occurred.
Git's existing CRLF conversion warnings are not whitespace errors.

---

﻿# Wheel operation and raffle consumer audit

## Wheel evidence and decisions

The repository has no separate typed Wheel action schema. The wire contract is
`wheel_control` with `action` and `value`, dispatched in
`bot/overlay_server.py` and emitted by `bot/overlay_static/wheel_overlay.html`.
Only `set_multiplier` and `set_remove_on_win` are accepted. There were no existing
Wheel operation tests before `tests/test_wheel_operations.py`.

| Action | Established implementation | Authoritative operation |
| --- | --- | --- |
| WebSocket `set_multiplier` | Coerce integer (invalid -> 1), clamp 1..500, replace every existing count including manual users; leave stored multiplier/manual membership unchanged | `WheelState.set_all_counts` |
| Twitch `!wheelmultiplier` | Validate 1..500, store multiplier, replace only non-manual current counts | `WheelState.set_multiplier` |
| Twitch `!wheeljoin` | Reject duplicates and locked wheel; user-requested counts must be one; command calculates configured multiplier and announces that count | `WheelState.join` preserves the established one-slot result; reply now reports one slot |
| Twitch `!wheeladd` | Add specified count for a new manual participant; reject duplicates and locked wheel | Existing `add_slots(..., allow_multi=True, manual=True)` |
| Twitch `!wheelremove`, `!wheelcolor` | Remove one participant / update an existing participant's color | `remove_user`, `set_color` |
| WebSocket `set_remove_on_win`, Twitch `!wheelremoveonwin` | Persist the same boolean flag | `set_remove_on_win` |

State and persistence now live in `bot/wheel_state.py`. The cog re-exports
`WheelState` for import compatibility. A path-keyed registry supplies the same
live object to Twitch and WebSocket controls. Operations refresh a private copy, validate, atomically replace the file, then
publish the candidate to the shared live object. Both callers broadcast only on
success. Unknown persisted fields survive saves. The wire action names and
legacy WebSocket coercions remain unchanged. Counts in the operation layer must
be integers in 1..500; WebSocket normalization/clamping remains in its adapter.
Colors use the same normalization in command parsing and the model. Manual adds
also enforce lock/duplicate checks in the operation layer.

**Unresolved action:** whether WebSocket `wheel_control/action=set_multiplier`
should also configure future joins and exempt manual users. Its handler says no;
the overlay labels the input “Multiplier” and describes `!wheelmultiplier` as
“set all counts,” which suggests equivalence but does not specify manual-entry or
future-join policy. No existing test resolves this discrepancy. This change
preserves both established behaviors under distinct operations. Merging them
would change manual users' odds and/or future participants' counts. A subsequent
Twitch multiplier change can still replace non-manual counts set by WebSocket.

There is **no individual absolute-count WebSocket action**, UI control, or test
in this repository. `set_slot_count` is not a supported schema. Whether such an
action should create a user, mark them manual, remove at zero, or be overridden
by a later multiplier is unresolved; adding it would invent policy. Existing
individual add/remove/color and spin decrement operations are retained. Spin
continues to decrement one slot under either removal mode; it is not a multiplier
operation.

**Dar's precise future-join decision:** after `!wheelmultiplier 4`, should a
previously absent participant receive **one slot** (the established persisted
behavior) or **four slots** (the old command's claim)? The original
`WheelCog.wheel_join` calculated four and announced four, but
`WheelState.add_slots(..., allow_multi=False)` unconditionally reset the count
to one. `wheel_overlay.html:230` says "Multiplier", line 246 says "join the
wheel", and line 250 says "set all counts"; none specifies future joins.
`git grep` of HEAD tests finds no Wheel tests. The initially untracked new test
asserting four encoded the guess; it was not an independent legacy contract.
The evidence does not establish intended policy. This review restores one-slot
joins, fixes the join reply to one, and removes the unfulfilled "for future
joins" promise from the multiplier reply. A decision for four must explicitly
change `join` and its regression tests. The separate WebSocket/manual-entry
policy decision above remains separate.

## Every raffle state consumer

Repository-wide searches covered both class names/import paths, `RaffleCog`
lookups, raffle file references, and read-method names, including tools/tests.

- `bot/raffle_state.py` is now the read-only projection (it previously exposed unused writers). Its production
  consumer is `labels_stats.get_raffle_odds`, reading `picks`. Its read APIs
  `load`, `available_entries`, `user_picks`, `all_picks`, `entries`, `picks`, and
  `prize` remain intact, including case-sensitive legacy lookups and numeric
  sorting. Ownership tests exercise these without modifying the file.
- `commands/raffle_cog.SimpleRaffleState` is the writer. `RaffleCog` uses its
  balance/pick reads, eligibility, prize, jackpot, open/chat and ZAP state as
  well as its mutation methods. No writer API was removed.
- `labels_stats.get_raffle_prize` calls the writer's `get_giveaway_amount`;
  `get_ticker_messages` reads `bad_beat_jackpot`. These imports and reads remain.
- Disabled `bot/commands/analytics_cog.py.disabled` also constructs the writer
  and calls `set_giveaway_amount`; it is not loaded as an active cog.
- `stream_analytics` reads `get_giveaway_amount` and writes via
  `set_giveaway_amount` on a separately loaded writer. These remain supported.
  This separate writer does not refresh an already loaded raffle cog; this
  pre-existing cross-instance synchronization limitation is not fixed by the
  Wheel registry.
- `new_follower_cog` uses the live cog's `add_entries`, `get_giveaway_amount`,
  and `is_open`; `wotd_cog` uses `add_entries`; `streamstart_cog` uses `stop_zap`,
  `start_zap`, and `open_raffle`.
- `media_overlay` calls `trigger_zap_sfx` / `trigger_zap_gif`;
  `song_request_simple` calls `trigger_zap_song` at both song request sites.
  These delegate to the raffle cog's existing award operations.
- `overlay_server.get_raffle_data` reads JSON directly for `raffle_numbers.html`;
  `main.backup_raffle_state` copies the file. Neither is a state-class writer.
  Main's ticker loops consume the label helpers above.
- Existing direct raffle tests are `test_raffle_state_ownership`,
  `test_new_followers`, and `test_streamstart`; no other test references a raffle
  state class or Wheel control. The added Wheel suite executes real command
  callbacks and WebSocket dispatch with temporary state files and mocked sockets.

## Exact implementation scope and ownership

This review edits six already dirty/untracked files:

- `bot/wheel_state.py`: adds `WheelOperationError`, `staged`, `validated_count`,
  `normalize_hex_color`, `validated_color`; updates `save`, `load`, `add_slots`,
  `join`, `set_all_counts`, `set_color`, `set_multiplier`, `apply_wheel_control`.
  `remove_user`, `set_remove_on_win`, `set_wheel_locked`,
  `set_last_man_standing`, `reset`, and `spin` now use staged commits.
- `bot/commands/wheel_cog.py`: imports/re-exports the shared color normalizer;
  adds `wheel_errors` on all eleven `wheel_*` command callbacks; corrects
  `wheel_join` and `wheel_multiplier` replies. `WheelCog.__init__` already used
  `get_wheel_state` in the incoming diff.
- `bot/overlay_server.py`: `websocket_handler` uses the operation's refresh and
  returns `wheel_error` on a failed commit; success broadcasts its live payload.
  The unrelated lifecycle changes in this file are incoming work.
- `tests/test_wheel_operations.py`: extends `WheelTests` and its isolated socket
  helper, tests one-slot joins, bounds, invalid colors/counts, lock/duplicates,
  both transports, every mutation under serialization failure, replacement
  failure, invalid refresh, unknown fields, and full reload agreement. A delivery
  failure test distinguishes committed state from failure to broadcast it.
- `tests/test_raffle_state_ownership.py`: strengthens
  `test_projection_has_no_write_capability` with local attribute replacement
  and nested prize edits that cannot affect persisted state.
- `docs/wheel-raffle-operation-audit.md`: evidence, decisions and validation.

The full Wheel/raffle diff additionally includes the incoming edits to
`bot/raffle_state.py` (`SimpleRaffleState.__init__`, `load`, preserved read
methods, removal of write methods) and `bot/commands/raffle_cog.py`
(`SimpleRaffleState.__init__`, `load`, `save`, retaining unknown fields). These
were reviewed and tested, with no further implementation edits this turn.

Old Wheel ownership: Twitch -> cog-local `WheelState` -> direct JSON save;
WebSocket -> `_load_wheel_state_file` / dictionary edits /
`_save_wheel_state_file` -> independently reloaded payload. New ownership:
Twitch -> shared `WheelState` operation; WebSocket -> `apply_wheel_control` ->
shared `WheelState` operation; both -> staged validation and atomic save ->
shared live state -> broadcast. `WheelState` remains re-exported by the cog.

Old raffle ownership: two `SimpleRaffleState` classes could overwrite the same
file with different schemas. New: `commands.raffle_cog.SimpleRaffleState` owns
writes and retains the union plus unknown fields; `bot.raffle_state` provides
read APIs without save/repair/create capability. Mapping fields reject item
writes. Local attribute replacement and nested `prize` edits are harmless
in-memory edits, not deep immutability; no projection method can persist them.

Failure behavior deliberately changes: failed Wheel writes no longer leave
partial live mutation or truncate the old JSON. Both transports log and report
"no change was committed", without a success broadcast. Twitch reports chat
text; WebSocket replies `wheel_error`. The current overlay has no visual error
renderer for this new reply. Transport delivery failure after a successful
commit does not roll back persisted state and is not called a commit failure.
The synchronous transaction covers this process's event-loop callers; it is
not a cross-process file lock. Legacy truthiness is preserved for WebSocket
booleans (including the string `"false"` being truthy).

## Validation

Final exact commands and results:

```text
python -m unittest tests.test_wheel_operations tests.test_raffle_state_ownership tests.test_new_followers tests.test_streamstart
37 tests, OK, exit 0

python -m unittest tests.test_storage_audit tests.test_wot_stats tests.test_research_policy tests.test_rpg_v2_engine tests.test_rpg_v2_contracts tests.test_research_synthesis tests.test_sports_evidence tests.test_temporal_context
93 tests, OK, exit 0

python -m compileall -q bot tests
No output, exit 0

git diff --check
No whitespace errors, exit 0 (existing LF/CRLF conversion warnings only)
```

Focused tests use temporary state, real command callbacks and WebSocket dispatch,
mocked sockets/broadcasting, and an AST-extracted real raffle writer class to
avoid cog import effects. No bot startup or external service calls were needed.
An intermediate failure exposed stale `_persisted_fields` after save; successful
commits now update that snapshot. Two subsequent test failures compared a
registry-normalized path string with a `Path` object; the reload comparison now
uses the same path. Both failures were resolved before the final passing run.

Remaining runtime validation: real Twitch moderator/viewer commands, an OBS or
browser overlay connected to the running bot, reconnect payloads, Windows file
replacement permissions with the deployed bot account, and operator handling
of `wheel_error`. No live broadcast, stream, or production state mutation was
performed. Raffle's pre-existing independent-writer synchronization and direct
(non-atomic) writer saves are outside this Wheel transaction change.

## Initial working tree (this review)

```text
 M .env.example
 M bot/commands/fishing_cog.py
 M bot/commands/media_overlay.py
 M bot/commands/raffle_cog.py
 M bot/commands/song_cog.py
 M bot/commands/song_request_simple.py
 M bot/commands/walkin.py
 M bot/commands/wheel_cog.py
 M bot/config.py
 M bot/main.py
 M bot/overlay_server.py
 M bot/overlay_static/fishing/fishing.css
 M bot/overlay_static/fishing/fishing.js
 M bot/raffle_state.py
 M bot/weather_utils.py
 M data/autoplay_state.json
 M data/bittleships_state.json
 M data/coup_state.json
 M data/fishing.db
 M data/new_follower_state.json
 M data/playlist_cache.json
 M data/user_quarters.json
 M data/wotd_state.json
 M tests/test_fishing_service.py
?? bot/discord_operator.py
?? bot/hermes_bridge.py
?? bot/hermes_debug.py
?? bot/lore_capture.py
?? bot/lore_observability.py
?? bot/lore_store.py
?? bot/research_policy.py
?? bot/research_synthesis.py
?? bot/sports_evidence.py
?? bot/wheel_state.py
?? data/lore.db
?? docs/wheel-raffle-operation-audit.md
?? tests/offline_main.py
?? tests/test_audio_dependencies.py
?? tests/test_cleanup_lifecycle.py
?? tests/test_discord_operator.py
?? tests/test_hermes_bridge.py
?? tests/test_hermes_debug.py
?? tests/test_lore_capture.py
?? tests/test_lore_ingress.py
?? tests/test_lore_observability.py
?? tests/test_lore_store.py
?? tests/test_raffle_state_ownership.py
?? tests/test_research_policy.py
?? tests/test_research_synthesis.py
?? tests/test_sports_evidence.py
?? tests/test_temporal_context.py
?? tests/test_wheel_operations.py
```

## Final working-tree scope

Initial and final status path/status lists are identical: 24 modified tracked files and 28 untracked files. No new path was introduced by this review. The initial list above is also the final list. Only the six files enumerated under implementation scope were edited this turn; incoming unrelated source and data changes remain in place. No commit was created.
