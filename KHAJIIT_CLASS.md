# Khajiit Custom Class

## Overview
Custom class designed exclusively for player **caerdwyn**. The Khajiit is a feline fighter with unique battle skills and a charitable stream skill.

## Auto-Assignment
- **Player**: caerdwyn
- **Class Name**: Khajiit  
- **Tier**: 1
- **Base Class**: Khajiit
- Automatically assigned on first embark and maintained throughout the game

## Battle Skills

### 1. **!scratch** (Moderate Direct Damage + Bleed)
- **Damage**: 5 base damage (scales with level)
- **Special Effect**: 30% chance to apply bleed
- **Bleed Details**: 
  - Stacks with other bleeds
  - Deals 2 damage per stack per turn
  - Lasts 3 turns
- **Usage**: `!scratch [monster_number]`
- **Description**: Slash at enemies with sharp claws, potentially causing them to bleed

### 2. **!hairball** (Direct Damage + Gross Out DoT)
- **Damage**: 4 base damage (scales with level)
- **Special Effect**: 35% chance to apply "Gross Out" DoT
- **Gross Out Details**:
  - Deals 1 damage per turn
  - Lasts 3 turns
  - Unique DoT effect (separate from bleed, corruption, dragonfire)
- **Usage**: `!hairball [monster_number]`
- **Description**: Hack up a hairball at enemies, potentially grossing them out for ongoing damage

### 3. **!meow** (Random Object Knock-Off)
- **Damage**: Variable (0-10+ damage)
- **Special Effect**: Knocks a random object from a shelf with different outcomes
- **Usage**: `!meow`
- **Description**: Very cat-like behavior with chaotic results!

#### Possible Objects & Effects:

| Object | Effect | Damage | Probability |
|--------|--------|--------|-------------|
| Stapler, Pen, Coffee Mug, Remote, Phone | Light damage to random monster | 2 | 45% |
| Laptop, Monitor, Printer, Keyboard, Desk Lamp | Moderate damage to random monster | 5 | 35% |
| Bookshelf, Filing Cabinet, Potted Plant, Office Chair | Heavy damage to random monster | 10 | 18% |
| Bowling Ball | **INSTAKILL** random monster | Instant death | 1.9% |
| **Heavy Lourde** | **PARTY WIPE** - kills all players | Total party kill | 0.1% |

## Stream Skill

### **!coin** (Charitable Gift)
- **Effect**: Gives 1-5 raffle entries to **all other embarked players** (not caerdwyn)
- **Usage**: `!coin` (once per stream)
- **Entry Distribution**:
  - 1 entry: 50% chance
  - 2 entries: 30% chance
  - 3 entries: 15% chance
  - 4 entries: 4% chance
  - 5 entries: 1% chance
- **Requirements**: Must be embarked; at least one other player must be embarked
- **Cooldown**: Once per stream (resets on !rpgreset)
- **Description**: Khajiit has wares if you have coin! Share your wealth with fellow adventurers.

## Mechanics Notes

### Gross Out DoT
- New status effect added to monster tracking
- Applied independently of other DoTs (corruption, dragonfire, bleed)
- Displays message: "{monster} is grossed out and takes 1 damage!"
- Tracked via `gross_out_damage` and `gross_out_rounds_remaining` fields

### Meow Random Selection
- Uses weighted random distribution
- Most common: useful light/moderate damage
- Rare: heavy damage or instakill
- Ultra-rare: party wipe (0.1% = 1 in 1000)
- No targeting - always hits random alive monster
- **Heavy Lourde** immediately ends battle with all players at 0 HP

## Constants Added
```python
KHAJIIT_NAME = "caerdwyn"
KHAJIIT_SCRATCH_BASE_DAMAGE = 5
KHAJIIT_SCRATCH_BLEED_CHANCE = 0.30
KHAJIIT_HAIRBALL_BASE_DAMAGE = 4
KHAJIIT_HAIRBALL_GROSSOUT_CHANCE = 0.35
KHAJIIT_GROSSOUT_DAMAGE = 1
KHAJIIT_GROSSOUT_DURATION = 3
KHAJIIT_COIN_CHANCES = [0.50, 0.30, 0.15, 0.04, 0.01]  # Chances for 1-5 entries
```

## Integration
- All three battle skills properly queue actions during battle phase
- !coin is a stream skill (usable outside battle, once per stream)
- Integration with existing turn resolution system
- Works with all existing battle mechanics (crits, level scaling, etc.)
- Scratch and hairball use standard `_queue_monster_action` helper
- Meow has custom action resolution due to unique mechanics
- !coin integrates with raffle system to grant entries
