import unittest
from unittest.mock import patch

import numpy as np

from hybrid_engine.evaluate_generalization import run_generalization, _convergence_summary


def _test_image(seed=0, shape=(24, 24, 3)):
    rng = np.random.default_rng(seed)
    return rng.integers(20, 235, size=shape, dtype=np.uint8)


class TestConvergenceSummary(unittest.TestCase):
    def test_identical_post_stats_give_zero_std(self):
        results = {
            "sony": {"post_stats": {"b2": 10.0, "w995": 220.0, "sat": 50.0},
                     "pre_noise_sigma": 1.0, "post_noise_sigma": 1.0},
            "nikon": {"post_stats": {"b2": 10.0, "w995": 220.0, "sat": 50.0},
                      "pre_noise_sigma": 2.0, "post_noise_sigma": 1.0},
        }
        summary = _convergence_summary(results)
        self.assertEqual(summary["post_b2_std_across_sources"], 0.0)
        self.assertEqual(summary["post_w995_std_across_sources"], 0.0)
        self.assertEqual(summary["post_sat_std_across_sources"], 0.0)

    def test_fingerprint_erasure_ratio_below_one_means_convergence(self):
        results = {
            "a": {"post_stats": {"b2": 10, "w995": 220, "sat": 50},
                  "pre_noise_sigma": 1.0, "post_noise_sigma": 1.0},
            "b": {"post_stats": {"b2": 11, "w995": 221, "sat": 51},
                  "pre_noise_sigma": 5.0, "post_noise_sigma": 1.1},
        }
        summary = _convergence_summary(results)
        self.assertLess(summary["fingerprint_erasure_ratio"], 1.0)

    def test_zero_pre_noise_variance_gives_none_ratio(self):
        results = {
            "a": {"post_stats": {"b2": 10, "w995": 220, "sat": 50},
                  "pre_noise_sigma": 1.0, "post_noise_sigma": 1.0},
            "b": {"post_stats": {"b2": 11, "w995": 221, "sat": 51},
                  "pre_noise_sigma": 1.0, "post_noise_sigma": 2.0},
        }
        summary = _convergence_summary(results)
        self.assertIsNone(summary["fingerprint_erasure_ratio"])


class TestRunGeneralizationSyntheticOnly(unittest.TestCase):
    """실제 RAW 디코드 없이(fuji glob을 빈 리스트로 mock) 합성 소스
    경로(sony/nikon/canon)만 검증 - CI에서 빠르게 돈다."""

    def test_unknown_target_brand_raises(self):
        with self.assertRaises(ValueError):
            run_generalization("not-a-brand", "/nonexistent.jpg")

    def test_synthetic_sources_produce_stats_when_no_raw_available(self):
        import tempfile
        import cv2
        with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
            cv2.imwrite(f.name, _test_image())
            with patch("hybrid_engine.evaluate_generalization.glob.glob", return_value=[]):
                results = run_generalization("hasselblad", f.name)

        self.assertNotIn("fuji", results)
        for brand in ("sony", "nikon", "canon"):
            self.assertIn(brand, results)
            self.assertFalse(results[brand]["is_real_raw"])
            self.assertIn("b2", results[brand]["post_stats"])


if __name__ == "__main__":
    unittest.main()
