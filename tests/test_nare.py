import hashlib
import unittest

from hybrid_engine.evaluation.nare import (
    evaluate_nare_metrics,
    validate_nare_manifest,
    classify_nare_result,
    summarize_nare_subgroups,
)


def row(scene_id="s1", lighting="daylight", scene_type="portrait"):
    return {
        "scene_id": scene_id, "session_id": "session-1", "contributor": "p1",
        "source_path": f"{scene_id}.raw", "target_path": f"{scene_id}.jpg",
        "source_sha256": hashlib.sha256(f"raw-{scene_id}".encode()).hexdigest(),
        "target_sha256": hashlib.sha256(f"jpeg-{scene_id}".encode()).hexdigest(),
        "picture_style": "standard", "lighting": lighting,
        "scene_type": scene_type, "split": "evaluation",
    }


class TestNARE(unittest.TestCase):
    def test_manifest_requires_sooc_metadata_and_hashes(self):
        summary = validate_nare_manifest([row()])
        self.assertEqual(summary["n_scenes"], 1)
        self.assertEqual(summary["n_sessions"], 1)
        bad = row(); bad["picture_style"] = ""
        with self.assertRaises(ValueError):
            validate_nare_manifest([bad])

    def test_manifest_rejects_scene_split_leakage(self):
        bad = row(); bad["split"] = "lockbox"
        with self.assertRaises(ValueError):
            validate_nare_manifest([row(), bad])

    def test_evaluation_keeps_three_baselines_at_scene_level(self):
        manifest = [row(f"s{i}", "daylight" if i < 3 else "tungsten",
                        "portrait" if i % 2 else "landscape") for i in range(6)]
        metrics = [{"scene_id": f"s{i}", "raw_delta_e00": 10,
                    "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                    "registration": {"ecc_correlation": 0.9, "overlap_fraction": 0.99,
                                     "shift_x_px": 0, "shift_y_px": 0, "long_edge_px": 512}}
                   for i in range(6)]
        result = evaluate_nare_metrics(manifest, metrics, n_bootstrap=200, seed=0)
        self.assertEqual(result["n_scenes"], 6)
        self.assertEqual(result["baseline_layers"], ["raw_decoder", "colorimetric_foundation", "appearance_candidate"])
        self.assertAlmostEqual(result["improvement_pct"], 30.0)
        self.assertTrue(result["registration_passed"])
        self.assertFalse(result["subgroup_metrics_passed"])

    def test_evaluation_rejects_invalid_registration_values(self):
        manifest = [row(f"s{i}") for i in range(2)]
        metrics = [{"scene_id": f"s{i}", "raw_delta_e00": 10,
                    "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                    "registration": {"ecc_correlation": -1,
                                      "overlap_fraction": 0,
                                      "shift_x_px": 0, "shift_y_px": 0}}
                   for i in range(2)]
        result = evaluate_nare_metrics(manifest, metrics, n_bootstrap=20)
        self.assertFalse(result["registration_passed"])

    def test_evaluation_rejects_non_integer_registration_scale(self):
        manifest = [row("s1")]
        metrics = [{"scene_id": "s1", "raw_delta_e00": 10,
                    "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                    "registration": {"ecc_correlation": .9,
                                      "overlap_fraction": .99,
                                      "shift_x_px": 0, "shift_y_px": 0,
                                      "long_edge_px": 512.0}}]
        result = evaluate_nare_metrics(manifest, metrics, n_bootstrap=20)
        self.assertFalse(result["registration_passed"])

    def test_evaluation_rejects_duplicate_metric_scene_ids(self):
        manifest = [row("s1")]
        metric = {"scene_id": "s1", "raw_delta_e00": 10,
                  "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                  "registration": {"ecc_correlation": .9,
                                    "overlap_fraction": .99}}
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate_nare_metrics(manifest, [metric, dict(metric)], n_bootstrap=20)

    def test_evaluation_rejects_boolean_or_nonpositive_bootstrap_metadata(self):
        manifest = [row("s1")]
        metric = [{"scene_id": "s1", "raw_delta_e00": 10,
                   "foundation_delta_e00": 8, "candidate_delta_e00": 7}]
        with self.assertRaisesRegex(ValueError, "n_bootstrap"):
            evaluate_nare_metrics(manifest, metric, n_bootstrap=True)
        with self.assertRaisesRegex(ValueError, "n_bootstrap"):
            evaluate_nare_metrics(manifest, metric, n_bootstrap=0)
        with self.assertRaisesRegex(ValueError, "seed"):
            evaluate_nare_metrics(manifest, metric, seed=True)

    def test_evaluation_coverage_uses_evaluated_rows_only(self):
        manifest = [row(f"s{i}", "daylight", "landscape") for i in range(3)]
        for i, lighting in enumerate(("tungsten", "mixed"), 3):
            extra = row(f"s{i}", lighting, ("portrait", "indoor")[i - 3])
            extra["split"] = "discovery"
            manifest.append(extra)
        metrics = [{"scene_id": f"s{i}", "raw_delta_e00": 10,
                    "foundation_delta_e00": 8, "candidate_delta_e00": 7,
                    "registration": {"ecc_correlation": .9,
                                      "overlap_fraction": .99}}
                   for i in range(3)]
        result = evaluate_nare_metrics(manifest, metrics, n_bootstrap=20)
        self.assertEqual(result["coverage"]["lighting"], ["daylight"])

    def test_subgroups_reject_nonfinite_and_zero_baseline_regression(self):
        bad = [{"scene_id": "s1", "subgroups": {
            name: {"baseline_delta_e00": 0, "candidate_delta_e00": 100}
            for name in ("skin", "sky")}}]
        result = summarize_nare_subgroups(bad, required=("skin", "sky"))
        self.assertFalse(result["passed"])
        self.assertIn("skin", result["catastrophic_regressions"])
        nan = [{"scene_id": "s1", "subgroups": {
            name: {"baseline_delta_e00": 1, "candidate_delta_e00": float("nan")}
            for name in ("skin", "sky")}}]
        with self.assertRaisesRegex(ValueError, "finite"):
            summarize_nare_subgroups(nan, required=("skin", "sky"))

    def _passing_gate(self):
        return {"n_scenes": 12, "improvement_pct": 10,
                "ci95": [0.1, 2], "sign_test_p": 0.01,
                "coverage": {"lighting": ["daylight", "tungsten", "mixed"],
                             "scene_type": ["portrait", "landscape", "indoor"]},
                "picture_styles": ["standard"], "registration_passed": True,
                "subgroup_metrics_passed": True, "subgroups_passed": True,
                "controls_passed": True, "provenance_passed": True,
                "receipt_valid": True}

    def test_ship_gate_requires_three_lighting_and_scene_strata(self):
        result = self._passing_gate()
        self.assertTrue(classify_nare_result(result)["ship_gate_passed"])
        result["coverage"]["lighting"] = ["daylight"]
        self.assertFalse(classify_nare_result(result)["ship_gate_passed"])

    def test_ship_gate_rejects_unreceipted_plausible_metrics(self):
        result = self._passing_gate()
        result.pop("receipt_valid")
        report = classify_nare_result(result)
        self.assertFalse(report["ship_gate_passed"])
        self.assertFalse(report["checks"]["receipt_integrity"])

    def test_ship_gate_rejects_mixed_or_unknown_picture_style(self):
        result = self._passing_gate()
        self.assertTrue(classify_nare_result(result)["ship_gate_passed"])
        result["picture_styles"] = ["standard", "velvia"]
        self.assertFalse(classify_nare_result(result)["ship_gate_passed"])
        result["picture_styles"] = ["unknown"]
        self.assertFalse(classify_nare_result(result)["ship_gate_passed"])

    def test_ship_gate_requires_recorded_registration(self):
        result = self._passing_gate()
        result.pop("registration_passed")
        self.assertFalse(classify_nare_result(result)["ship_gate_passed"])

    def test_subgroups_require_all_requested_regions_and_block_catastrophic_loss(self):
        metrics = [
            {"scene_id": "s1", "subgroups": {
                "skin": {"baseline_delta_e00": 10, "candidate_delta_e00": 8},
                "sky": {"baseline_delta_e00": 10, "candidate_delta_e00": 11},
            }},
            {"scene_id": "s2", "subgroups": {
                "skin": {"baseline_delta_e00": 12, "candidate_delta_e00": 9},
                "sky": {"baseline_delta_e00": 8, "candidate_delta_e00": 20},
            }},
        ]
        result = summarize_nare_subgroups(metrics, required=("skin", "sky"),
                                          catastrophic_regression_pct=25)
        self.assertAlmostEqual(result["groups"]["skin"]["improvement_pct"], 22.727272727272727)
        self.assertFalse(result["passed"])
        self.assertIn("sky", result["catastrophic_regressions"])


if __name__ == "__main__":
    unittest.main()
