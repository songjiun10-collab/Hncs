"""tools/match_dpreview_downloads_by_hash.py, tools/write_dpreview_manifest.py -
import smoke test + unit test for the pure logic (SHA-256 matching, CSV
writing), no network/browser dependency so this runs in CI."""
import csv
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from tools import match_dpreview_downloads_by_hash as match_mod
from tools import write_dpreview_manifest as manifest_mod


class TestMatchByHash(unittest.TestCase):
    def test_matches_by_content_hash_ignoring_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = os.path.join(tmp, "Downloads")
            dest = os.path.join(tmp, "raw")
            os.makedirs(downloads)
            match_mod.DOWNLOADS = downloads

            content = b"fake raw bytes"
            anon_path = os.path.join(downloads, ".Q6L2SF6YDW.com.anthropic.claudefordesktop.abc123")
            with open(anon_path, "wb") as f:
                f.write(content)

            digest = hashlib.sha256(content).hexdigest()
            hashes = [{"id": 999, "hash": digest, "size": len(content)}]

            matched, missing = match_mod.match_and_copy(hashes, "test", dest, cutoff_mtime=0)

            self.assertEqual(matched, [999])
            self.assertEqual(missing, [])
            self.assertTrue(os.path.exists(os.path.join(dest, "test_999.dng")))
            self.assertFalse(os.path.exists(anon_path))

    def test_reports_missing_id_when_hash_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = os.path.join(tmp, "Downloads")
            dest = os.path.join(tmp, "raw")
            os.makedirs(downloads)
            match_mod.DOWNLOADS = downloads

            hashes = [{"id": 1, "hash": "0" * 64, "size": 10}]
            matched, missing = match_mod.match_and_copy(hashes, "test", dest, cutoff_mtime=0)

            self.assertEqual(matched, [])
            self.assertEqual(missing, [1])


class TestWriteManifest(unittest.TestCase):
    def test_writes_csv_and_deletes_raw_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest_mod.REPO_ROOT = tmp
            rel_dir = "datasets/fakebrand/contributed/fake-chart"
            full_dir = os.path.join(tmp, rel_dir)
            raw_dir = os.path.join(full_dir, "raw")
            os.makedirs(raw_dir)
            with open(os.path.join(raw_dir, "a.dng"), "wb") as f:
                f.write(b"x")

            images = [{"id": 42, "url": "https://example.com/42.dng"}]
            manifest_mod.write_manifest_and_clean(rel_dir, "Fake Camera", 12345, images)

            self.assertFalse(os.path.exists(raw_dir))
            manifest_path = os.path.join(full_dir, "manifest.csv")
            with open(manifest_path, newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], ["image_id", "camera", "product_id", "raw_file_url", "notes"])
            self.assertEqual(rows[1][:4], ["42", "Fake Camera", "12345", "https://example.com/42.dng"])


if __name__ == "__main__":
    unittest.main()
