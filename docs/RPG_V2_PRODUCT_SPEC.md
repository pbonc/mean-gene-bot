# Stream RPG v2 Product and Contract Specification

## Product statement

Stream RPG v2 is a persistent chat expedition with two public web presentations and one private operator presentation:

- A transparent 1920x96 journey strip remains available during the normal stream.
- A 1920x1080 JRPG battle page is shown only when the streamer manually selects its OBS scene.
- A private control page prepares, starts, pauses, aborts, or resolves encounters.

The bot never changes OBS scenes, opens the battle page, or interrupts the stream automatically.

## Core principles

- The logical expedition and battle rosters are uncapped.
- Rendering density never determines combat eligibility.
- Every friendly class has three numbered skills and a declared automatic default.
- Only the acting viewer may select a skill by sending a bare `1`, `2`, or `3`.
- A recently active viewer receives a short choice window.
- An absent viewer acts immediately through the class default.
- A timed-out viewer uses the class default.
- No Twitch response is required for combat to progress.
- Python owns game state and resolution. Web pages render snapshots and animation events.
- The archived RPG is reference material, never a runtime dependency.

## Presentation surfaces

### Journey strip: `/rpg-micro`

The strip is persistent, transparent stream decoration. It shows the expedition traveling, resting, camping, finding treasure, meeting a merchant, or waiting at an encounter. It uses adaptive crowd layout and temporary name flourishes so a joined viewer can recognize their character.

Major battles do not resolve inside the strip. When an encounter is ready, the party settles and a compact announcement appears. The encounter waits indefinitely for the streamer.

### Battle page: `/rpg-battle`

The full-screen page places the friendly crowd on the left and enemy crowd on the right. It reserves prominent friendly and enemy action positions near the center. On an actor's turn:

1. The actor highlights in its crowd.
2. The actor moves to its side's action position.
3. The page shows the actor name and three numbered skills.
4. A viewer selection or automatic default resolves.
5. The action, targets, and results animate.
6. The actor returns to its crowd unless defeated or otherwise displaced.

The page remains dormant when no battle is active. Loading or displaying it does not start an encounter.

### Control page: `/rpg-control`

The private page separates encounter preparation from battle start. Initial controls are prepare, start, pause, resume, abort, auto-resolve, advance stalled playback, show results, and return to journey. It also displays the current phase, pending actor, choice deadline, accepted choice, and overlay connection status.

## Manual OBS workflow

```text
Journey strip announces ENCOUNTER READY
                 -> encounter waits
Streamer manually selects the RPG battle scene in OBS
                 -> battle page is visible but does not self-start
Streamer starts the prepared encounter from the control page
                 -> battle runs
Results complete
                 -> streamer manually returns to the normal OBS scene
Control returns the expedition to journey state
```

## Roster and presence model

- `!join` creates or reactivates a character.
- Ordinary chat messages refresh presence after joining.
- Expedition membership and current presence are distinct from persistent character ownership.
- Encounter participants are captured when the encounter is prepared according to a documented presence policy.
- There is no four-character active party and no combat reserve system.
- Large rosters remain eligible even when the renderer must pack, overlap, scale, or visually de-emphasize idle sprites.
- The acting character always receives an identifiable action position and nameplate.
- Inactivity may remove a character from the visible expedition without deleting progression.

## Class progression and initial skills

Every new viewer begins as an Adventurer and may advance at level 5.

| Class | Choice 1 | Choice 2 | Choice 3 | Default policy |
|---|---|---|---|---|
| Adventurer | Strike | Brace | Rally | Strike |
| Warrior | Slash | Guard Ally | Shield Slam | Slash |
| Mage | Arcane Bolt | Fireball | Focus | Arcane Bolt |
| Healer | Smite | Heal | Group Heal | Heal when useful; otherwise Smite |
| Ranger | Quick Shot | Mark Target | Volley | Quick Shot |

The first version uses automatic targeting. Viewers select a skill, not a target. Skill effects and balance are defined by the engine rather than the persistence or transport contracts.

## Turn and timeout rules

Every friendly turn produces a turn prompt containing:

- battle ID
- unique turn ID
- acting viewer ID
- exactly three numbered skill choices
- declared default choice
- whether the engine is waiting for that viewer
- deadline when waiting, otherwise no deadline

Only a bare `1`, `2`, or `3` from the acting viewer is accepted. Other viewers' numbers, invalid text, duplicates, and late responses do not change the turn and should not produce routine error messages.

When the actor is recently active, the engine opens a short configurable deadline. A valid selection ends the wait immediately. At expiration, the engine selects the declared default. When the actor is absent, the engine does not open a deadline and selects the default immediately.

Enemy turns always use automatic behavior and never wait for chat.

## State machine

```text
JOURNEY
    -> ENCOUNTER_READY
    -> BATTLE_STARTING       (operator action only)
    -> ACTOR_CHOICE          (friendly active viewer only)
         -> ACTION_PLAYBACK
    -> ACTION_PLAYBACK       (enemy or automatic friendly)
    -> CHECK
         -> ACTOR_CHOICE or ACTION_PLAYBACK when combat continues
         -> VICTORY
         -> DEFEAT
    -> RESULTS
    -> JOURNEY               (operator-controlled presentation handoff)

Any active battle phase may enter PAUSED and later resume.
```

Changing OBS scenes has no state-machine effect. Browser connection or visibility must never determine game progress.

## Version 2 contracts

The current contract version is `2`. Version 1 is intentionally rejected rather than silently interpreted.

### Player record

Persists stable viewer identity, display name, class, level, XP, cosmetics, and aggregate history. It does not persist presence, active turns, cooldowns, stream claims, or legacy economy fields.

### Runtime snapshot

Contains:

- current phase and update time
- optional battle ID and round
- uncapped expedition actor list
- uncapped encounter participant list
- uncapped enemy list
- optional pending turn prompt
- last animation-event sequence
- optional result

Actor IDs must be present and unique within each list. `ACTOR_CHOICE` requires a valid pending turn prompt.

### Turn prompt

Contains exactly three choices numbered 1, 2, and 3. Each choice has a stable skill ID and display label. The prompt declares a default choice. A prompt waiting for a viewer requires a deadline; an automatic prompt must not have one.

### Animation event

Contains a battle ID, round, monotonically increasing sequence, event type, optional actor, targets, effect key, and display values. Overlays ignore duplicated or stale sequences and recover from the latest runtime snapshot.

## Code and data boundaries

```text
bot/rpg_v2/
    contracts.py      # versioned persistence and transport boundaries
    models.py         # future pure actors, skills, effects, encounters
    engine.py         # future pure deterministic combat
    classes.py        # future friendly class definitions
    enemies.py        # future enemy definitions
    progression.py    # future XP and advancement
    repository.py     # future persistence boundary
    service.py        # future timers, lifecycle, publication
    commands.py       # future Twitch presence and numeric input adapter

bot/overlay_static/rpg_micro/    # journey strip
bot/overlay_static/rpg_battle/   # future full-screen battle page
bot/overlay_static/rpg_control/  # future private control page
data/rpg_v2/                     # future mutable v2 state
```

The engine must run without Twitch, OBS, WebSockets, or files. The overlay must never decide damage, targeting, rewards, timeouts, or progression.

## Archive and migration

- `archive/rpg/` remains read-only historical material.
- v2 never imports the archived cog or accepts its state as a v2 record.
- Active legacy battles, classes, cooldowns, pets, currencies, referrals, and salaries are not migrated.
- A future one-way migration may preserve identity and award reviewed cosmetic recognition.
- No migration work begins until persistence and progression policies are stable.

## Deferred features

Inventories, equipment stats, currencies, gacha, referrals, salaries, PvP, prestige classes, branching skill trees, viewer-selected targets, and automatic OBS control remain out of the initial release.
