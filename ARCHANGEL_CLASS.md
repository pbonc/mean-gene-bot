# Archangel Custom Class

## Overview
Custom class designed exclusively for player **karnave**. The Archangel is a divine warrior that builds power through prayer and combat, then unleashes devastating holy abilities.

## Auto-Assignment
- **Player**: karnave
- **Class Name**: Archangel  
- **Tier**: 1
- **Base Class**: Archangel
- Automatically assigned on first embark and maintained throughout the game

## Power Meter System
- Archangel has a power meter that starts at **0** at the beginning of each battle
- Power is gained through **!pray** (+2) and **!touch** (+1)
- Power is consumed by **!expel** and **!judgement** (resets to 0 after use)
- Power persists between turns within a battle but **resets to 0** when joining a new battle

## Battle Skills

### 1. **!pray** (Power Gain + Self Heal)
- **Power Gain**: +2
- **Self Heal**: 3 HP (base, does not scale)
- **Usage**: `!pray`
- **Description**: Channel divine energy to gain power and heal yourself
- **Strategy**: Primary power-building ability with sustain

### 2. **!touch** (Damage + Power Gain)
- **Damage**: 3 base damage (scales with level)
- **Power Gain**: +1
- **Usage**: `!touch [monster_number]`
- **Description**: Strike an enemy with holy energy while building power
- **Strategy**: Offensive power-building option - deals damage while preparing for finishers

### 3. **!expel** (AoE Damage + Party Heal + Power Reset)
- **AoE Damage**: `(level) × (power)` to **all enemies**
- **Party Heal**: `(level) × (power ÷ 2)` to **all alive party members**
- **Power Cost**: Consumes ALL power (resets to 0)
- **Usage**: `!expel`
- **Requirements**: Power must be > 0
- **Description**: Expel dark forces, damaging all enemies and healing all allies
- **Strategy**: Powerful AoE option that benefits the entire team
- **Example**: Level 5 Archangel with 6 power = 30 damage to all enemies + 15 HP healed to party

### 4. **!judgement** (Massive Single-Target Damage + Power Reset)
- **Damage**: `(level) × (power) × 5` to **one target**
- **Power Cost**: Consumes ALL power (resets to 0)
- **Usage**: `!judgement [monster_number]`
- **Requirements**: Power must be > 0
- **Description**: Pass divine judgement on a single enemy with overwhelming damage
- **Strategy**: Maximum single-target burst damage - excellent for boss fights
- **Example**: Level 5 Archangel with 6 power = 150 damage to one enemy

## Strategy Guide

### Power Building
- **Conservative**: Use !pray to build +2 power per turn while healing
- **Aggressive**: Use !touch to deal damage while building +1 power per turn
- **Balanced**: Alternate between pray and touch based on HP needs

### Power Spending
- **!expel** is better when:
  - Facing multiple enemies
  - Party needs healing
  - Power × Level is moderate (e.g., 4-8 power at mid-levels)
  
- **!judgement** is better when:
  - Facing a single high-HP boss
  - You've built up high power (8+)
  - Need to eliminate a priority target

### Example Build Sequence
1. Turn 1: !pray → Power: 2, Heal: 3 HP
2. Turn 2: !touch → Power: 3, Deal: 3+ damage
3. Turn 3: !pray → Power: 5, Heal: 3 HP
4. Turn 4: !judgement → Deal: (level × 5 × 5) damage, Power: 0
   - At level 5: 125 damage to target!

## Damage Scaling

| Level | Pray Heal | Touch Base | Expel (6 power) | Judgement (6 power) |
|-------|-----------|------------|-----------------|---------------------|
| 1     | 3 HP      | 3 dmg      | 6 AoE / 3 heal  | 30 dmg single       |
| 3     | 3 HP      | 5 dmg      | 18 AoE / 9 heal | 90 dmg single       |
| 5     | 3 HP      | 7 dmg      | 30 AoE / 15 heal| 150 dmg single      |
| 7     | 3 HP      | 9 dmg      | 42 AoE / 21 heal| 210 dmg single      |
| 10    | 3 HP      | 12 dmg     | 60 AoE / 30 heal| 300 dmg single      |

*Note: Touch damage scales with level like other skills (+1 per level)*

## Constants Added
```python
ARCHANGEL_NAME = "karnave"
ARCHANGEL_PRAY_POWER_GAIN = 2
ARCHANGEL_PRAY_HEAL = 3
ARCHANGEL_TOUCH_POWER_GAIN = 1
ARCHANGEL_TOUCH_BASE_DAMAGE = 3
```

## Integration
- Power meter tracked via `archangel_power` user field
- Resets to 0 when joining a battle (!join)
- All skills properly queue actions during battle phase
- Works with existing turn resolution, crit chance, level scaling
- Expel/Judgement check for power > 0 before queuing
