"""tools/download_dpreview_studio_chart_raw.py - unit test for the pure
download-completion poller (`_wait_for_download`), isolated from the real
~/Downloads folder and the opencli/browser dependency (no network, runs
under default python3). `download_manifest()` itself needs a real opencli
Browser Bridge session and is exercised manually per-brand (see
hybrid_engine/EVALUATION.md's dpreview RAW re-download entries), not here
(tests/CLAUDE.md: CI has no network/browser access)."""
import os
import tempfile
import threading
import time
import unittest

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


if __name__ == "__main__":
    unittest.main()
