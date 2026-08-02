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


class TestSubtractionLooMatchesRecompute(unittest.TestCase):
    def test_subtraction_equals_full_recompute(self):
        from tools.calibrate import _pair_counts_sums, _build_lut_from_counts

        rng = np.random.default_rng(42)
        pairs = []
        for _ in range(4):
            neutral_l = rng.integers(0, 256, size=30).astype(np.int64)
            target_l = neutral_l.astype(np.float64) + rng.normal(0, 5, size=30)
            counts, sums = _pair_counts_sums(neutral_l, target_l)
            pairs.append(dict(neutral_l=neutral_l, target_l=target_l,
                               counts=counts, sums=sums))

        prior = np.arange(256, dtype=np.float32)
        lam = 500

        counts_all = sum(p['counts'] for p in pairs)
        sums_all = sum(p['sums'] for p in pairs)

        for i, held_out in enumerate(pairs):
            # 뺄셈 방식
            train_counts_sub = counts_all - held_out['counts']
            train_sums_sub = sums_all - held_out['sums']
            lut_sub = _build_lut_from_counts(train_counts_sub, train_sums_sub, prior, lam)

            # 재계산 방식 (기존 방식 그대로 재현)
            train = [p for j, p in enumerate(pairs) if j != i]
            train_counts_full = sum(p['counts'] for p in train)
            train_sums_full = sum(p['sums'] for p in train)
            lut_full = _build_lut_from_counts(train_counts_full, train_sums_full, prior, lam)

            np.testing.assert_array_equal(lut_sub, lut_full)


class TestSignTestP(unittest.TestCase):
    def test_no_pairs_is_p_one(self):
        from tools.calibrate import _sign_test_p
        self.assertEqual(_sign_test_p(0, 0), 1.0)

    def test_even_split_is_p_one(self):
        from tools.calibrate import _sign_test_p
        self.assertAlmostEqual(_sign_test_p(5, 5), 1.0)

    def test_all_wins_is_significant(self):
        from tools.calibrate import _sign_test_p
        p = _sign_test_p(10, 0)
        self.assertLess(p, 0.05)


class TestSummarizeShape(unittest.TestCase):
    def test_returns_expected_keys(self):
        from tools.calibrate import summarize
        per_fold = [(f"pair{i}", 10.0, 9.0) for i in range(20)]
        s = summarize(per_fold)
        expected_keys = {
            "n", "mean_a", "mean_b", "mean_diff", "median_diff",
            "improvement_pct", "b_wins", "a_wins", "sd_diff", "sem_diff",
            "t_stat", "sign_test_p", "ci_diff", "ci_pct",
            "dropone_pct_min", "dropone_pct_max", "dropone_flips_sign",
            "inconclusive", "verdict",
        }
        self.assertEqual(set(s.keys()), expected_keys)
        self.assertEqual(s["n"], 20)
        self.assertAlmostEqual(s["mean_a"], 10.0)
        self.assertAlmostEqual(s["mean_b"], 9.0)

    def test_identical_values_is_inconclusive(self):
        from tools.calibrate import summarize
        per_fold = [(f"pair{i}", 10.0, 10.0) for i in range(20)]
        s = summarize(per_fold)
        self.assertTrue(s["inconclusive"])
        self.assertIn("판정 보류", s["verdict"])


class TestGenerationBreakdown(unittest.TestCase):
    def test_groups_and_computes_rmse(self):
        from tools.calibrate import _generation_breakdown
        fold = [
            ("a", "X1D", 3.0),
            ("b", "X1D", 5.0),
            ("c", "X2D 100C", 4.0),
        ]
        result = _generation_breakdown(fold)
        by_gen = {gen: (n, rmse) for gen, n, rmse in result}
        self.assertEqual(by_gen["X1D"][0], 2)
        self.assertAlmostEqual(by_gen["X1D"][1], (3.0 ** 2 + 5.0 ** 2) ** 0.5 / (2 ** 0.5))
        self.assertEqual(by_gen["X2D 100C"][0], 1)
        self.assertAlmostEqual(by_gen["X2D 100C"][1], 4.0)

    def test_sorted_by_generation_name(self):
        from tools.calibrate import _generation_breakdown
        fold = [("a", "X2D 100C", 1.0), ("b", "CFV 100C/907X", 1.0)]
        result = _generation_breakdown(fold)
        gens = [gen for gen, _, _ in result]
        self.assertEqual(gens, sorted(gens))


if __name__ == "__main__":
    unittest.main()
