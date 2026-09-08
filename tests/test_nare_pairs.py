import unittest
import json
import tempfile
from unittest.mock import patch

from hybrid_engine.evaluation.nare_pairs import find_strict_pairs
from hybrid_engine.evaluation.nare_pairs_cli import main


def tags(timestamp, make="FUJIFILM", model="X-T100", iso=200):
    return {"DateTimeOriginal": timestamp, "Make": make, "Model": model,
            "ISO": iso, "FileName": "ignored"}


class TestFindStrictPairs(unittest.TestCase):
    def test_accepts_only_exact_capture_metadata_match(self):
        raw = ["/samples/raw/DSCF0138.RAF", "/samples/raw/DSCF9976.RAF"]
        jpeg = ["/samples/jpeg/DSCF0138.JPG", "/samples/jpeg/DSCF9977.JPG"]
        metadata = {
            raw[0]: tags("2018:08:19 22:16:43"),
            jpeg[0]: tags("2018:08:19 22:16:43"),
            raw[1]: tags("2018:08:17 10:17:00", iso=6400),
            jpeg[1]: tags("2018:08:17 10:17:07", iso=12800),
        }
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif",
                   side_effect=lambda path: metadata[path]):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [{"raw_path": raw[0], "jpeg_path": jpeg[0]}])
        self.assertEqual(report["unmatched_raw"], [raw[1]])
        self.assertEqual(report["unmatched_jpeg"], [jpeg[1]])

    def test_rejects_ambiguous_duplicate_capture_key(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG", "/samples/jpeg/a-copy.JPG"]
        metadata = {path: tags("2018:08:19 22:16:43") for path in raw + jpeg}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif",
                   side_effect=lambda path: metadata[path]):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [])
        self.assertEqual(report["ambiguous_keys"], [{
            "key": ["2018:08:19 22:16:43", "fujifilm", "x-t100", "200"],
            "raw_count": 1, "jpeg_count": 2,
        }])

    def test_rejects_missing_required_exif(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG"]
        metadata = {raw[0]: tags("2018:08:19 22:16:43"), jpeg[0]: {}}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif",
                   side_effect=lambda path: metadata[path]):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [])
        self.assertEqual(report["invalid_jpeg"], [jpeg[0]])


class TestNAREPairsCLI(unittest.TestCase):
    def test_writes_machine_readable_preflight_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir, jpeg_dir = f"{tmp}/raw", f"{tmp}/jpeg"
            import os
            os.makedirs(raw_dir); os.makedirs(jpeg_dir)
            output = f"{tmp}/report.json"
            report = {"raw_input_count": 1, "jpeg_input_count": 1, "pairs": [],
                      "unmatched_raw": ["a.RAF"], "unmatched_jpeg": ["a.JPG"],
                      "invalid_raw": [], "invalid_jpeg": [], "ambiguous_keys": []}
            with patch("hybrid_engine.evaluation.nare_pairs_cli.scan_pair_directories",
                       return_value=report):
                with self.assertRaises(SystemExit) as stopped:
                    main([raw_dir, jpeg_dir, "--output", output])
            self.assertEqual(stopped.exception.code, 2)
            with open(output, encoding="utf-8") as f:
                self.assertEqual(json.load(f), report)


if __name__ == "__main__":
    unittest.main()
