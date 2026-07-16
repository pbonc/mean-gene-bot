import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import storage_audit


class StorageAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "data" / "music_cache").mkdir(parents=True)
        (self.root / "data" / "backups").mkdir(parents=True)
        (self.root / "logs").mkdir()
        (self.root / "bot" / "overlay_static" / "gifs").mkdir(parents=True)
        (self.root / "overlay_static").mkdir()
        self.root_patch = patch.object(storage_audit, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp_dir.cleanup()

    def test_music_cache_uses_exact_numbered_catalog_filename(self):
        playlist = [{"number": 7, "title": "Test Song", "artist": "Test"}]
        (self.root / "data" / "playlist_cache.json").write_text(json.dumps(playlist), encoding="utf-8")
        cache = self.root / "data" / "music_cache"
        (cache / "007_Test_Song.mp3").write_bytes(b"active")
        (cache / "007_Old_Title.mp3").write_bytes(b"review")
        (cache / "yt_123_Request.mp3").write_bytes(b"request")
        (cache / "mystery.mp3").write_bytes(b"unknown")

        result = storage_audit.audit_music_cache()

        self.assertEqual(result["categories"]["exact_catalog_match"]["files"], 1)
        self.assertEqual(result["categories"]["catalog_number_title_or_format_mismatch"]["files"], 1)
        self.assertEqual(result["categories"]["youtube_request_or_transient"]["files"], 1)
        self.assertEqual(result["categories"]["unclassified_review_required"]["files"], 1)

    def test_static_duplicate_requires_identical_content(self):
        canonical = self.root / "bot" / "overlay_static" / "gifs"
        suspected = self.root / "overlay_static"
        (canonical / "same.gif").write_bytes(b"same")
        (suspected / "same.gif").write_bytes(b"same")
        (canonical / "different.gif").write_bytes(b"aaaa")
        (suspected / "different.gif").write_bytes(b"bbbb")

        result = storage_audit.audit_static_duplicates()

        self.assertEqual(result["identical_files"], 1)
        self.assertEqual(result["reclaimable_bytes"], 4)

    def test_report_is_read_only_and_totals_only_high_confidence_items(self):
        (self.root / "data" / "playlist_cache.json").write_text("[]", encoding="utf-8")
        canonical = self.root / "bot" / "overlay_static" / "gifs" / "same.gif"
        suspected = self.root / "overlay_static" / "same.gif"
        canonical.write_bytes(b"1234")
        suspected.write_bytes(b"1234")

        report = storage_audit.build_report(retain_days=30, retain_count=20)

        self.assertEqual(report["mode"], "read-only")
        self.assertEqual(report["high_confidence_reclaimable_bytes"], 4)


if __name__ == "__main__":
    unittest.main()
