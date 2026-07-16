"""Read-only storage and cleanup audit for Mean Gene Bot."""

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO_EXTENSIONS = {".mp3", ".mp4", ".webm", ".m4a", ".opus", ".ogg", ".wav"}


def size_bytes(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def human_size(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_title(title: str) -> str:
    cleaned = "".join(char for char in title if char.isalnum() or char in (" ", "-", "_"))
    return cleaned.rstrip().replace(" ", "_")


def audit_music_cache() -> dict:
    cache_dir = ROOT / "data" / "music_cache"
    playlist_path = ROOT / "data" / "playlist_cache.json"
    playlist = json.loads(playlist_path.read_text(encoding="utf-8")) if playlist_path.exists() else []
    catalog = {int(song["number"]): song for song in playlist if song.get("number") is not None}
    expected = {
        f"{number:03d}_{safe_title(str(song.get('title', 'Unknown')))}.mp3".lower()
        for number, song in catalog.items()
    }

    categories = Counter()
    category_bytes = Counter()
    audio_files = []
    number_pattern = re.compile(r"^(\d+)_")
    for path in cache_dir.iterdir() if cache_dir.exists() else []:
        if not path.is_file() or path.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        audio_files.append(path)
        lower_name = path.name.lower()
        match = number_pattern.match(path.stem)
        if lower_name in expected:
            category = "exact_catalog_match"
        elif match and int(match.group(1)) in catalog:
            category = "catalog_number_title_or_format_mismatch"
        elif lower_name.startswith("yt_"):
            category = "youtube_request_or_transient"
        else:
            category = "unclassified_review_required"
        categories[category] += 1
        category_bytes[category] += path.stat().st_size

    return {
        "path": str(cache_dir.relative_to(ROOT)),
        "files": len(audio_files),
        "bytes": sum(path.stat().st_size for path in audio_files),
        "catalog_entries": len(catalog),
        "categories": {
            name: {"files": count, "bytes": category_bytes[name]}
            for name, count in sorted(categories.items())
        },
        "note": "Only exact catalog matches are proven active. Other categories are review candidates, not safe deletions.",
    }


def audit_static_duplicates() -> dict:
    canonical = ROOT / "bot" / "overlay_static" / "gifs"
    suspected = ROOT / "overlay_static"
    duplicates = []
    for path in suspected.iterdir() if suspected.exists() else []:
        counterpart = canonical / path.name
        if not path.is_file() or not counterpart.is_file() or path.stat().st_size != counterpart.stat().st_size:
            continue
        if sha256(path) == sha256(counterpart):
            duplicates.append({"name": path.name, "bytes": path.stat().st_size})
    return {
        "suspected_redundant_root": str(suspected.relative_to(ROOT)),
        "canonical_runtime_root": str(canonical.relative_to(ROOT)),
        "identical_files": len(duplicates),
        "reclaimable_bytes": sum(item["bytes"] for item in duplicates),
        "files": sorted(duplicates, key=lambda item: item["bytes"], reverse=True),
        "confidence": "high after external OBS/browser-source references are checked",
    }


def audit_backups(retain_days: int, retain_count: int) -> dict:
    backup_dir = ROOT / "data" / "backups"
    files = sorted(
        (path for path in backup_dir.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ) if backup_dir.exists() else []
    cutoff = datetime.now(timezone.utc) - timedelta(days=retain_days)
    candidates = []
    for index, path in enumerate(files):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if index >= retain_count and modified < cutoff:
            candidates.append(path)
    return {
        "path": str(backup_dir.relative_to(ROOT)),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "policy_preview": {"retain_days": retain_days, "retain_count_minimum": retain_count},
        "candidate_files": len(candidates),
        "candidate_bytes": sum(path.stat().st_size for path in candidates),
        "confidence": "medium; validate restore requirements before applying retention",
    }


def audit_logs() -> dict:
    log_dir = ROOT / "logs"
    files = [path for path in log_dir.iterdir() if path.is_file()] if log_dir.exists() else []
    telemetry = log_dir / "telemetry.jsonl"
    return {
        "path": str(log_dir.relative_to(ROOT)),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "telemetry_bytes": telemetry.stat().st_size if telemetry.exists() else 0,
        "telemetry_rotation_configured": False,
    }


def audit_artifacts() -> dict:
    pycache_files = [path for path in ROOT.rglob("*.pyc") if ".venv" not in path.parts and ".git" not in path.parts]
    temp_files = [path for path in ROOT.iterdir() if path.is_file() and (path.name.startswith("tmp_") or path.name == "temp_fix.txt")]
    return {
        "pyc_files": len(pycache_files),
        "pyc_bytes": sum(path.stat().st_size for path in pycache_files),
        "root_temp_files": len(temp_files),
        "root_temp_bytes": sum(path.stat().st_size for path in temp_files),
        "confidence": "high for generated bytecode; manual review required for temporary source/text files",
    }


def build_report(retain_days: int, retain_count: int) -> dict:
    sections = {
        "music_cache": audit_music_cache(),
        "static_duplicates": audit_static_duplicates(),
        "backups": audit_backups(retain_days, retain_count),
        "logs": audit_logs(),
        "artifacts": audit_artifacts(),
    }
    high_confidence = sections["static_duplicates"]["reclaimable_bytes"] + sections["artifacts"]["pyc_bytes"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only",
        "sections": sections,
        "high_confidence_reclaimable_bytes": high_confidence,
    }


def print_report(report: dict) -> None:
    sections = report["sections"]
    music = sections["music_cache"]
    print("MGB STORAGE AUDIT (READ-ONLY)")
    print(f"Music cache: {music['files']} files, {human_size(music['bytes'])}, {music['catalog_entries']} catalog entries")
    for name, data in music["categories"].items():
        print(f"  {name}: {data['files']} files, {human_size(data['bytes'])}")
    duplicate = sections["static_duplicates"]
    print(f"Static duplicates: {duplicate['identical_files']} files, {human_size(duplicate['reclaimable_bytes'])}")
    backups = sections["backups"]
    print(f"Backups: {backups['files']} files, {human_size(backups['bytes'])}")
    print(f"  retention candidates: {backups['candidate_files']} files, {human_size(backups['candidate_bytes'])}")
    logs = sections["logs"]
    print(f"Logs: {logs['files']} files, {human_size(logs['bytes'])}; telemetry {human_size(logs['telemetry_bytes'])}")
    artifacts = sections["artifacts"]
    print(f"Generated bytecode: {artifacts['pyc_files']} files, {human_size(artifacts['pyc_bytes'])}")
    print(f"Root temporary files: {artifacts['root_temp_files']} files, {human_size(artifacts['root_temp_bytes'])}")
    print(f"High-confidence reclaimable preview: {human_size(report['high_confidence_reclaimable_bytes'])}")
    print("No files were changed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--retain-backup-days", type=int, default=30)
    parser.add_argument("--retain-backup-count", type=int, default=20)
    args = parser.parse_args()
    if args.retain_backup_days < 0 or args.retain_backup_count < 0:
        parser.error("retention values cannot be negative")
    report = build_report(args.retain_backup_days, args.retain_backup_count)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
