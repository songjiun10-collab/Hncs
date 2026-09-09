import unittest

import numpy as np

from hybrid_engine.evaluation.care import (
    apply_exposure,
    apply_wb_gain,
    build_perturbations,
    compare_response,
    run_care_response,
    validate_care_record,
)


class TestCarePerturbations(unittest.TestCase):
    def test_build_perturbations_has_fixed_exposure_grid(self):
        grid = build_perturbations()
        self.assertEqual([item["ev"] for item in grid if item["kind"] == "exposure"],
                         [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0])

    def test_apply_exposure_scales_linear_rgb(self):
        image = np.array([[[0.25, 0.5, 1.0]]], dtype=np.float32)
        np.testing.assert_allclose(apply_exposure(image, 1.0), image * 2.0)

    def test_apply_wb_gain_changes_only_requested_channels(self):
        image = np.ones((1, 1, 3), dtype=np.float32)
        result = apply_wb_gain(image, red=1.1, blue=0.9)
        np.testing.assert_allclose(result[0, 0], [1.1, 1.0, 0.9])

    def test_compare_response_reports_identity_zero(self):
        image = np.full((2, 2, 3), 0.5, dtype=np.float32)
        result = compare_response(image, image)
        self.assertEqual(result["delta_e00"], 0.0)

    def test_compare_response_rejects_nonfinite_input(self):
        image = np.full((2, 2, 3), 0.5, dtype=np.float32)
        image[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            compare_response(image, image)

    def test_validate_care_record_rejects_missing_target_kind(self):
        with self.assertRaises(ValueError):
            validate_care_record({"capture_id": "a", "look": "provia"})

    def test_validate_care_record_rejects_unreviewed_scene_statistics(self):
        with self.assertRaises(ValueError):
            validate_care_record({"capture_id": "a", "target_kind": "none",
                                  "scene_reviewed": False, "delta_e00": 1.0})

    def test_validate_care_record_allows_diagnostic_without_target(self):
        record = validate_care_record({"capture_id": "a", "target_kind": "none",
                                       "scene_reviewed": False,
                                       "delta_e00": None})
        self.assertEqual(record["claim_level"], "diagnostic")

    def test_validate_care_record_rejects_numeric_delta_without_target(self):
        with self.assertRaises(ValueError):
            validate_care_record({"capture_id": "a", "target_kind": "none",
                                  "scene_reviewed": True, "delta_e00": 2.0})

    def test_compare_response_uses_common_shape(self):
        with self.assertRaises(ValueError):
            compare_response(np.zeros((2, 2, 3), dtype=np.float32),
                             np.zeros((3, 2, 3), dtype=np.float32))

    def test_apply_wb_gain_rejects_wrong_channel_count(self):
        with self.assertRaises(ValueError):
            apply_wb_gain(np.zeros((2, 2), dtype=np.float32), red=1.0, blue=1.0)

    def test_response_record_preserves_control_magnitude(self):
        image = np.full((2, 2, 3), 0.5, dtype=np.float32)
        result = compare_response(image, apply_exposure(image, 1.0), control_delta_e00=0.25)
        self.assertEqual(result["control_delta_e00"], 0.25)

    def test_run_care_response_keeps_zero_exposure_anchor(self):
        image = np.full((2, 2, 3), 0.5, dtype=np.float32)
        records = run_care_response(image, lambda value: value)
        anchor = next(item for item in records
                      if item["kind"] == "exposure" and item["ev"] == 0.0)
        self.assertEqual(anchor["response_delta_e00"], 0.0)

    def test_run_care_response_rejects_nonfinite_look_output(self):
        image = np.full((2, 2, 3), 0.5, dtype=np.float32)
        with self.assertRaises(ValueError):
            run_care_response(image, lambda value: np.full_like(value, np.nan))


if __name__ == "__main__":
    unittest.main()
