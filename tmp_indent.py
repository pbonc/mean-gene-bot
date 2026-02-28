from pathlib import Path
lines=Path('bot/commands/rpg_cog.py').read_bytes().decode('utf-8').splitlines()
for i in range(2650, 2780):
    print(i+1, repr(lines[i]))
