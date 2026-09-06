"""`tools/experiment_leica_sl3p_upscale_chart.py`의 순수 로직 테스트 -
실제 raw 디코드 없이 `tests/test_chart_baseline.py`와 같은 합성 챠트
이미지로 `detect_and_sample_upscaled()`을 검증한다(CI에 이미지 데이터
없음, `tests/CLAUDE.md`)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.core import chart_baseline
from tests.test_chart_baseline import _synthetic_chart_linear
from tools.experiment_leica_sl3p_upscale_chart import detect_and_sample_upscaled, _mean_de


class TestDetectAndSampleUpscaled(unittest.TestCase):
    def setUp(self):
        self.ref = chart_baseline.reference_patches_linear_srgb()
        self.linear = _synthetic_chart_linear(self.ref)

    def test_upscale_1x_recovers_known_colors(self):
        samples = detect_and_sample_upscaled(self.linear, max_dim=2000, shrink=0.5, upscale=1.0)
        self.assertIsNotNone(samples)
        self.assertEqual(samples.shape, (24, 3))
        de = chart_baseline.patch_delta_e(samples, self.ref)
        self.assertLess(float(np.mean(de)), 1.0)

    def test_upscale_3x_recovers_known_colors(self):
        samples = detect_and_sample_upscaled(self.linear, max_dim=2000, shrink=0.5, upscale=3.0)
        self.assertIsNotNone(samples)
        self.assertEqual(samples.shape, (24, 3))
        de = chart_baseline.patch_delta_e(samples, self.ref)
        self.assertLess(float(np.mean(de)), 1.0)

    def test_returns_none_when_no_chart_present(self):
        blank = np.full((400, 600, 3), 0.3, dtype=np.float64)
        samples = detect_and_sample_upscaled(blank, max_dim=800)
        self.assertIsNone(samples)


class TestMeanDe(unittest.TestCase):
    def test_zero_for_identical_samples(self):
        reference_xyz = chart_baseline.reference_patches_xyz_d50()
        self.assertAlmostEqual(_mean_de(reference_xyz, reference_xyz), 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
