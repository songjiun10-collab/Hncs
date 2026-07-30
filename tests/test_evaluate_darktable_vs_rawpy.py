import csv
import os
import tempfile
import unittest

import numpy as np

from tools.evaluate_darktable_vs_rawpy import _resize_max_dim, load_fuji_pairs

_FIELDS = ["camera", "datetime", "film_mode", "raw_path", "jpeg_path"]


class TestLoadFujiPairs(unittest.TestCase):
    def _write_manifest(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def test_parses_camera_and_paths(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T3", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T3/jpeg/DSCF3954.jpg",
        }])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["camera"], "Fujifilm X-T3")
        self.assertEqual(pairs[0]["name"], "DSCF3954.RAF")

    def test_paths_are_absolute(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T30", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T30/jpeg/DSCF7030.JPG",
        }])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertTrue(os.path.isabs(pairs[0]["raw_path"]))
        self.assertTrue(os.path.isabs(pairs[0]["jpeg_path"]))

    def test_multiple_rows_preserve_order(self):
        path = self._write_manifest([
            {"camera": "A", "datetime": "t1", "film_mode": "m1",
             "raw_path": "r1.RAF", "jpeg_path": "j1.jpg"},
            {"camera": "B", "datetime": "t2", "film_mode": "m2",
             "raw_path": "r2.RAF", "jpeg_path": "j2.jpg"},
        ])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertEqual([p["camera"] for p in pairs], ["A", "B"])


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(2000, 4000, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertLessEqual(max(out.shape[:2]), 1024)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 4000 / 2000, places=1)

    def test_preserves_channel_count(self):
        img = np.random.default_rng(2).uniform(0, 1, size=(1200, 600, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape[2], 3)


if __name__ == "__main__":
    unittest.main()
