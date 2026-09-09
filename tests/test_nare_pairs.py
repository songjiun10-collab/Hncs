import unittest
import json
import tempfile
from unittest.mock import patch

from hybrid_engine.evaluation.nare_pairs import build_nare_manifest, find_strict_pairs
from hybrid_engine.evaluation.nare_pairs_cli import main


def tags(timestamp, make="FUJIFILM", model="X-T100", iso=200, software=None):
    record = {"DateTimeOriginal": timestamp, "Make": make, "Model": model,
              "ISO": iso, "FileName": "ignored"}
    if software is not None:
        record["Software"] = software
    return record


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
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [{"raw_path": raw[0], "jpeg_path": jpeg[0]}])
        self.assertEqual(report["unmatched_raw"], [raw[1]])
        self.assertEqual(report["unmatched_jpeg"], [jpeg[1]])

    def test_rejects_ambiguous_duplicate_capture_key(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG", "/samples/jpeg/a-copy.JPG"]
        metadata = {path: tags("2018:08:19 22:16:43") for path in raw + jpeg}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
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
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [])
        self.assertEqual(report["invalid_jpeg"], [jpeg[0]])

    def test_rejects_jpeg_rendered_by_dcraw(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG"]
        metadata = {raw[0]: tags("2018:08:19 22:16:43"),
                    jpeg[0]: tags("2018:08:19 22:16:43", software="dcraw 9.28")}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [])
        self.assertEqual(report["invalid_jpeg"], jpeg)

    def test_rejects_jpeg_rendered_by_rawpy(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG"]
        metadata = {raw[0]: tags("2018:08:19 22:16:43"),
                    jpeg[0]: tags("2018:08:19 22:16:43", software="rawpy 0.19.0")}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [])
        self.assertEqual(report["invalid_jpeg"], jpeg)

    def test_rejects_jpeg_rendered_by_common_editors(self):
        for software in ("Adobe Photoshop 26.0", "Adobe Lightroom Classic"):
            with self.subTest(software=software):
                raw = ["/samples/raw/a.RAF"]
                jpeg = ["/samples/jpeg/a.JPG"]
                metadata = {raw[0]: tags("2018:08:19 22:16:43"),
                            jpeg[0]: tags("2018:08:19 22:16:43", software=software)}
                with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                           return_value=metadata):
                    report = find_strict_pairs(raw, jpeg)
                self.assertEqual(report["pairs"], [])
                self.assertEqual(report["invalid_jpeg"], jpeg)

    def test_editor_software_match_is_case_insensitive_and_trimmed(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG"]
        metadata = {raw[0]: tags("2018:08:19 22:16:43"),
                    jpeg[0]: tags("2018:08:19 22:16:43", software="  RAWPY 1.0 ")}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["invalid_jpeg"], jpeg)

    def test_accepts_camera_jpeg_software(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG"]
        metadata = {raw[0]: tags("2018:08:19 22:16:43"),
                    jpeg[0]: tags("2018:08:19 22:16:43", software="FUJIFILM X-T100")}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["pairs"], [{"raw_path": raw[0], "jpeg_path": jpeg[0]}])

    def test_rejected_render_does_not_enter_jpeg_key_map(self):
        raw = ["/samples/raw/a.RAF"]
        jpeg = ["/samples/jpeg/a.JPG"]
        metadata = {raw[0]: tags("2018:08:19 22:16:43"),
                    jpeg[0]: tags("2018:08:19 22:16:43", software="Adobe Camera Raw")}
        with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                   return_value=metadata):
            report = find_strict_pairs(raw, jpeg)
        self.assertEqual(report["unmatched_jpeg"], [])
        self.assertEqual(report["invalid_jpeg"], jpeg)
        self.assertEqual(report["ambiguous_keys"][0]["jpeg_count"], 0)


class TestBuildNAREManifest(unittest.TestCase):
    def test_preserves_capture_provenance_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, jpeg = f"{tmp}/a.RAF", f"{tmp}/a.JPG"
            with open(raw, "wb") as handle:
                handle.write(b"raw")
            with open(jpeg, "wb") as handle:
                handle.write(b"jpeg")
            metadata = {
                raw: {**tags("2025:03:21 21:41:39"), "LensModel": "GF35mmF4",
                      "ExposureTime": "1/125", "WhiteBalance": "Auto", "FilmMode": "F0/Standard (Provia)"},
                jpeg: {**tags("2025:03:21 21:41:39"), "LensModel": "GF35mmF4",
                       "ExposureTime": "1/125", "WhiteBalance": "Auto", "FilmMode": "F0/Standard (Provia)",
                       "Software": "FUJIFILM X-T100"},
            }
            with patch("hybrid_engine.evaluation.nare_pairs._read_exif_many",
                       return_value=metadata):
                rows = build_nare_manifest([{"raw_path": raw, "jpeg_path": jpeg}],
                                           contributor="dpreview", lighting="daylight",
                                           scene_type="unknown", scene_prefix="gfx")
        self.assertEqual(rows[0]["scene_id"], "gfx-000")
        self.assertEqual(rows[0]["session_id"], "capture-2025-03-21")
        self.assertEqual(rows[0]["picture_style"], "F0/Standard (Provia)")
        self.assertEqual(rows[0]["lens"], "GF35mmF4")
        self.assertEqual(rows[0]["exposure"], "1/125")
        self.assertEqual(rows[0]["white_balance"], "Auto")
        self.assertEqual(len(rows[0]["source_sha256"]), 64)
        self.assertEqual(rows[0]["jpeg_software"], "FUJIFILM X-T100")


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

    def test_optionally_writes_candidate_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir, jpeg_dir = f"{tmp}/raw", f"{tmp}/jpeg"
            import os
            os.makedirs(raw_dir); os.makedirs(jpeg_dir)
            output, manifest = f"{tmp}/report.json", f"{tmp}/manifest.json"
            report = {"raw_input_count": 1, "jpeg_input_count": 1,
                      "pairs": [{"raw_path": "a.RAF", "jpeg_path": "a.JPG"}],
                      "unmatched_raw": [], "unmatched_jpeg": [], "invalid_raw": [],
                      "invalid_jpeg": [], "ambiguous_keys": []}
            candidate = [{"scene_id": "demo-000"}]
            with patch("hybrid_engine.evaluation.nare_pairs_cli.scan_pair_directories",
                       return_value=report), \
                 patch("hybrid_engine.evaluation.nare_pairs_cli.build_nare_manifest",
                       return_value=candidate) as build:
                with self.assertRaises(SystemExit) as stopped:
                    main([raw_dir, jpeg_dir, "--output", output, "--manifest-out", manifest,
                          "--contributor", "dpreview", "--lighting", "daylight",
                          "--scene-type", "unknown", "--scene-prefix", "demo"])
            self.assertEqual(stopped.exception.code, 0)
            with open(manifest, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), candidate)
            self.assertEqual(build.call_args.kwargs["contributor"], "dpreview")


if __name__ == "__main__":
    unittest.main()
