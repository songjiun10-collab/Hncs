import math
import unittest

import numpy as np

from tools.evaluate_chromatic_aberration import _resize_max_dim, _sign_test_p, summarize


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(2000, 4000, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertLessEqual(max(out.shape[:2]), 512)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 4000 / 2000, places=1)


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 6), 1.0)

    def test_no_pairs_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(13, 0), 0.001)

    def test_known_exact_value(self):
        # C(13,3) 이하 누적 / 2^13 = 0.046142578125(한쪽 꼬리) x 2(양측) -
        # tools/evaluate_darktable_vs_rawpy.py의 동일 구현/동일 관례로
        # 교차검증한 값(_sign_test_p(10, 3) == 0.09228515625)
        self.assertAlmostEqual(_sign_test_p(10, 3), 0.09228515625, places=9)


class TestSummarizeShape(unittest.TestCase):
    """summarize(baseline_de, best_de, names)가 반환하는 dict의 키/타입만
    검증 - tools/evaluate_chromatic_aberration.py의 실제 시그니처(리스트
    of 튜플이 아니라 3개의 나란한 배열)를 그대로 따른다."""

    def test_returns_expected_keys(self):
        names = ["p1", "p2", "p3"]
        baseline_de = [10.0, 12.0, 9.0]
        best_de = [8.0, 12.5, 7.5]
        s = summarize(baseline_de, best_de, names)
        for key in ("n", "mean_baseline", "mean_best", "mean_diff", "rel_pct",
                    "n_better", "n_worse", "n_tie", "sign_test_p", "t_stat",
                    "ci_lo", "ci_hi", "drop_one_min", "drop_one_max"):
            self.assertIn(key, s)
        self.assertEqual(s["n"], 3)
        self.assertEqual(s["n_better"], 2)
        self.assertEqual(s["n_worse"], 1)


# 실제 13쌍 LOO 교차검증 재실행 기록값 - hybrid_engine/EVALUATION.md의
# "색수차 보정(chromatic aberration) 실험" 절에 실린 것과 정확히 같다.
# (name, de_baseline, de_corrected) - best_red/best_blue는 summarize()가
# 안 쓰므로 뺐다(둘 다 폴드 전부 (1.0, 1.0) 선택 - 완전 무신호).
_RECORDED_13_PAIR_RUN = [
    ("x1d-II-sample-02.jpg", 13.858, 13.858),
    ("x1d-II-sample-09.jpg", 17.301, 17.301),
    ("B0000994.jpg", 14.667, 14.667),
    ("B0001395.jpg", 16.005, 16.005),
    ("x1d-xcd45-01.jpg", 16.700, 16.700),
    ("x1d-xcd45-03.jpg", 3.936, 3.936),
    ("x1d-xcd45-04.jpg", 3.670, 3.670),
    ("x1d-ii-xcd45p-01.jpg", 6.563, 6.563),
    ("x1d-ii-xcd45p-02.jpg", 9.938, 9.938),
    ("x1d-II-sample-01.jpg", 13.903, 13.903),
    ("x1d-II-sample-06.jpg", 17.088, 17.088),
    ("02709.jpg", 12.496, 12.496),
    ("00378.jpg", 3.866, 3.866),
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 실제 13쌍 LOO 결과를
    재현하는 회귀 테스트 - 스크립트를 다시 안 돌려도(60~70분 소요)
    문서의 통계 수치를 검증할 수 있다. 이 기록은 완전히 평평한
    결과다: 13개 LOO 폴드 전부가 훈련 폴드 12쌍에서 (1.0, 1.0)을
    최선으로 골랐다 - baseline과 corrected가 폴드마다 바이트
    단위로(따라서 ΔE 단위로도) 동일하다. diffs가 전부 정확히 0이라
    표본표준편차도 0 - _paired_t()는 이 경우 t_stat=inf를 반환한다
    (0으로 나누기 방지 분기, `se > 0`이 거짓)."""

    def setUp(self):
        names = [r[0] for r in _RECORDED_13_PAIR_RUN]
        baseline_de = [r[1] for r in _RECORDED_13_PAIR_RUN]
        best_de = [r[2] for r in _RECORDED_13_PAIR_RUN]
        self.s = summarize(baseline_de, best_de, names)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_baseline"], 11.538, places=2)
        self.assertAlmostEqual(self.s["mean_best"], 11.538, places=2)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["n_better"], 0)
        self.assertEqual(self.s["n_worse"], 0)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["sign_test_p"], 1.0, places=9)

    def test_t_stat_is_inf_for_zero_variance_diffs(self):
        self.assertTrue(math.isinf(self.s["t_stat"]))


# 2026-08 - 13쌍 결과를 83쌍(공식 13 + 로컬 기여 61 + owner-x2dii 9)으로
# 재검증한 실제 재실행 출력 그대로 - hybrid_engine/EVALUATION.md의 같은
# 절에 실린 것과 정확히 같다.
_RECORDED_83_PAIR_RUN = [
    ("x1d-II-sample-02.jpg", 13.864, 13.864),
    ("x1d-II-sample-09.jpg", 17.319, 17.319),
    ("B0000994.jpg", 14.709, 14.709),
    ("B0001395.jpg", 16.023, 16.023),
    ("x1d-xcd45-01.jpg", 16.704, 16.704),
    ("x1d-xcd45-03.jpg", 3.942, 3.942),
    ("x1d-xcd45-04.jpg", 3.717, 3.717),
    ("x1d-ii-xcd45p-01.jpg", 6.600, 6.600),
    ("x1d-ii-xcd45p-02.jpg", 9.956, 9.956),
    ("x1d-II-sample-01.jpg", 13.896, 13.896),
    ("x1d-II-sample-06.jpg", 17.126, 17.126),
    ("02709.jpg", 12.498, 12.498),
    ("00378.jpg", 3.874, 3.874),
    ("local-mixed-2026-07__6507810936", 8.561, 8.561),
    ("local-mixed-2026-07__0149725587", 5.300, 5.300),
    ("local-mixed-2026-07__8204307982", 4.719, 4.719),
    ("local-mixed-2026-07__3832345792", 5.653, 5.653),
    ("local-mixed-2026-07__5537240075", 5.370, 5.370),
    ("local-mixed-2026-07__0587181218", 3.665, 3.665),
    ("local-mixed-2026-07__7971015535", 4.796, 4.796),
    ("local-mixed-2026-07__6311094775", 3.239, 3.239),
    ("local-mixed-2026-07__6787000086", 11.556, 11.556),
    ("local-mixed-2026-07__7826992126", 5.468, 5.468),
    ("local-mixed-2026-07__5533274085", 4.380, 4.380),
    ("local-mixed-2026-07__1094220000", 4.565, 4.565),
    ("local-mixed-2026-07__8082395282", 4.778, 4.778),
    ("local-mixed-2026-07__1932636179", 4.849, 4.849),
    ("local-mixed-2026-07__3953661245", 4.820, 4.820),
    ("local-mixed-2026-07__8127122405", 2.688, 2.688),
    ("local-mixed-2026-07__5746737497", 8.011, 8.011),
    ("local-mixed-2026-07__9515423899", 3.256, 3.256),
    ("local-mixed-2026-07__6454535758", 4.039, 4.039),
    ("local-mixed-2026-07__8742913299", 3.528, 3.528),
    ("local-mixed-2026-07__7492975828", 2.932, 2.932),
    ("local-mixed-2026-07__7321006825", 4.051, 4.051),
    ("local-mixed-2026-07__6660888354", 33.030, 33.030),
    ("local-mixed-2026-07__4236625428", 4.179, 4.179),
    ("local-mixed-2026-07__8581844385", 14.945, 14.945),
    ("local-mixed-2026-07__7121592185", 14.233, 14.233),
    ("local-mixed-2026-07__3766372330", 5.108, 5.108),
    ("local-mixed-2026-07__7732046028", 5.089, 5.089),
    ("local-mixed-2026-07__0908944042", 5.976, 5.976),
    ("local-mixed-2026-07__1917191504", 4.026, 4.026),
    ("local-mixed-2026-07__9011626130", 3.094, 3.094),
    ("local-mixed-2026-07__5310704161", 5.721, 5.721),
    ("local-mixed-2026-07__3683076943", 6.521, 6.521),
    ("local-mixed-2026-07__7406451876", 6.420, 6.420),
    ("local-mixed-2026-07__6519755969", 6.228, 6.228),
    ("local-mixed-2026-07__3333340029", 14.562, 14.562),
    ("local-mixed-2026-07__9479682988", 8.794, 8.794),
    ("local-mixed-2026-07__5385314660", 5.263, 5.263),
    ("local-mixed-2026-07__9247740424", 2.064, 2.064),
    ("local-mixed-2026-07__5715595764", 7.856, 7.856),
    ("local-mixed-2026-07__6704898202", 4.434, 4.434),
    ("local-mixed-2026-07__6340134840", 3.312, 3.312),
    ("local-mixed-2026-07__9928856380", 4.626, 4.626),
    ("local-mixed-2026-07__0758706524", 5.617, 5.617),
    ("local-mixed-2026-07__4087418227", 5.991, 5.991),
    ("local-mixed-2026-07__1063588653", 4.103, 4.103),
    ("local-mixed-2026-07__1755788551", 36.830, 36.830),
    ("local-mixed-2026-07__9070200412", 3.622, 3.622),
    ("local-mixed-2026-07__9318140329", 3.151, 3.151),
    ("local-mixed-2026-07__4589763049", 4.061, 4.061),
    ("local-mixed-2026-07__0229019868", 23.371, 23.371),
    ("local-mixed-2026-07__9063680763", 17.749, 17.749),
    ("local-mixed-2026-07__0550549226", 3.032, 3.032),
    ("local-mixed-2026-07__3153320186", 6.197, 6.197),
    ("local-mixed-2026-07__6762931572", 13.810, 13.810),
    ("local-mixed-2026-07__6661213999", 14.762, 14.762),
    ("local-mixed-2026-07__5983653715", 14.564, 14.564),
    ("local-mixed-2026-07__1372685658", 5.547, 5.547),
    ("local-mixed-2026-07__3528755502", 8.622, 8.622),
    ("local-mixed-2026-07__7278483295", 28.388, 28.388),
    ("local-mixed-2026-07__8647104982", 7.607, 7.607),
    ("owner-x2dii-2026-08__B0000044", 20.267, 20.267),
    ("owner-x2dii-2026-08__B0000125", 13.905, 13.905),
    ("owner-x2dii-2026-08__B0000203", 9.547, 9.547),
    ("owner-x2dii-2026-08__B0000204", 8.632, 8.632),
    ("owner-x2dii-2026-08__B00002333FR1756808191", 20.788, 20.788),
    ("owner-x2dii-2026-08__B0000239", 16.981, 16.981),
    ("owner-x2dii-2026-08__B0000241", 17.460, 17.460),
    ("owner-x2dii-2026-08__B0000246", 12.230, 12.230),
    ("owner-x2dii-2026-08__B0000251", 7.951, 7.951),
]


class TestSummarizeRecordedRun83Pair(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 83쌍(74쌍 확장 + owner-x2dii
    9쌍) LOO 결과를 재현하는 회귀 테스트 - 13쌍 결과와 마찬가지로 완전히
    평평하다(83개 폴드 전부 (1.0, 1.0) 선택)."""

    def setUp(self):
        names = [r[0] for r in _RECORDED_83_PAIR_RUN]
        baseline_de = [r[1] for r in _RECORDED_83_PAIR_RUN]
        best_de = [r[2] for r in _RECORDED_83_PAIR_RUN]
        self.s = summarize(baseline_de, best_de, names)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_baseline"], 9.165, places=3)
        self.assertAlmostEqual(self.s["mean_best"], 9.165, places=3)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["n_better"], 0)
        self.assertEqual(self.s["n_worse"], 0)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["sign_test_p"], 1.0, places=9)

    def test_t_stat_is_inf_for_zero_variance_diffs(self):
        self.assertTrue(math.isinf(self.s["t_stat"]))


if __name__ == "__main__":
    unittest.main()
