import json
import subprocess
import sys
import tempfile
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
    evaluate_manifest_metrics,
    validate_controls,
    validate_robustness,
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

    def test_manifest_metrics_join_uses_one_row_per_scene(self):
        manifest = [
            {
                "scene_id": "scene-1", "source_body": "a", "target_body": "b",
                "illumination_id": "daylight", "source_path": "a.raw",
                "target_path": "b.jpg", "source_sha256": "a" * 64,
                "target_sha256": "b" * 64, "split": "lockbox", "evidence_tier": "C",
            },
            {
                "scene_id": "scene-1", "source_body": "c", "target_body": "b",
                "illumination_id": "daylight", "source_path": "c.raw",
                "target_path": "b.jpg", "source_sha256": "c" * 64,
                "target_sha256": "b" * 64, "split": "lockbox", "evidence_tier": "C",
            },
        ]
        result = evaluate_manifest_metrics(
            manifest, [{"scene_id": "scene-1", "baseline_delta_e00": 10, "candidate_delta_e00": 8}],
            n_bootstrap=100, seed=0,
        )
        self.assertEqual(result["manifest"]["n_scenes"], 1)
        self.assertEqual(result["paired"]["n_scenes"], 1)

    def test_manifest_metrics_join_rejects_missing_scene_metric(self):
        manifest = [{
            "scene_id": "scene-1", "source_body": "a", "target_body": "b",
            "illumination_id": "daylight", "source_path": "a.raw", "target_path": "b.jpg",
            "source_sha256": "a" * 64, "target_sha256": "b" * 64,
            "split": "evaluation", "evidence_tier": "C",
        }]
        with self.assertRaises(ValueError):
            evaluate_manifest_metrics(manifest, [], n_bootstrap=100)


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

    def test_all_required_controls_must_be_present_and_true(self):
        controls = {
            "identity_baseline": True,
            "target_reference_shuffle": True,
            "source_label_shuffle": True,
            "holdout_rerun": True,
            "chart_positive_control": True,
        }
        self.assertEqual(validate_controls(controls)["passed"], True)
        controls["source_label_shuffle"] = False
        self.assertFalse(validate_controls(controls)["passed"])

    def test_robustness_rejects_any_failing_stratum(self):
        result = validate_robustness({"body-a": True, "tungsten": False})
        self.assertFalse(result["passed"])
        self.assertEqual(result["failures"], ["tungsten"])

    def test_cli_emits_classified_report_from_json_inputs(self):
        manifest = []
        metrics = []
        for index in range(6):
            scene_id = f"scene-{index}"
            manifest.append({
                "scene_id": scene_id, "source_body": "source", "target_body": "target",
                "illumination_id": "daylight", "source_path": f"{scene_id}.raw",
                "target_path": f"{scene_id}.jpg", "source_sha256": "a" * 64,
                "target_sha256": "b" * 64, "split": "lockbox", "evidence_tier": "C",
            })
            metrics.append({"scene_id": scene_id, "baseline_delta_e00": 10, "candidate_delta_e00": 8})
        controls = {
            "identity_baseline": True, "target_reference_shuffle": True,
            "source_label_shuffle": True, "holdout_rerun": True,
            "chart_positive_control": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            paths = {}
            for name, value in (("manifest", manifest), ("metrics", metrics),
                                ("controls", controls), ("robustness", {"body": True})):
                path = f"{directory}/{name}.json"
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(value, handle)
                paths[name] = path
            proc = subprocess.run(
                [sys.executable, "-m", "hybrid_engine.evaluation.eager_cli",
                 "--manifest", paths["manifest"], "--metrics", paths["metrics"],
                 "--controls", paths["controls"], "--robustness", paths["robustness"],
                 "--evidence-tier", "C", "--validation-passed", "--lockbox-passed"],
                capture_output=True, text=True, check=True,
            )
        report = json.loads(proc.stdout)
        self.assertEqual(report["classification"]["classification"], "Supported")
        self.assertTrue(report["classification"]["ship_gate_passed"])


if __name__ == "__main__":
    unittest.main()
