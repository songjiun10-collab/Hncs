import unittest

from hybrid_engine.evaluation.nare import (
    evaluate_nare_metrics,
    validate_nare_manifest,
    classify_nare_result,
)


def row(scene_id="s1", lighting="daylight", scene_type="portrait"):
    return {
        "scene_id": scene_id, "session_id": "session-1", "contributor": "p1",
        "source_path": f"{scene_id}.raw", "target_path": f"{scene_id}.jpg",
        "source_sha256": "a" * 64, "target_sha256": "b" * 64,
        "picture_style": "standard", "lighting": lighting,
        "scene_type": scene_type, "split": "evaluation",
    }


class TestNARE(unittest.TestCase):
    def test_manifest_requires_sooc_metadata_and_hashes(self):
        self.assertEqual(validate_nare_manifest([row()])["n_scenes"], 1)
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
                    "foundation_delta_e00": 8, "candidate_delta_e00": 7}
                   for i in range(6)]
        result = evaluate_nare_metrics(manifest, metrics, n_bootstrap=200, seed=0)
        self.assertEqual(result["n_scenes"], 6)
        self.assertEqual(result["baseline_layers"], ["raw_decoder", "colorimetric_foundation", "appearance_candidate"])
        self.assertAlmostEqual(result["improvement_pct"], 30.0)

    def test_ship_gate_requires_three_lighting_and_scene_strata(self):
        result = {"n_scenes": 12, "improvement_pct": 10,
                  "ci95": [0.1, 2], "sign_test_p": 0.01,
                  "coverage": {"lighting": ["daylight", "tungsten", "mixed"],
                               "scene_type": ["portrait", "landscape", "indoor"]},
                  "subgroups_passed": True, "controls_passed": True,
                  "provenance_passed": True}
        self.assertTrue(classify_nare_result(result)["ship_gate_passed"])
        result["coverage"]["lighting"] = ["daylight"]
        self.assertFalse(classify_nare_result(result)["ship_gate_passed"])


if __name__ == "__main__":
    unittest.main()
