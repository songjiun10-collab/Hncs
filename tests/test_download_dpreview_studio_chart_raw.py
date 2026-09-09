"""tools/download_dpreview_studio_chart_raw.py - unit test for the pure
download-completion poller (`_wait_for_download`), isolated from the real
~/Downloads folder and the opencli/browser dependency (no network, runs
under default python3). `download_manifest()` itself needs a real opencli
Browser Bridge session and is exercised manually per-brand (see
hybrid_engine/EVALUATION.md's dpreview RAW re-download entries), not here
(tests/CLAUDE.md: CI has no network/browser access)."""
import os
import hashlib
import tempfile
import threading
import time
import unittest
from unittest import mock

import tools.download_dpreview_studio_chart_raw as m


class TestWaitForDownload(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_downloads = m.DOWNLOADS
        m.DOWNLOADS = self._tmpdir

    def tearDown(self):
        m.DOWNLOADS = self._orig_downloads

    def test_returns_path_once_final_file_exists(self):
        dest = os.path.join(self._tmpdir, "x.dng")
        with open(dest, "wb") as f:
            f.write(b"data")
        found = m._wait_for_download("x.dng", timeout_s=5, poll_s=0.05)
        self.assertEqual(found, dest)

    def test_waits_out_crdownload_before_returning(self):
        fname = "y.dng"
        dest = os.path.join(self._tmpdir, fname)
        partial = dest + ".crdownload"
        with open(partial, "wb") as f:
            f.write(b"partial")

        def finish_after_delay():
            time.sleep(0.15)
            os.remove(partial)
            with open(dest, "wb") as f:
                f.write(b"data")

        threading.Thread(target=finish_after_delay).start()
        found = m._wait_for_download(fname, timeout_s=5, poll_s=0.05)
        self.assertEqual(found, dest)

    def test_times_out_when_never_downloaded(self):
        found = m._wait_for_download("never.dng", timeout_s=0.2, poll_s=0.05)
        self.assertIsNone(found)


class TestDownloadManifest(unittest.TestCase):
    def test_opencli_failure_does_not_adopt_stale_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = os.path.join(tmp, "downloads")
            raw_dir = os.path.join(tmp, "raw")
            os.makedirs(downloads)
            stale = os.path.join(downloads, "hash.cr3")
            with open(stale, "wb") as handle:
                handle.write(b"stale")
            manifest = os.path.join(tmp, "manifest.csv")
            with open(manifest, "w", newline="", encoding="utf-8") as handle:
                handle.write("raw_file_url\nhttps://example.test/hash.cr3\n")

            with mock.patch.object(m, "DOWNLOADS", downloads), mock.patch.object(
                m.subprocess,
                "run",
                return_value=mock.Mock(returncode=1, stderr="challenge"),
            ):
                ok, failed = m.download_manifest(manifest, raw_dir, timeout_s=0.01)
            quarantined = [name for name in os.listdir(downloads)
                           if name.startswith("hash.cr3.hncs-stale")]

        self.assertEqual(ok, [])
        self.assertEqual(failed, ["hash.cr3"])
        self.assertFalse(os.path.exists(os.path.join(raw_dir, "hash.cr3")))
        self.assertEqual(len(quarantined), 1)

    def test_opencli_timeout_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = os.path.join(tmp, "downloads")
            os.makedirs(downloads)
            manifest = os.path.join(tmp, "manifest.csv")
            with open(manifest, "w", newline="", encoding="utf-8") as handle:
                handle.write("raw_file_url\nhttps://example.test/hash.cr3\n")

            with mock.patch.object(m, "DOWNLOADS", downloads), mock.patch.object(
                m.subprocess,
                "run",
                side_effect=m.subprocess.TimeoutExpired("opencli", 0.01),
            ):
                ok, failed = m.download_manifest(manifest, os.path.join(tmp, "raw"), timeout_s=0.01)

        self.assertEqual(ok, [])
        self.assertEqual(failed, ["hash.cr3"])

    def test_existing_raw_is_not_skipped_without_manifest_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloads = os.path.join(tmp, "downloads")
            raw_dir = os.path.join(tmp, "raw")
            os.makedirs(downloads)
            os.makedirs(raw_dir)
            with open(os.path.join(raw_dir, "hash.cr3"), "wb") as handle:
                handle.write(b"unverified")
            manifest = os.path.join(tmp, "manifest.csv")
            with open(manifest, "w", newline="", encoding="utf-8") as handle:
                handle.write("raw_file_url\nhttps://example.test/hash.cr3\n")

            with mock.patch.object(m, "DOWNLOADS", downloads), mock.patch.object(
                m.subprocess,
                "run",
                return_value=mock.Mock(returncode=1, stderr="challenge"),
            ):
                ok, failed = m.download_manifest(manifest, raw_dir, timeout_s=0.01)

        self.assertEqual(ok, [])
        self.assertEqual(failed, ["hash.cr3"])

    def test_matching_manifest_checksum_allows_existing_raw(self):
        payload = b"verified"
        checksum = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            downloads = os.path.join(tmp, "downloads")
            raw_dir = os.path.join(tmp, "raw")
            os.makedirs(downloads)
            os.makedirs(raw_dir)
            with open(os.path.join(raw_dir, "hash.cr3"), "wb") as handle:
                handle.write(payload)
            manifest = os.path.join(tmp, "manifest.csv")
            with open(manifest, "w", newline="", encoding="utf-8") as handle:
                handle.write(f"raw_file_url,sha256\nhttps://example.test/hash.cr3,{checksum}\n")

            with mock.patch.object(m, "DOWNLOADS", downloads), mock.patch.object(
                m.subprocess, "run"
            ) as run:
                ok, failed = m.download_manifest(manifest, raw_dir, timeout_s=0.01)

        self.assertEqual(ok, ["hash.cr3"])
        self.assertEqual(failed, [])
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
