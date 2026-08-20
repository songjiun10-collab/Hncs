import os
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calibrate import _CONTAMINATED_OFFICIAL_PAIRS, _generation_for, _resolve_pairs


class TestResolvePairsExcludesContaminated(unittest.TestCase):
    """2026-08 EXIF Software 태그 재검증(docs/measurements.md)에서 확인된
    편집 오염 9쌍이 _resolve_pairs()의 반환값에서 실제로 빠지는지 -
    네트워크(download)와 로컬 기여 데이터셋(collect_local_pairs)은 CI에
    없으므로 모킹한다(tests/CLAUDE.md)."""

    @patch("tools.calibrate.collect_local_pairs", return_value=[])
    @patch("tools.calibrate.download", return_value=True)
    def test_contaminated_official_pairs_excluded(self, mock_download, mock_local):
        pairs = _resolve_pairs()
        names = {p["filename"] for p in pairs}
        self.assertTrue(names.isdisjoint(_CONTAMINATED_OFFICIAL_PAIRS))

    @patch("tools.calibrate.collect_local_pairs", return_value=[])
    @patch("tools.calibrate.download", return_value=True)
    def test_exactly_four_clean_official_pairs_remain(self, mock_download, mock_local):
        pairs = _resolve_pairs()
        self.assertEqual(len(pairs), 4)
        self.assertEqual({p["filename"] for p in pairs},
                          {"00378.jpg", "02709.jpg", "x1d-ii-xcd45p-01.jpg",
                           "x1d-ii-xcd45p-02.jpg"})


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


class TestFoldBestComboMatchesRecompute(unittest.TestCase):
    """grid_search_loo()의 _fold_best_combo()가 쓰는 뺄셈 트릭(전체 합계에서
    held-out 열 하나만 빼기)이 매 폴드 재계산(held-out 뺀 나머지로 처음부터
    평균)과 동일한 폴드별 최적 조합을 고르는지 - TestSubtractionLooMatchesRecompute
    와 같은 성격의 검증."""

    def test_subtraction_equals_full_recompute(self):
        from tools.calibrate import _fold_best_combo

        rng = np.random.default_rng(7)
        n_combos, n_pairs = 12, 6
        sqerr = rng.random((n_combos, n_pairs))

        for held_out in range(n_pairs):
            got = _fold_best_combo(sqerr, held_out)

            train_idx = [j for j in range(n_pairs) if j != held_out]
            train_mean_full = sqerr[:, train_idx].mean(axis=1)
            expected = int(np.argmin(train_mean_full))

            self.assertEqual(got, expected)

    def test_picks_the_combo_with_lower_error_on_remaining_pairs(self):
        from tools.calibrate import _fold_best_combo

        # combo 0이 페어 1에서만 나쁘고 나머지에선 좋음 - held_out=1을 빼면
        # combo 0이 이겨야 한다.
        sqerr = np.array([
            [1.0, 100.0, 1.0],  # combo 0
            [5.0, 5.0, 5.0],    # combo 1
        ])
        self.assertEqual(_fold_best_combo(sqerr, 1), 0)


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


# 실제 74쌍 regularize LOO 재실행 기록값(2026-08,
# /tmp/calibrate_regularize_74pair_v2.log, run_regularize()의 폴드별
# print에서 추출) - brands/hasselblad_learned.py와 docs/measurements.md의
# "하이브리드(regularize) 재검증(2026-08)" 절에 실린 것과 정확히 같다
# (v12(λ=0, _build_lut_from_counts의 평균 기반 근사) vs 최적
# 하이브리드(λ=1e9 = 사실상 순수 파라메트릭 v11)).
# (name, v12_e, hybrid_e)
_RECORDED_HYBRID_VS_V12_RUN = [
    ("x1d-II-sample-02.jpg", 17.543, 18.438),
    ("x1d-II-sample-09.jpg", 0.341, 1.000),
    ("B0000994.jpg", 42.646, 57.454),
    ("B0001395.jpg", 34.917, 33.980),
    ("x1d-xcd45-01.jpg", 6.016, 27.854),
    ("x1d-xcd45-03.jpg", 28.792, 4.540),
    ("x1d-xcd45-04.jpg", 42.197, 33.340),
    ("x1d-ii-xcd45p-01.jpg", 34.052, 10.930),
    ("x1d-ii-xcd45p-02.jpg", 29.138, 12.972),
    ("x1d-II-sample-01.jpg", 20.495, 41.387),
    ("x1d-II-sample-06.jpg", 23.824, 25.120),
    ("02709.jpg", 27.901, 3.604),
    ("00378.jpg", 31.852, 20.314),
    ("local-mixed-2026-07__6507810936", 43.551, 31.482),
    ("local-mixed-2026-07__0149725587", 39.817, 2.499),
    ("local-mixed-2026-07__8204307982", 38.787, 1.471),
    ("local-mixed-2026-07__3832345792", 1.931, 4.132),
    ("local-mixed-2026-07__5537240075", 30.789, 8.622),
    ("local-mixed-2026-07__0587181218", 22.838, 8.396),
    ("local-mixed-2026-07__7971015535", 33.828, 9.288),
    ("local-mixed-2026-07__6311094775", 24.940, 8.814),
    ("local-mixed-2026-07__6787000086", 33.051, 8.554),
    ("local-mixed-2026-07__7826992126", 25.784, 20.639),
    ("local-mixed-2026-07__5533274085", 32.816, 24.387),
    ("local-mixed-2026-07__1094220000", 27.880, 8.845),
    ("local-mixed-2026-07__8082395282", 36.786, 2.727),
    ("local-mixed-2026-07__1932636179", 33.788, 19.695),
    ("local-mixed-2026-07__3953661245", 32.780, 8.649),
    ("local-mixed-2026-07__8127122405", 45.766, 15.180),
    ("local-mixed-2026-07__5746737497", 40.795, 7.380),
    ("local-mixed-2026-07__9515423899", 43.119, 2.596),
    ("local-mixed-2026-07__6454535758", 31.798, 24.725),
    ("local-mixed-2026-07__8742913299", 37.747, 10.858),
    ("local-mixed-2026-07__7492975828", 42.760, 6.441),
    ("local-mixed-2026-07__7321006825", 32.784, 24.362),
    ("local-mixed-2026-07__6660888354", 35.786, 4.511),
    ("local-mixed-2026-07__4236625428", 37.794, 21.017),
    ("local-mixed-2026-07__8581844385", 28.912, 20.724),
    ("local-mixed-2026-07__7121592185", 38.727, 18.974),
    ("local-mixed-2026-07__3766372330", 29.969, 22.000),
    ("local-mixed-2026-07__7732046028", 23.790, 7.211),
    ("local-mixed-2026-07__0908944042", 26.826, 24.461),
    ("local-mixed-2026-07__1917191504", 37.784, 6.555),
    ("local-mixed-2026-07__9011626130", 36.513, 8.928),
    ("local-mixed-2026-07__5310704161", 22.555, 28.474),
    ("local-mixed-2026-07__3683076943", 24.823, 6.622),
    ("local-mixed-2026-07__7406451876", 35.801, 8.568),
    ("local-mixed-2026-07__6519755969", 0.805, 24.409),
    ("local-mixed-2026-07__3333340029", 2.234, 22.644),
    ("local-mixed-2026-07__9479682988", 33.353, 19.602),
    ("local-mixed-2026-07__5385314660", 32.787, 6.345),
    ("local-mixed-2026-07__9247740424", 42.490, 1.710),
    ("local-mixed-2026-07__5715595764", 30.549, 12.458),
    ("local-mixed-2026-07__6704898202", 38.782, 22.613),
    ("local-mixed-2026-07__6340134840", 33.864, 8.054),
    ("local-mixed-2026-07__9928856380", 36.909, 22.409),
    ("local-mixed-2026-07__0758706524", 22.991, 22.482),
    ("local-mixed-2026-07__4087418227", 0.739, 0.000),
    ("local-mixed-2026-07__1063588653", 22.769, 12.167),
    ("local-mixed-2026-07__1755788551", 35.811, 4.511),
    ("local-mixed-2026-07__9070200412", 38.802, 4.727),
    ("local-mixed-2026-07__9318140329", 37.789, 3.727),
    ("local-mixed-2026-07__4589763049", 32.788, 20.788),
    ("local-mixed-2026-07__0229019868", 37.786, 11.345),
    ("local-mixed-2026-07__9063680763", 39.785, 5.727),
    ("local-mixed-2026-07__0550549226", 39.846, 2.471),
    ("local-mixed-2026-07__3153320186", 41.524, 5.482),
    ("local-mixed-2026-07__6762931572", 36.690, 49.904),
    ("local-mixed-2026-07__6661213999", 51.228, 61.383),
    ("local-mixed-2026-07__5983653715", 52.756, 57.371),
    ("local-mixed-2026-07__1372685658", 38.784, 26.014),
    ("local-mixed-2026-07__3528755502", 39.488, 30.273),
    ("local-mixed-2026-07__7278483295", 38.690, 55.906),
    ("local-mixed-2026-07__8647104982", 33.785, 13.977),
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """brands/hasselblad_learned.py·docs/measurements.md에 기록된 실제
    74쌍 regularize LOO 결과(v12(λ=0) vs 최적 하이브리드(λ=1e9=v11))를
    재현하는 회귀 테스트."""

    def test_reproduces_documented_means(self):
        from tools.calibrate import summarize
        s = summarize(_RECORDED_HYBRID_VS_V12_RUN)
        self.assertAlmostEqual(s["mean_a"], 31.716, places=3)
        self.assertAlmostEqual(s["mean_b"], 16.989, places=3)

    def test_reproduces_documented_improvement_pct(self):
        from tools.calibrate import summarize
        s = summarize(_RECORDED_HYBRID_VS_V12_RUN)
        self.assertAlmostEqual(s["improvement_pct"], 46.4, places=1)

    def test_reproduces_documented_win_loss(self):
        from tools.calibrate import summarize
        s = summarize(_RECORDED_HYBRID_VS_V12_RUN)
        self.assertEqual(s["b_wins"], 60)
        self.assertEqual(s["a_wins"], 14)

    def test_reproduces_documented_sign_test_p(self):
        from tools.calibrate import summarize
        s = summarize(_RECORDED_HYBRID_VS_V12_RUN)
        self.assertAlmostEqual(s["sign_test_p"], 6.22176141634788e-08, places=9)


if __name__ == "__main__":
    unittest.main()
