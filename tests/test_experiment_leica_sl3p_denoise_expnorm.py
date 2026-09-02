"""`tools/experiment_leica_sl3p_denoise_expnorm.py`의 순수 로직 테스트 -
디노이즈/노출정규화 실험이 쓰는 통계 헬퍼(`_sign_test_p`, `summarize`,
`_exposure_normalize`)와, 합성 챠트 이미지로 `detect_and_sample_denoised()`를
검증한다(CI에 이미지 데이터 없음, `tests/CLAUDE.md`)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.core import chart_baseline
from tests.test_chart_baseline import _synthetic_chart_linear
from tools.experiment_leica_sl3p_denoise_expnorm import (
    detect_and_sample_denoised, _mean_de, _sign_test_p, _exposure_normalize, summarize,
)


class TestDetectAndSampleDenoised(unittest.TestCase):
    def test_recovers_known_colors_from_synthetic_chart(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        linear = _synthetic_chart_linear(ref)
        samples = detect_and_sample_denoised(linear, max_dim=2000, shrink=0.5, blur_ksize=5)
        self.assertIsNotNone(samples)
        self.assertEqual(samples.shape, (24, 3))
        de = chart_baseline.patch_delta_e(samples, ref)
        self.assertLess(float(np.mean(de)), 1.0)

    def test_returns_none_when_no_chart_present(self):
        blank = np.full((400, 600, 3), 0.3, dtype=np.float64)
        samples = detect_and_sample_denoised(blank, max_dim=800)
        self.assertIsNone(samples)


class TestMeanDe(unittest.TestCase):
    def test_zero_for_identical_samples(self):
        reference_xyz = chart_baseline.reference_patches_xyz_d50()
        self.assertAlmostEqual(_mean_de(reference_xyz, reference_xyz), 0.0, places=6)


class TestSignTestP(unittest.TestCase):
    def test_balanced_wins_losses_is_not_significant(self):
        self.assertAlmostEqual(_sign_test_p(5, 5), 1.0, places=6)

    def test_all_wins_is_highly_significant(self):
        p = _sign_test_p(10, 0)
        self.assertLess(p, 0.01)

    def test_no_samples_returns_one(self):
        self.assertEqual(_sign_test_p(0, 0), 1.0)


class TestExposureNormalize(unittest.TestCase):
    def test_scales_samples_to_match_reference_gain(self):
        reference = np.array([[0.5, 0.4, 0.3], [0.2, 0.2, 0.2]] * 12, dtype=np.float64)
        samples = reference * 0.5
        normalized = _exposure_normalize(samples, reference)
        np.testing.assert_allclose(normalized, reference, atol=1e-6)

    def test_leaves_already_matched_samples_unchanged(self):
        reference = np.array([[0.5, 0.4, 0.3], [0.2, 0.2, 0.2]] * 12, dtype=np.float64)
        normalized = _exposure_normalize(reference, reference)
        np.testing.assert_allclose(normalized, reference, atol=1e-6)


class TestSummarize(unittest.TestCase):
    def test_identical_arrays_is_inconclusive(self):
        des = [5.0, 6.0, 7.0, 8.0, 9.0] * 4
        result = summarize("A", des, "B", des, n_bootstrap=200)
        self.assertTrue(result["inconclusive"])
        self.assertAlmostEqual(result["improvement_pct"], 0.0, places=6)

    def test_consistently_better_array_is_not_inconclusive(self):
        a = [10.0] * 20
        b = [5.0] * 20
        result = summarize("A", a, "B", b, n_bootstrap=200)
        self.assertFalse(result["inconclusive"])
        self.assertGreater(result["improvement_pct"], 0.0)
        self.assertEqual(result["wins"], 20)
        self.assertEqual(result["losses"], 0)


if __name__ == "__main__":
    unittest.main()
