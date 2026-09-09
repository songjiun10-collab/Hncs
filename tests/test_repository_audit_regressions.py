import contextlib
import io
import sys
import unittest
from unittest import mock

import colour
import numpy as np

from core.brand_classifier import extract_features
from hybrid_engine import convert as convert_cli
from hybrid_engine.evaluation import care
from hybrid_engine.evaluation.care import (
    compare_response,
    run_care_response,
    validate_care_record,
)
from hybrid_engine.evaluation.metrics import delta_e_by_zone, ssim_L


class TestRepositoryAuditRegressions(unittest.TestCase):
    @staticmethod
    def _brand_record(hue_mean):
        return {
            "b2": 0.0,
            "w995": 0.0,
            "median": 0.0,
            "dark_pct": 0.0,
            "sat_mean": 0.0,
            "hue_mean": hue_mean,
            "a_p1": 0.0,
            "a_p99": 0.0,
            "b_p1": 0.0,
            "b_p99": 0.0,
            "a_std": 0.0,
            "b_std": 0.0,
            "chroma_mean": 0.0,
            "chroma_p99": 0.0,
        }

    def test_brand_hue_uses_opencv_half_degree_units(self):
        features, names = extract_features([
            self._brand_record(1.0),
            self._brand_record(179.0),
        ])
        hue_columns = [names.index("hue_cos"), names.index("hue_sin")]
        distance = float(np.linalg.norm(features[0, hue_columns] - features[1, hue_columns]))

        angles = np.deg2rad([2.0, 358.0])
        expected = float(np.linalg.norm(
            np.array([np.cos(angles[0]), np.sin(angles[0])])
            - np.array([np.cos(angles[1]), np.sin(angles[1])])
        ))
        self.assertAlmostEqual(distance, expected, places=12)
        self.assertLess(distance, 0.1)

    def test_care_validator_rejects_non_string_identity_and_target(self):
        with self.assertRaises(ValueError):
            validate_care_record({
                "capture_id": None,
                "target_kind": None,
                "delta_e00": -1,
                "scene_reviewed": True,
            })

    def test_care_validator_rejects_unknown_target_kind(self):
        with self.assertRaises(ValueError):
            validate_care_record({
                "capture_id": "capture-a",
                "target_kind": "mystery",
                "delta_e00": 1.0,
                "scene_reviewed": True,
            })

    def test_care_validator_rejects_negative_target_metric(self):
        with self.assertRaises(ValueError):
            validate_care_record({
                "capture_id": "capture-a",
                "target_kind": "sooc",
                "delta_e00": -1.0,
                "scene_reviewed": True,
            })

    def test_care_validator_accepts_reviewed_sooc_metric(self):
        record = validate_care_record({
            "capture_id": "capture-a",
            "target_kind": "sooc",
            "delta_e00": 1.0,
            "scene_reviewed": True,
        })
        self.assertEqual(record["claim_level"], "targeted_response")

    def test_care_rejects_empty_images(self):
        empty = np.empty((0, 2, 3), dtype=np.float64)
        with self.assertRaises(ValueError):
            compare_response(empty, empty)

    def test_care_rejects_nonfinite_computed_metric(self):
        image = np.full((2, 2, 3), 0.5, dtype=np.float64)
        with mock.patch.object(care, "mean_delta_e", return_value=np.nan):
            with self.assertRaises(ValueError):
                compare_response(image, image)

    def test_care_identity_control_shares_preprocessing(self):
        image = np.full((2, 2, 3), 0.5001, dtype=np.float64)

        def quantize(value):
            return np.round(np.clip(value, 0.0, 1.0) * 255.0) / 255.0

        records = run_care_response(
            image,
            lambda value: value,
            preprocess=quantize,
            perturbations=[{"kind": "exposure", "ev": 0.001}],
        )
        self.assertEqual(len(records), 1)
        self.assertAlmostEqual(records[0]["response_delta_e00"], 0.0, places=12)
        self.assertAlmostEqual(records[0]["control_delta_e00"], 0.0, places=12)

    def test_convert_cli_reports_imwrite_failure_as_error(self):
        image = np.zeros((32, 32, 3), dtype=np.uint8)
        stderr = io.StringIO()
        argv = [
            "hybrid_engine.convert",
            "input.jpg",
            "missing/output.jpg",
            "--source",
            "canon",
            "--target",
            "sony",
        ]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(convert_cli.cv2, "imread", return_value=image), \
                mock.patch.object(convert_cli, "convert_between_brands", return_value=image), \
                mock.patch.object(convert_cli.cv2, "imwrite", return_value=False), \
                contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                convert_cli.main()
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("저장하지 못함", stderr.getvalue())

    def test_metrics_ignore_external_colour_domain_scale(self):
        image_a = np.full((16, 16, 3), 0.2, dtype=np.float64)
        image_b = np.full((16, 16, 3), 0.3, dtype=np.float64)

        with colour.domain_range_scale("reference"):
            reference_zones = delta_e_by_zone(image_a, image_b)
            reference_ssim = ssim_L(image_a, image_b)
        with colour.domain_range_scale("1"):
            scaled_zones = delta_e_by_zone(image_a, image_b)
            scaled_ssim = ssim_L(image_a, image_b)

        self.assertEqual(reference_zones.keys(), scaled_zones.keys())
        for name in reference_zones:
            if reference_zones[name] is None:
                self.assertIsNone(scaled_zones[name])
            else:
                self.assertAlmostEqual(reference_zones[name], scaled_zones[name], places=12)
        self.assertAlmostEqual(reference_ssim, scaled_ssim, places=12)


if __name__ == "__main__":
    unittest.main()
