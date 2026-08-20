import unittest

import numpy as np

from tools.simulate_pair_count_power import _sign_test_p, bootstrap_power_at_n


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 6), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(13, 0), 0.001)


class TestBootstrapPowerAtN(unittest.TestCase):
    def test_returns_expected_keys(self):
        r = bootstrap_power_at_n([1.0, -1.0, 2.0, -0.5], n_target=10, n_bootstrap=200)
        for key in ("n_target", "observed_mean", "observed_sd",
                    "sign_test_significant_rate", "ci_excludes_zero_rate"):
            self.assertIn(key, r)
        self.assertEqual(r["n_target"], 10)

    def test_rates_are_probabilities(self):
        r = bootstrap_power_at_n([1.0, -1.0, 2.0, -0.5], n_target=10, n_bootstrap=200)
        self.assertGreaterEqual(r["sign_test_significant_rate"], 0.0)
        self.assertLessEqual(r["sign_test_significant_rate"], 1.0)
        self.assertGreaterEqual(r["ci_excludes_zero_rate"], 0.0)
        self.assertLessEqual(r["ci_excludes_zero_rate"], 1.0)

    def test_all_positive_diffs_gives_high_significance_rate(self):
        # 전부 양수인 관측값을 리샘플링하면 부호검정은 거의 항상 유의함
        r = bootstrap_power_at_n([1.0, 2.0, 1.5, 0.8, 1.2], n_target=30, n_bootstrap=500)
        self.assertGreater(r["sign_test_significant_rate"], 0.9)

    def test_zero_centered_diffs_gives_low_significance_rate(self):
        rng = np.random.default_rng(0)
        diffs = rng.normal(0.0, 1.0, size=13)
        r = bootstrap_power_at_n(diffs, n_target=13, n_bootstrap=500, seed=1)
        self.assertLess(r["sign_test_significant_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
