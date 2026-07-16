from pathlib import Path
lines = Path('bot/grid_state.py').read_text().splitlines()
out = []
for idx, line in enumerate(lines, start=1):
    if 'def _sanitize_description' in line:
        out.append(f'SANITIZE {idx}')
    if 'description = _sanitize_description' in line:
        out.append(f'USE {idx}')
Path('lineinfo.txt').write_text('\n'.join(out))
