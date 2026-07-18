# Mean Gene Bot Roadmap

This file is the execution roadmap for the whole bot. Detailed feature specifications remain in `docs/`; this document records priorities, sprint-sized outcomes, and completion criteria.

## Roadmap conventions

- A sprint is a focused development slice, not necessarily a fixed calendar period.
- Each sprint should end with something demonstrable or operationally safer.
- A sprint is complete only when its exit criteria are met.
- New work should be added under the appropriate workstream rather than mixed into an unrelated sprint.
- Live state in `data/` is not cleanup material. Back up and validate it before migrations.

## Current priorities

1. Redefine the Stream RPG contracts around an uncapped expedition and manual full-screen battles.
2. Turn the proven micro-strip prototype into a useful ambient journey surface.
3. Build the standalone turn engine and three-skill class kits.
4. Build the full-screen battle source and private control surface.
5. Preserve bot reliability while new work is introduced.
6. Address storage, telemetry, and repository hygiene in bounded maintenance sprints.

---

# Workstream: Stream RPG v2

## Goal

Create a persistent chat expedition with two public presentations: a tiny transparent journey strip during the normal stream and a manually selected full-screen JRPG battle scene for encounters. Every participating character belongs to the battle roster. When a recently active viewer's turn arrives, they may choose one of three skills by typing `1`, `2`, or `3`; a class-appropriate default resolves automatically on timeout or absence so combat never stalls.

The detailed product and technical specification lives in [docs/RPG_V2_PRODUCT_SPEC.md](docs/RPG_V2_PRODUCT_SPEC.md).

## Product baseline

- Transparent 1920x96 journey strip for a 1920x1080 stream canvas
- Full-screen 1920x1080 JRPG battle source selected manually in OBS
- Private browser-based control surface for starting, pausing, aborting, and resolving encounters
- No automatic OBS scene changes and no battle page popups
- Uncapped logical expedition and battle roster; rendering density adapts independently of eligibility
- Friendly crowd on the left, enemy crowd on the right, and clear action positions between them
- Adventurer base class progressing into Warrior, Mage, Healer, or Ranger
- Slime and Goblin common enemies, followed by an Ogre boss
- Journey loop: `wander -> ambient event -> encounter ready -> wait for streamer`
- Battle loop: `start -> actor turn -> choice or default -> action -> outcome check -> results`
- Three numbered skills per class with automatic targeting in the initial release
- Normal chat activity refreshes presence; only the acting viewer's bare `1`, `2`, or `3` is accepted
- Every class has a safe default action; absent viewers resolve immediately and active-viewer prompts time out
- Short strip announcements for camps, treasure, encounters, levels, and loot
- Persistent identity and progression without importing the old RPG economy

## RPG Sprint 0: Archive boundary and decisions

**Objective:** Make the old and new RPG pathways unambiguous before implementation begins.

**Status:** Complete — 2026-07-17

- Treat `archive/rpg/` as read-only historical material.
- Add an archive manifest classifying old concepts as keep, reinterpret, or retire.
- Confirm that v2 will not import `archive/rpg/rpg_cog.py` or restore it as an active cog.
- Define versioned player, runtime snapshot, and animation-event schemas.
- Confirm the initial strip height, active party size, actor scale, and class roster.
- Update the detailed RPG specification from command rounds to the ambient automatic battle loop.
- Define legacy recognition separately from combat progression; default to cosmetic titles rather than inherited power.

**Exit criteria:** The v2 package, data paths, schemas, and archive rules are documented well enough that development cannot accidentally reactivate the legacy implementation.

## RPG Sprint 1: Transparent micro-strip prototype

**Objective:** Prove that the idea is readable and pleasant at its actual stream size before building the game.

**Status:** Complete — 2026-07-18

- Add a new `/rpg-micro` OBS browser-source route without replacing `/battle`.
- Build a 1920x96 page with a fully transparent background.
- Create temporary, visually distinct silhouettes for the five friendly classes and three enemies.
- Render a readable friendly group, enemy group, tiny health bars, status pips, and temporary name/action labels.
- Demonstrate wandering, enemy arrival, melee lunge, projectile, healing, hit reaction, knockout, victory, defeat, and loot flourish.
- Add a scripted demo loop independent of Twitch and persistent data.
- Test the source in OBS at 1080p, in a downscaled preview, and against both bright and dark stream content.
- Check whether a 64-pixel quiet mode is useful or whether a fixed 96-pixel source is sufficiently unobtrusive.

**Exit criteria:** Viewers can distinguish sides, broad character roles, health changes, and major events after realistic scaling and compression, without permanent text panels.

## RPG Sprint 2: Contract reset and battle rules

**Objective:** Replace the obsolete four-slot auto-battle assumptions before implementing the engine.

**Status:** Complete — 2026-07-18

- Remove the four-friendly eligibility limit from the v2 runtime contract.
- Model an uncapped expedition roster and encounter participant roster.
- Keep screen position and sprite density out of combat eligibility rules.
- Add explicit phases for journey, encounter ready, streamer-controlled start, actor choice, action playback, results, and return to journey.
- Define the manual handoff:
  - the strip announces and holds an encounter
  - the streamer changes OBS scenes
  - a control action starts the battle
  - nothing changes OBS scenes automatically
- Define a turn prompt containing actor ID, three skill choices, deadline, and default skill.
- Define timeout behavior:
  - recently active viewer gets a short choice window
  - valid input resolves immediately
  - timeout uses the class default
  - absent viewer auto-acts without waiting
- Update the detailed specification, archive decisions, fixtures, and contract tests.

**Exit criteria:** Versioned contracts describe the journey strip, full battle, control surface, uncapped roster, numbered choices, and non-blocking defaults without retaining four-slot assumptions.

## RPG Sprint 3: Journey strip as an expedition surface

**Objective:** Convert the micro strip from a combat demo into persistent, low-distraction stream decoration before the full battle system is complete.

**Status:** In progress — functional ambient renderer implemented; OBS visual review pending

- Display the joined expedition as an adaptive friendly group rather than four active slots.
- Retain simple idle motion and temporary join/name flourishes.
- Add restrained ambient states such as wandering, resting, camp, treasure, merchant, and encounter ready.
- Freeze or settle the party when an encounter is ready.
- Show compact encounter, progression, and loot announcements.
- Use scripted or lightweight placeholder events until the real battle engine is connected.
- Do not run major battles in the strip; minor ambient events may resolve without taking over the stream.
- Keep visual events configurable so the strip can be quieted or hidden instantly.

**Exit criteria:** The strip works as useful stream decoration, communicates expedition state and pending encounters, and does not require attention, chat commands, or the completed battle engine.

## RPG Sprint 4: Standalone turn engine and class kits

**Objective:** Implement deterministic combat without Twitch, OBS, WebSockets, or persistence.

- Create pure models for actors, skills, effects, encounters, turns, and outcomes.
- Resolve one actor at a time using speed, priority, and a stable tie-breaker.
- Give each friendly class three skills and one declared default:
  - Adventurer: Strike, Brace, Rally; default Strike
  - Warrior: Slash, Guard Ally, Shield Slam; default Slash
  - Mage: Arcane Bolt, Fireball, Focus; default Arcane Bolt
  - Healer: Smite, Heal, Group Heal; default Heal when needed, otherwise Smite
  - Ranger: Quick Shot, Mark Target, Volley; default Quick Shot
- Use automatic targeting in the first release; viewers choose a skill, not a target.
- Add Slime, Goblin, and Ogre skills and defaults.
- Produce ordered domain and animation events for prompts, choices, defaults, movement, effects, damage, healing, knockouts, and results.
- Support seeded simulations with one participant, typical groups, and large rosters.
- Test invalid choices, late choices, timeouts, absent actors, targeting, turn order, victory, defeat, and stalemate protection.

**Exit criteria:** Battles of varying roster sizes complete deterministically, every turn has a valid default path, and no viewer response is required for progress.

## RPG Sprint 5: Full-screen battle prototype

**Objective:** Prove the crowd-and-action-stage presentation at 1920x1080 before Twitch integration.

- Add `/rpg-battle` as a separate OBS browser source.
- Place the friendly crowd on the left and enemy crowd on the right.
- Reserve prominent friendly and enemy action positions near the center.
- Adapt crowd layout by population while keeping all roster members eligible.
- Highlight the acting crowd sprite, move it to the action position, show its nameplate and three numbered skills, resolve the effect, and return it to the crowd.
- Show the current viewer prompt clearly enough for mobile users to respond with a bare number.
- Accelerate ordinary playback for large encounters without hiding specials, knockouts, or major heals.
- Add scripted fixtures for small, medium, and crowded battles.
- Keep the battle page dormant when no battle is active; never trigger navigation or OBS scene changes.

**Exit criteria:** The full-screen prototype clearly presents turn ownership, three choices, targets, outcomes, and crowd identity across tested roster sizes.

## RPG Sprint 6: Private battle control surface

**Objective:** Give the streamer reliable manual control without placing operator controls on-stream.

- Add `/rpg-control` with authenticated or local-only operator controls.
- Support prepare encounter, start, pause, resume, abort, auto-resolve, advance stalled playback, show results, and return to journey.
- Make encounter preparation and battle start separate operations so the streamer can switch OBS scenes first.
- Display connected overlay status, current phase, pending actor, deadline, and last accepted choice.
- Ensure refreshing or disconnecting the controller cannot corrupt or stall combat.
- Do not attempt automatic OBS scene switching in the initial release.

**Exit criteria:** The streamer can safely stage and operate an encounter while manually controlling OBS scenes.

## RPG Sprint 7: Twitch presence and numbered choices

**Objective:** Connect ordinary chat presence and turn-specific `1`, `2`, or `3` input without creating general chat spam.

- Add `!join` to create or reactivate a character.
- Refresh joined-viewer presence from ordinary chat messages.
- Remove a character from the visible expedition after configurable inactivity without deleting progression.
- Accept a bare `1`, `2`, or `3` only from the viewer whose choice window is currently open.
- Ignore other numeric messages and late responses without posting errors.
- End the choice window immediately on valid input.
- Use the declared class default on timeout and skip the wait for viewers considered absent.
- Suppress routine bot confirmations; the battle screen confirms the accepted choice.
- Add rate-limit, duplicate-message, reconnect, and identity tests.

**Exit criteria:** A private stream completes battles through a mixture of viewer selections and automatic defaults, with no stalled turns and minimal bot output.

## RPG Sprint 8: Persistence and progression

**Objective:** Give viewers durable identity and meaningful choices without allowing veterans to invalidate newcomers.

- Persist viewer identity, XP, level, class, cosmetics, and basic battle history.
- Begin every new character as an Adventurer.
- Unlock Warrior, Mage, Healer, or Ranger selection at level 5.
- Keep stat growth conservative and emphasize cosmetics, titles, and animation variants.
- Persist encounter state safely enough to recover or explicitly abort after restart.
- Add versioned persistence, migration, backup, and recovery tests.
- Create a reviewed, one-way legacy recognition migration only after the v2 schema stabilizes.

**Exit criteria:** Viewers can leave, return, choose a class, and retain recognizable progress without importing legacy combat balance.

## RPG Sprint 9: Stream trial and pacing

**Objective:** Validate that the journey/battle split supports stream growth and remains practical with real chat behavior.

- Measure joins, returns, encounter acceptance, choice response rate, defaults, battle duration, and roster size.
- Tune active-viewer choice windows, absence thresholds, playback speed, and large-roster acceleration.
- Test manual scene-switch timing from encounter ready through results.
- Tune strip brightness, announcement frequency, battle readability, and sound independently.
- Document OBS setup, controller use, recovery, and safe fallback behavior.
- Provide quiet, paused, hidden, and auto-resolve operating modes.

**Exit criteria:** Several real streams show that the strip supports normal content, full battles are easy to stage manually, and timeouts/defaults keep every encounter moving.

## RPG post-launch backlog

- Additional enemy families, environments, camps, treasure, merchants, and journey events
- Cosmetic pets or assists that do not complicate core combat
- Raid-triggered reinforcements or special encounters
- Community milestones and scheduled bosses
- Additional cosmetics, titles, palettes, and animation variants
- Optional group decisions, boss mechanics, or target selection after the numbered-skill loop is proven

The following remain explicitly deferred until usage data justifies them: inventories, equipment stats, currencies, gacha, referrals, salaries, PvP, prestige classes, and branching skill trees.

---

# Workstream: Reliability and operations

## Operations Sprint 0: Connection resilience

**Objective:** Prevent a transient Twitch or Discord outage from terminating unrelated bot services.

- Maintain automated coverage for Twitch reconnect behavior inside and outside the configured grace period.
- Add structured connection lifecycle events without exposing tokens.
- Decide and document whether sustained failure restarts one service or exits under a supervisor.
- Add a concise startup health summary.

**Exit criteria:** A short DNS or network interruption reconnects without terminating overlays or unrelated services.

## Operations Sprint 1: Storage lifecycle

**Objective:** Make large caches and growing backups manageable without risking live data.

- Provide a dry-run storage report for music cache, duplicates, backups, and reclaimable space.
- Add configurable music-cache limits and safe eviction rules.
- Protect queued, currently playing, configured, and recently used media.
- Bound raffle backup retention and avoid identical backups.
- Confirm all consumers before consolidating duplicate static media roots.

**Exit criteria:** Operators can understand and safely control storage growth through an allowlisted, dry-run-first workflow.

## Operations Sprint 2: Logging and telemetry

**Objective:** Retain useful evidence without unbounded files or noisy routine messages.

- Use named loggers and rotating handlers.
- Rotate telemetry independently and avoid loading the full telemetry file for tail operations.
- Keep broadcast and polling detail at DEBUG.
- Add service and correlation fields for connection and lifecycle events.

**Exit criteria:** Normal operation produces compact logs, while a failure can still be reconstructed end to end.

---

# Workstream: Bot architecture and maintenance

## Maintenance Sprint 0: Active-feature inventory

**Objective:** Clearly identify what the repository actively runs and what is historical or recoverable material.

- Classify each cog, overlay, root-level utility, compiled artifact, and temporary script as keep, repair, replace, archive, or remove.
- Require a known use case and a smoke test for active features.
- Separate immutable configuration and seed data from mutable runtime state.
- Document canonical locations for overlays, assets, logs, backups, and caches.

**Exit criteria:** A contributor can determine whether a file is active without relying on filenames or oral history.

## Maintenance Sprint 1: Application boundaries

**Objective:** Reduce coupling in startup and the largest modules without combining this work with RPG development.

- Separate bootstrap, lifecycle supervision, Twitch, Discord, overlays, and scheduled-task ownership.
- Replace import-time dependency checks with explicit startup checks.
- Establish an application context rather than adding new global state.
- Split oversized modules only through behavior-preserving, tested changes.

**Exit criteria:** Services have explicit owners and can fail, start, and stop without hidden import side effects.

## Maintenance Sprint 2: Baseline tests and operator documentation

**Objective:** Make routine changes safer and operation less dependent on memory.

- Add compile/import, command-routing, persistence, and external-response fixture tests.
- Document startup, shutdown, backup, restore, token refresh, cache cleanup, and incident diagnosis.
- Replace the empty root README with a short project entry point linking to detailed guides.

**Exit criteria:** Core checks run repeatably and a new operator can perform common recovery tasks from documentation.

---

# Workstream: Music and media

## Candidate sprints

- Separate song queue, downloader/cache, playback, Sheets synchronization, and command responsibilities.
- Normalize media filenames and prevent duplicate `.mp3.mp3` outputs.
- Add cache health reporting and explicit protected-entry rules.
- Establish a single canonical overlay asset root after consumer verification.

These items need prioritization before they become committed sprints.

---

# Workstream: Sports and ticker

## Candidate sprints

- Share one long-lived HTTP session and a common fetch/cache pipeline.
- Fetch league data concurrently with deadlines and provider backoff.
- Add stale-while-revalidate and negative caching.
- Make stream-day timezone boundaries explicit.
- Add fixture tests for scheduled, live, final, postponed, and malformed responses.

These items need prioritization before they become committed sprints.

---

# Ideas and uncommitted work

Add new ideas here before scheduling them. Each idea should eventually state the viewer/operator problem, intended outcome, dependencies, risks, and a measurable exit criterion.

- Additional presentation modes driven by the shared RPG engine
- Bot management and health dashboard
- Improved Discord/Twitch cross-platform command ownership
- Additional stream-growth experiments that do not rely on chat spam

---

# Completed sprints

Move completed sprint summaries here with the completion date, relevant commit or pull request, and any deferred follow-up work.

## 2026-07-17: RPG Sprint 0 — Archive boundary and decisions

- Added a read-only archive manifest with keep, reinterpret, and retire decisions.
- Established `bot/rpg_v2/` without dependencies on the archived RPG, Twitch, OBS, or file storage.
- Added version 1 player, runtime snapshot, and sequenced animation-event contracts.
- Locked the initial class roster and initial prototype limits; Sprint 2 now explicitly replaces the superseded four-friendly auto-battle assumptions.
- Updated the detailed RPG specification to use chat for presence rather than required combat commands.
- Added contract tests for defaults, retired legacy fields, class validation, actor limits, and ordered events.
- Deferred the one-way legacy migration until the v2 persistence schema and progression policy are proven in later sprints.

## 2026-07-18: RPG Sprint 1 — Transparent micro-strip prototype

- Added the `/rpg-micro` transparent OBS browser source and verified it at 1920x1080 source size with a 1920x96 bottom strip.
- Added readable temporary sprites for Adventurer, Warrior, Mage, Healer, Ranger, Slime, Goblin, and Ogre.
- Demonstrated idle motion, enemy arrival, melee and projectile actions, healing, health changes, action nameplates, victory, and loot flourishes.
- Corrected aspect-ratio handling after live OBS review and placed the Warrior at the friendly front.
- Kept scenery effects out of the baseline after review to preserve a simple visual foundation.
- Scheduled conversion from the combat demo to the expedition journey surface as the next visual deliverable in RPG Sprint 3.

## 2026-07-18: RPG Sprint 2 — Contract reset and battle rules

- Replaced contract version 1 with an explicitly incompatible version 2.
- Removed active-party, reserve-count, four-friendly, and three-enemy limits from runtime state.
- Added uncapped expedition, participant, and enemy collections with unique actor identity validation.
- Added journey, encounter-ready, operator-start, actor-choice, playback, result, and pause phases.
- Added a turn-prompt contract requiring exactly three numbered skills and a declared default.
- Distinguished timed active-viewer prompts from immediate absent-viewer defaults.
- Required pending turns to match the current battle and an encounter participant.
- Replaced the micro-strip-only specification with the combined journey, battle, control, Twitch-input, and manual-OBS product specification.
