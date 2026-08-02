import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calibrate import _generation_for


class TestGenerationFor(unittest.TestCase):
    def test_cfv_passthrough(self):
        self.assertEqual(_generation_for("CFV 100C/907X"), "CFV 100C/907X")

    def test_x2d_passthrough(self):
        self.assertEqual(_generation_for("X2D 100C"), "X2D 100C")

    def test_x1d_ii_mapped(self):
        self.assertEqual(_generation_for("Hasselblad X1D II 50C"), "X1D II 50C")

    def test_x1d_mapped(self):
        self.assertEqual(_generation_for("Hasselblad X1D"), "X1D")

    def test_unknown_camera_passthrough(self):
        self.assertEqual(_generation_for("Some New Camera"), "Some New Camera")


class TestPairCountsSums(unittest.TestCase):
    def test_matches_manual_bincount(self):
        from tools.calibrate import _pair_counts_sums
        neutral_l = np.array([10, 10, 20, 250], dtype=np.int64)
        target_l = np.array([12.0, 14.0, 22.0, 240.0], dtype=np.float64)
        counts, sums = _pair_counts_sums(neutral_l, target_l)
        self.assertEqual(counts.shape, (256,))
        self.assertEqual(sums.shape, (256,))
        self.assertEqual(counts[10], 2)
        self.assertEqual(sums[10], 26.0)
        self.assertEqual(counts[20], 1)
        self.assertEqual(sums[20], 22.0)
        self.assertEqual(counts[250], 1)
        self.assertEqual(sums[250], 240.0)
        self.assertEqual(counts[0], 0)
        self.assertEqual(sums[0], 0.0)


class TestBuildLutFromCounts(unittest.TestCase):
    def test_lambda_zero_is_pure_empirical_mean(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.zeros(256, dtype=np.float64)
        sums = np.zeros(256, dtype=np.float64)
        counts[100] = 4
        sums[100] = 4 * 150.0  # 평균 150
        prior = np.arange(256, dtype=np.float32)  # prior[100] = 100
        lut = _build_lut_from_counts(counts, sums, prior, lam=0)
        self.assertAlmostEqual(lut[100], 150.0, places=4)

    def test_huge_lambda_converges_to_prior(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.zeros(256, dtype=np.float64)
        sums = np.zeros(256, dtype=np.float64)
        counts[100] = 4
        sums[100] = 4 * 150.0
        prior = np.arange(256, dtype=np.float32)
        lut = _build_lut_from_counts(counts, sums, prior, lam=1e9)
        self.assertAlmostEqual(lut[100], 100.0, places=1)

    def test_empty_bin_falls_back_to_prior(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.zeros(256, dtype=np.float64)
        sums = np.zeros(256, dtype=np.float64)
        prior = np.arange(256, dtype=np.float32)
        lut = _build_lut_from_counts(counts, sums, prior, lam=0)
        self.assertAlmostEqual(lut[50], 50.0, places=4)

    def test_monotonic_nondecreasing(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.array([0, 5, 0, 3] + [0] * 252, dtype=np.float64)
        sums = np.array([0, 5 * 200.0, 0, 3 * 10.0] + [0.0] * 252, dtype=np.float64)
        prior = np.arange(256, dtype=np.float32)
        lut = _build_lut_from_counts(counts, sums, prior, lam=0)
        self.assertTrue(np.all(np.diff(lut) >= 0))


if __name__ == "__main__":
    unittest.main()
