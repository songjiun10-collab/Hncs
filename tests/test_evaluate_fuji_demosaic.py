import csv
import os
import tempfile
import unittest

from tools.evaluate_fuji_demosaic import load_pairs

_FIELDS = ["camera", "datetime", "film_mode", "raw_path", "jpeg_path"]


class TestLoadPairs(unittest.TestCase):
    def _write_manifest(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def test_parses_all_fields(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T3",
            "datetime": "2018:10:06 15:56:45",
            "film_mode": "F0/Standard (Provia)",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T3/jpeg/DSCF3954.jpg",
        }])
        pairs = load_pairs(manifest_path=path)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["camera"], "Fujifilm X-T3")
        self.assertEqual(pairs[0]["datetime"], "2018:10:06 15:56:45")
        self.assertEqual(pairs[0]["film_mode"], "F0/Standard (Provia)")

    def test_raw_and_jpeg_paths_are_absolute(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T30", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T30/jpeg/DSCF7030.JPG",
        }])
        pairs = load_pairs(manifest_path=path)
        self.assertTrue(os.path.isabs(pairs[0]["raw_path"]))
        self.assertTrue(os.path.isabs(pairs[0]["jpeg_path"]))
        self.assertTrue(pairs[0]["raw_path"].endswith(
            "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF"))

    def test_multiple_rows_preserve_csv_order(self):
        path = self._write_manifest([
            {"camera": "A", "datetime": "t1", "film_mode": "m1",
             "raw_path": "r1.RAF", "jpeg_path": "j1.jpg"},
            {"camera": "B", "datetime": "t2", "film_mode": "m2",
             "raw_path": "r2.RAF", "jpeg_path": "j2.jpg"},
        ])
        pairs = load_pairs(manifest_path=path)
        self.assertEqual([p["camera"] for p in pairs], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
