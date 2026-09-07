import unittest

import numpy as np

from hybrid_engine.evaluation.eager import (
    EvidenceTier,
    SceneMetric,
    aggregate_scene_metrics,
    evaluate_paired,
    validate_manifest,
    reconcile_sample_accounting,
    check_physical_sanity,
    classify_result,
)


class TestManifestValidation(unittest.TestCase):
    def _row(self, **overrides):
        row = {
            "scene_id": "scene-1",
            "source_body": "source-a",
            "target_body": "target-a",
            "illumination_id": "daylight",
            "source_path": "source.raw",
            "target_path": "target.jpg",
            "source_sha256": "a" * 64,
            "target_sha256": "b" * 64,
            "split": "evaluation",
            "evidence_tier": "C",
        }
        row.update(overrides)
        return row

    def test_valid_manifest_is_accepted(self):
        result = validate_manifest([self._row()])
        self.assertEqual(result["n_rows"], 1)
        self.assertEqual(result["n_scenes"], 1)

    def test_same_scene_in_multiple_splits_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_manifest([
                self._row(split="discovery"),
                self._row(source_body="source-b", split="lockbox"),
            ])

    def test_missing_provenance_hash_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_manifest([self._row(source_sha256="")])


class TestSampleAccounting(unittest.TestCase):
    def test_reconciles_monotonic_pipeline_counts(self):
        result = reconcile_sample_accounting({
            "requested": 10,
            "downloaded": 9,
            "decoded": 8,
            "provenance_valid": 7,
            "paired": 6,
            "group_valid": 5,
            "evaluated": 4,
            "excluded": {"decode_failure": 1, "pair_mismatch": 5},
        })
        self.assertEqual(result["excluded_total"], 6)
        self.assertEqual(result["requested"], result["evaluated"] + result["excluded_total"])

    def test_count_drift_is_rejected(self):
        with self.assertRaises(ValueError):
            reconcile_sample_accounting({
                "requested": 10,
                "downloaded": 9,
                "decoded": 8,
                "provenance_valid": 7,
                "paired": 6,
                "group_valid": 5,
                "evaluated": 4,
                "excluded": {"decode_failure": 1},
            })


class TestSceneMetrics(unittest.TestCase):
    def test_multiple_observations_collapse_to_one_independent_scene(self):
        rows = [
            SceneMetric("scene-1", 10.0, 8.0, "body-a", "daylight"),
            SceneMetric("scene-1", 12.0, 9.0, "body-b", "daylight"),
            SceneMetric("scene-2", 8.0, 7.0, "body-a", "tungsten"),
        ]
        grouped = aggregate_scene_metrics(rows)
        self.assertEqual(len(grouped), 2)
        self.assertAlmostEqual(grouped[0].baseline_delta_e00, 11.0)
        self.assertAlmostEqual(grouped[0].candidate_delta_e00, 8.5)

    def test_paired_result_reports_ci_and_sign_test(self):
        rows = [SceneMetric(f"s{i}", 10.0, value, "body", "daylight")
                for i, value in enumerate([8.0, 8.5, 9.0, 8.0, 8.5, 9.0])]
        result = evaluate_paired(rows, n_bootstrap=500, seed=0)
        self.assertEqual(result["n_scenes"], 6)
        self.assertGreater(result["mean_improvement"], 0)
        self.assertLess(result["sign_test_p"], 0.05)
        self.assertEqual(len(result["ci95"]), 2)


class TestGatesAndSanity(unittest.TestCase):
    def test_physical_sanity_rejects_nonmonotonic_tone(self):
        result = check_physical_sanity(
            matrix=np.eye(3),
            tone_curve=[0.0, 0.6, 0.4, 1.0],
            clipping_ratio=0.0,
        )
        self.assertFalse(result["passed"])
        self.assertIn("tone_nonmonotonic", result["failures"])

    def test_ship_gate_requires_positive_ci_and_controls(self):
        result = {
            "mean_improvement_pct": 8.0,
            "ci95": [0.2, 2.0],
            "sign_test_p": 0.01,
            "neutral_mean_improvement": 0.5,
            "chromatic_mean_improvement": 0.4,
            "robustness_passed": True,
            "controls_passed": True,
        }
        self.assertTrue(classify_result(
            result, EvidenceTier.C, lockbox_passed=True,
            external_replication=False, validation_passed=True,
        )["ship_gate_passed"])

    def test_tier_d_cannot_be_verified_from_lockbox_alone(self):
        result = {
            "mean_improvement_pct": 8.0,
            "ci95": [0.2, 2.0],
            "sign_test_p": 0.01,
            "neutral_mean_improvement": 0.5,
            "chromatic_mean_improvement": 0.4,
            "robustness_passed": True,
            "controls_passed": True,
        }
        classified = classify_result(
            result, EvidenceTier.D, lockbox_passed=True,
            external_replication=True, validation_passed=True,
        )
        self.assertFalse(classified["ship_gate_passed"])
        self.assertEqual(classified["classification"], "Exploratory")


if __name__ == "__main__":
    unittest.main()
