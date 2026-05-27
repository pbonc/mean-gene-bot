import csv
import json
import os
from pathlib import Path

def main(csv_path: Path, out_path: Path) -> None:
    rows = []
    with csv_path.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    inventory = []
    for row in rows:
        name = row.get("name") or row.get("description")
        tier = int(row.get("tier", 1))
        flair = row.get("flair") or "common"
        description = row.get("description") or name
        count = int(row.get("count", 1))
        for _ in range(count):
            inventory.append({
                "name": name,
                "tier": tier,
                "flair": flair,
                "description": description,
            })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(inventory, fh, indent=2)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert a prize CSV to grid inventory JSON.")
    parser.add_argument("csv", type=Path, help="CSV file containing prize definitions")
    parser.add_argument("--out", type=Path, default=Path("data/grid_inventory.json"), help="output JSON file")
    args = parser.parse_args()
    main(args.csv, args.out)
