"""`tools/evaluate_dcp_huesatmap_full_srgb.py`의 순수 함수 단위 테스트 +
`hybrid_engine/EVALUATION.md`에 기록된 실제 LOO 결과의 재현 회귀 테스트.

기록된 표를 다시 `summarize()`에 넣어 판정(성립/보류)이 그대로 나오는지
확인한다 - 실험을 재실행하지 않고도(전체 스윕은 9장 RAW 디코드가 필요해
수 분 걸린다) 문서의 통계를 감사할 수 있게 하는 것이 목적
(`hybrid_engine/CLAUDE.md`의 recorded-run 회귀 테스트 관례).
"""
import unittest

import numpy as np

from tools.evaluate_dcp_huesatmap_full_srgb import (
    _apply_tables, _fit_tables, _hsv_to_rgb, _interp_division, _rgb_to_hsv,
    _wrap_deg, summarize,
)

# hybrid_engine/EVALUATION.md "HueSatMap 전자유도 LOO"(2026-09-04) 표의
# N=4 두 행. 값은 실행 리포트
# datasets/hasselblad/contributed/kmichels-x2dii-2026-07/
# huesatmap_full_srgb_loo_report.json 의 per_image_* 배열에서 전사
# (이미지 순서 B_31325~B_31333.3FR).
_RECORDED_MATRIX_ONLY = [
    2.9129647714, 2.5971802662, 2.2127192832, 2.0514498249, 2.7092837026,
    2.7428207020, 2.6481117124, 2.7599943083, 2.7132909807,
]
_RECORDED_N4_HUE_SAT = [
    2.6512899178, 2.3233118304, 1.9673132724, 1.8664730406, 2.6002767590,
    2.6262033500, 2.5185105863, 2.6491688475, 2.5932799207,
]
_RECORDED_N4_HUE_SAT_VAL = [
    3.2385056153, 2.8612005522, 2.2858746954, 1.9829458614, 2.1734659579,
    2.2008526547, 2.1177880185, 2.2190109679, 2.1744142062,
]


class TestWrapDeg(unittest.TestCase):
    def test_wraps_into_symmetric_range(self):
        self.assertAlmostEqual(_wrap_deg(370.0), 10.0)
        self.assertAlmostEqual(_wrap_deg(-190.0), 170.0)
        self.assertAlmostEqual(_wrap_deg(180.0), -180.0)


class TestHsvRoundTrip(unittest.TestCase):
    def test_rgb_hsv_rgb_is_identity(self):
        rng = np.random.RandomState(0)
        rgb = rng.rand(200, 3)
        h, s, v = _rgb_to_hsv(rgb)
        back = _hsv_to_rgb(h, s, v)
        self.assertLess(float(np.max(np.abs(rgb - back))), 1e-9)

    def test_neutral_has_zero_saturation(self):
        rgb = np.array([[0.4, 0.4, 0.4], [1.0, 1.0, 1.0]])
        _, s, v = _rgb_to_hsv(rgb)
        self.assertLess(float(np.max(s)), 1e-9)
        self.assertAlmostEqual(float(v[0]), 0.4)


class TestInterpDivision(unittest.TestCase):
    def test_hits_table_values_at_division_centers(self):
        table = np.array([1.0, 2.0, 3.0, 4.0])
        got = _interp_division(np.array([0.0, 90.0, 180.0, 270.0]), table, 4)
        np.testing.assert_allclose(got, table)

    def test_interpolates_linearly_between_centers(self):
        table = np.array([0.0, 4.0, 0.0, 0.0])
        self.assertAlmostEqual(float(_interp_division(np.array([45.0]), table, 4)[0]), 2.0)

    def test_circular_flag_takes_short_way_around(self):
        # 350도 -> 10도는 순환 보간에서 +20도 이동이어야 한다(-340도가 아니라).
        table = np.array([350.0, 10.0, 0.0, 0.0])
        mid = float(_interp_division(np.array([45.0]), table, 4, circular_deg=True)[0])
        self.assertAlmostEqual(mid, 360.0)  # 350 + 0.5*20


class TestFitTables(unittest.TestCase):
    def test_recovers_a_known_uniform_hue_shift(self):
        """예측 hue가 참조보다 일정하게 -20도 틀어져 있으면 학습된 테이블은
        전 division에서 +20도가 나와야 한다."""
        rng = np.random.RandomState(1)
        ref_h = rng.rand(24) * 360.0
        ref_s = np.full(24, 0.6)
        ref_v = np.full(24, 0.5)
        pred = [(( ref_h - 20.0) % 360.0, ref_s.copy(), ref_v.copy())]
        tables = _fit_tables(pred, ref_h, ref_s, ref_v, n_divisions=4)
        np.testing.assert_allclose(tables[0], np.full(4, 20.0), atol=1e-6)
        np.testing.assert_allclose(tables[1], np.ones(4), atol=1e-6)
        np.testing.assert_allclose(tables[2], np.ones(4), atol=1e-6)

    def test_recovers_a_known_uniform_saturation_scale(self):
        rng = np.random.RandomState(2)
        ref_h = rng.rand(24) * 360.0
        ref_s = np.full(24, 0.6)
        ref_v = np.full(24, 0.5)
        pred = [(ref_h.copy(), ref_s / 2.0, ref_v.copy())]
        tables = _fit_tables(pred, ref_h, ref_s, ref_v, n_divisions=4)
        np.testing.assert_allclose(tables[1], np.full(4, 2.0), atol=1e-6)

    def test_use_sat_false_leaves_saturation_untouched(self):
        h = np.array([10.0, 100.0])
        s = np.array([0.5, 0.5])
        v = np.array([0.5, 0.5])
        tables = np.array([[0.0] * 4, [2.0] * 4, [2.0] * 4], dtype=float)
        _, new_s, new_v = _apply_tables(h, s, v, tables, 4, use_sat=False, use_val=False)
        np.testing.assert_allclose(new_s, s)
        np.testing.assert_allclose(new_v, v)

    def test_use_sat_true_applies_the_scale_and_clips(self):
        h = np.array([10.0])
        s = np.array([0.7])
        v = np.array([0.5])
        tables = np.array([[0.0] * 4, [2.0] * 4, [1.0] * 4], dtype=float)
        _, new_s, _ = _apply_tables(h, s, v, tables, 4, use_sat=True, use_val=False)
        self.assertAlmostEqual(float(new_s[0]), 1.0)  # 1.4 -> [0,1] 클립


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md "HueSatMap 전자유도 LOO"(2026-09-04)에
    기록된 N=4 두 행을 재현 - 재실행 없이 판정을 감사할 수 있게 한다."""

    def test_hue_sat_is_statistically_established(self):
        s = summarize("a", _RECORDED_MATRIX_ONLY, "b", _RECORDED_N4_HUE_SAT)
        self.assertAlmostEqual(s["mean_a"], 2.5942, places=4)
        self.assertAlmostEqual(s["mean_b"], 2.4218, places=4)
        self.assertAlmostEqual(s["improvement_pct"], 6.65, places=2)
        self.assertEqual((s["wins"], s["losses"]), (9, 0))
        self.assertAlmostEqual(s["p_value"], 0.00390625, places=9)
        self.assertAlmostEqual(s["ci_lo"], 0.1316, places=4)
        self.assertAlmostEqual(s["ci_hi"], 0.2169, places=4)
        self.assertFalse(s["inconclusive"])

    def test_hue_sat_val_is_inconclusive_despite_better_mean(self):
        """평균은 hue+sat보다 낮은데(2.3616 < 2.4218) CI가 0을 포함해 판정
        보류다 - 이 절의 결론 자체가 이 대비다."""
        s = summarize("a", _RECORDED_MATRIX_ONLY, "b", _RECORDED_N4_HUE_SAT_VAL)
        self.assertAlmostEqual(s["mean_b"], 2.3616, places=4)
        self.assertAlmostEqual(s["improvement_pct"], 8.97, places=2)
        self.assertEqual((s["wins"], s["losses"]), (6, 3))
        self.assertAlmostEqual(s["p_value"], 0.5078125, places=9)
        self.assertAlmostEqual(s["ci_lo"], -0.0070, places=4)
        self.assertAlmostEqual(s["ci_hi"], 0.4504, places=4)
        self.assertTrue(s["inconclusive"])
        self.assertLess(s["mean_b"], 2.4218)  # 평균만 보면 더 좋아 보인다

    def test_documented_conclusion_sub_2_not_reached(self):
        """문서의 결론('1점대는 안 된다')이 기록된 값에서 그대로 따라 나오는지."""
        established = summarize("a", _RECORDED_MATRIX_ONLY, "b", _RECORDED_N4_HUE_SAT)
        self.assertGreater(established["mean_b"], 2.0)


if __name__ == "__main__":
    unittest.main()
