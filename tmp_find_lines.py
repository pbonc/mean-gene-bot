from pathlib import Path
text = Path("data/rpg_state.json").read_text().splitlines()
found = False
for idx, line in enumerate(text, 1):
    if '"karnave": {' in line:
        found = True
    if found and '"hp_current"' in line:
        print('hp_current', idx, line.strip())
        break
found = False
for idx, line in enumerate(text, 1):
    if '"karnave": {' in line:
        found = True
    if found and '"hp_max"' in line:
        print('hp_max', idx, line.strip())
        break
found = False
for idx, line in enumerate(text, 1):
    if '"karnave": {' in line:
        found = True
    if found and '"player_level"' in line:
        print('player_level', idx, line.strip())
        break
