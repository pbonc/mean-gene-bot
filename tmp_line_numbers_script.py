from pathlib import Path

lines = Path("bot/commands/grid_cog.py").read_text().splitlines()
notes = []
for idx, line in enumerate(lines, start=1):
    if "USAGE =" in line:
        notes.append(f"USAGE {idx}")
    if "elif action == \"add\"" in line:
        notes.append(f"ELIF_ADD {idx}")
    if "async def _handle_add" in line:
        notes.append(f"HANDLE_ADD {idx}")
    if "await self._handle_add" in line:
        notes.append(f"CALL_ADD {idx}")

Path("line_numbers_out.txt").write_text("\n".join(notes))
