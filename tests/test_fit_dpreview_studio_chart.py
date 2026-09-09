"""tools/fit_dpreview_studio_chart.py - unit test for the pure ΔE00 helper
(no RAW/cv2 dependency, runs under default python3) plus an import smoke
test. Mirrors tests/test_validate_dpreview_chart_brand.py's scope - the
actual fit_and_issue() path needs real RAW decode + DCP/ICC writers and
is exercised manually per-brand (see hybrid_engine/EVALUATION.md's
"dpreview 스튜디오씬 챠트 - 7브랜드 DCP/ICC 발급" entry), not here
(tests/CLAUDE.md: never commit a test that needs raw_calib_cache/
contributed datasets - they're git-ignored and absent in CI)."""
import unittest
import json
import os
import tempfile

import numpy as np

from tools.fit_dpreview_studio_chart import _mean_de, _validate_issuance_inputs, fit_and_issue


class TestMeanDe(unittest.TestCase):
    def test_zero_for_identical_patches(self):
        ref = np.tile(np.array([50.0, 60.0, 40.0]), (24, 1))
        self.assertAlmostEqual(_mean_de(ref, ref), 0.0, places=6)

    def test_positive_for_differing_patches(self):
        ref = np.tile(np.array([50.0, 60.0, 40.0]), (24, 1))
        samples = ref + 10.0
        self.assertGreater(_mean_de(samples, ref), 0.0)


class TestValidateIssuanceInputs(unittest.TestCase):
    def test_rejects_exif_display_name_as_dcp_camera_model(self):
        with self.assertRaisesRegex(ValueError, "UniqueCameraModel"):
            fit_and_issue("/does/not/matter", "demo", "Demo Camera", "raw")

    def test_requires_matching_validation_report_and_sample_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = os.path.join(tmp, "raw")
            os.makedirs(raw_dir)
            report_path = os.path.join(tmp, "chart_validation_report.json")
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump({
                    "brand": "demo",
                    "camera": "Demo Camera",
                    "n_images": 2,
                    "images": ["a.raw", "b.raw"],
                }, handle)

            self.assertIsNone(_validate_issuance_inputs(
                raw_dir, "demo", "Demo Camera", ["a.raw", "b.raw"]
            ))

            with self.assertRaisesRegex(ValueError, "표본 불일치"):
                _validate_issuance_inputs(raw_dir, "demo", "Demo Camera", ["a.raw"])

    def test_rejects_missing_validation_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = os.path.join(tmp, "raw")
            os.makedirs(raw_dir)
            with self.assertRaisesRegex(FileNotFoundError, "chart_validation_report.json"):
                _validate_issuance_inputs(raw_dir, "demo", "Demo Camera", ["a.raw"])


if __name__ == "__main__":
    unittest.main()
