from pathlib import Path
lines = Path('bot/grid_state.py').read_text().splitlines()
with Path('grid_state_numbered.txt').open('w', encoding='utf-8') as fh:
    for idx, line in enumerate(lines, start=1):
        fh.write(f"{idx}: {line}\n")
