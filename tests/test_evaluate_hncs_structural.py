import unittest

import numpy as np

from tools.evaluate_hncs_structural import (
    _pair_names, _resize_max_dim, _sign_test_p, summarize,
)

# hybrid_engine/EVALUATION.md "HNCS 구조 실험" 절에 기록된 실측 13폴드
# 결과 그대로 - 문서에 적힌 통계치가 summarize()로 재현되는지 여기서
# 검증한다(LOOCV를 다시 돌리지 않고도 확인 가능하도록).
RECORDED_PER_FOLD = [
    ("x1d-II-sample-02.jpg", "cluster_a", 10.787, 9.961),
    ("x1d-II-sample-09.jpg", "cluster_b", 5.249, 13.449),
    ("B0000994.jpg", "cluster_b", 14.223, 9.128),
    ("B0001395.jpg", "cluster_a", 18.412, 18.334),
    ("x1d-xcd45-01.jpg", "cluster_a", 13.194, 9.395),
    ("x1d-xcd45-03.jpg", "cluster_a", 8.342, 9.246),
    ("x1d-xcd45-04.jpg", "cluster_a", 4.729, 8.245),
    ("x1d-ii-xcd45p-01.jpg", "cluster_a", 10.126, 14.976),
    ("x1d-ii-xcd45p-02.jpg", "cluster_a", 11.055, 11.645),
    ("x1d-II-sample-01.jpg", "cluster_a", 6.452, 5.478),
    ("x1d-II-sample-06.jpg", "cluster_a", 11.726, 8.610),
    ("02709.jpg", "cluster_b", 13.074, 9.636),
    ("00378.jpg", "cluster_a", 5.115, 10.073),
]


class TestPairNames(unittest.TestCase):
    def test_returns_13_real_pairs(self):
        names = _pair_names()
        self.assertEqual(len(names), 13)

    def test_excludes_x2dii_chart_files(self):
        names = _pair_names()
        self.assertFalse(any("x2dii-chart" in n for n in names))

    def test_names_are_jpeg_basenames(self):
        names = _pair_names()
        self.assertTrue(all(n.endswith(".jpg") for n in names))


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(1000, 2000, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertLessEqual(max(out.shape[:2]), 512)
        # aspect ratio preserved (within 1px rounding)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 2000 / 1000, places=1)

    def test_preserves_channel_count(self):
        img = np.random.default_rng(2).uniform(0, 1, size=(600, 300, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertEqual(out.shape[2], 3)


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(5, 5), 1.0)

    def test_all_wins_is_significant(self):
        # 13전 13승 -> 2 * (1/2^13) = 0.000244
        self.assertAlmostEqual(_sign_test_p(13, 0), 2.0 / 2 ** 13, places=6)

    def test_six_of_thirteen_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 7), 1.0)

    def test_no_folds_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)


class TestSummarizeRecordedRun(unittest.TestCase):
    """EVALUATION.md에 기록된 수치가 summarize()에서 그대로 나오는지."""

    @classmethod
    def setUpClass(cls):
        cls.s = summarize(RECORDED_PER_FOLD)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_structural"], 10.191, places=3)
        self.assertAlmostEqual(self.s["mean_hncs"], 10.629, places=3)
        self.assertAlmostEqual(self.s["improvement_pct"], 4.1, places=1)

    def test_reproduces_documented_fold_counts(self):
        self.assertEqual(self.s["structural_wins"], 6)
        self.assertEqual(self.s["hncs_wins"], 7)
        self.assertEqual(self.s["n"], 13)

    def test_median_fold_favours_apply_hncs(self):
        # 평균은 구조 실험이 앞서지만 중앙값 폴드는 반대 방향이다.
        self.assertLess(self.s["median_diff"], 0.0)

    def test_paired_difference_is_not_distinguishable_from_zero(self):
        self.assertAlmostEqual(self.s["sd_diff"], 3.978, places=2)
        self.assertLess(abs(self.s["t_stat"]), 2.18)  # df=12 양측 5% 임계값
        self.assertAlmostEqual(self.s["sign_test_p"], 1.0, places=6)
        lo, hi = self.s["ci_diff"]
        self.assertLess(lo, 0.0)
        self.assertGreater(hi, 0.0)
        self.assertTrue(self.s["inconclusive"])

    def test_dropping_one_pair_flips_the_sign(self):
        self.assertTrue(self.s["dropone_flips_sign"])
        self.assertLess(self.s["dropone_pct_min"], 0.0)

    def test_verdict_is_inconclusive_not_a_win(self):
        self.assertIn("판정 보류", self.s["verdict"])


class TestSummarizeDecisiveCase(unittest.TestCase):
    """차이가 실제로 크고 일관되면 승리 판정이 나오는지(보류가 기본값이
    되어버리지 않는지) 확인."""

    def test_consistent_large_win_is_declared(self):
        per_fold = [(f"p{i}.jpg", "cluster_a", 5.0, 10.0) for i in range(13)]
        s = summarize(per_fold, n_bootstrap=2000)
        self.assertFalse(s["inconclusive"])
        self.assertEqual(s["verdict"], "구조적 실험이 이겼다")

    def test_consistent_large_loss_is_declared(self):
        per_fold = [(f"p{i}.jpg", "cluster_a", 10.0, 5.0) for i in range(13)]
        s = summarize(per_fold, n_bootstrap=2000)
        self.assertFalse(s["inconclusive"])
        self.assertEqual(s["verdict"], "apply_hncs()가 더 낫다")


if __name__ == "__main__":
    unittest.main()
