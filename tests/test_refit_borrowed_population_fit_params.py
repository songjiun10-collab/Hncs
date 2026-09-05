"""`tools/refit_borrowed_population_fit_params.py` 단위 테스트 + 기록된 실행
회귀 테스트.

이 도구가 잡아낸 것: Leica(n=15)는 `shoulder_start` 재적합이 CI를 아슬아슬
하게 0 배제(p=0.3018, `film_curve` 실제 clamp값 0.999에 경계 hit)해 판정을
보류했고, Sony(n=22)는 CI가 0을 포함해 명확히 null이었다. 두 브랜드 모두
기준선을 일부러 틀리게 만든 양성 대조에서는 도구가 열화를 정확히 잡아냈다.
이 숫자들은 `hybrid_engine/EVALUATION.md`에 실려 있으므로 커밋된 리포트에서
다시 확인한다.
"""
import json
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import refit_borrowed_population_fit_params as refit

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASETS = os.path.join(BASE, "datasets")


class TestSignTestP(unittest.TestCase):
    def test_all_wins_is_significant(self):
        self.assertLess(refit._sign_test_p(15, 0), 0.001)

    def test_even_split_is_one(self):
        self.assertAlmostEqual(refit._sign_test_p(5, 5), 1.0)

    def test_no_pairs_is_one(self):
        self.assertEqual(refit._sign_test_p(0, 0), 1.0)

    def test_matches_math_comb_by_hand_for_small_n(self):
        # n=4, wins=3: 2*sum(C(4,0..1))/2^4 = 2*(1+4)/16 = 0.625
        self.assertAlmostEqual(refit._sign_test_p(3, 1), 0.625)


class TestSummarize(unittest.TestCase):
    def test_identical_arrays_is_inconclusive(self):
        base = [10.0, 12.0, 8.0, 9.0, 11.0]
        stats = refit.summarize(base, base)
        self.assertTrue(stats["inconclusive"])
        self.assertEqual(stats["verdict"], "판정 보류 (CI가 0 포함)")

    def test_uniform_improvement_is_refit_wins(self):
        base = [10.0, 12.0, 8.0, 9.0, 11.0, 10.5, 9.5, 11.5]
        new = [x - (1.5 + 0.1 * i) for i, x in enumerate(base)]
        stats = refit.summarize(base, new)
        self.assertFalse(stats["inconclusive"])
        self.assertEqual(stats["verdict"], "재적합 우세")
        self.assertEqual(stats["wins"], len(base))
        self.assertEqual(stats["losses"], 0)
        self.assertLess(stats["ci_lo"], stats["ci_hi"])
        self.assertGreater(stats["ci_lo"], 0.0)

    def test_uniform_regression_is_current_wins(self):
        base = [10.0, 12.0, 8.0, 9.0, 11.0, 10.5, 9.5, 11.5]
        new = [x + 2.0 for x in base]
        stats = refit.summarize(base, new)
        self.assertEqual(stats["verdict"], "현행 차용값 우세")

    def test_deterministic_seed(self):
        base = [10.0, 12.0, 8.0, 9.0, 11.0, 7.0, 13.0]
        new = [9.0, 11.5, 8.5, 8.0, 10.0, 7.5, 12.0]
        a = refit.summarize(base, new, seed=0)
        b = refit.summarize(base, new, seed=0)
        self.assertEqual(a["ci_lo"], b["ci_lo"])
        self.assertEqual(a["ci_hi"], b["ci_hi"])


class TestApplyLook(unittest.TestCase):
    def test_output_shape_and_dtype_match_input(self):
        img = (np.random.default_rng(0).random((20, 20, 3)) * 255).astype(np.uint8)
        out = refit.apply_look(img, toe_lift=0.0, shoulder_start=0.78,
                               white_point=1.0, clahe_clip=1.25)
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, img.dtype)

    def test_identity_curve_with_no_clahe_leaves_luminance_ordering(self):
        # toe_lift=0, shoulder_start=1.0(사실상 항등), clahe_clip을 낮게 둬도
        # 완전히 꺼지진 않지만 순서는 보존되어야 한다: 더 밝은 입력 -> 더 밝은 출력
        dark = np.full((16, 16, 3), 40, dtype=np.uint8)
        bright = np.full((16, 16, 3), 200, dtype=np.uint8)
        out_dark = refit.apply_look(dark, 0.0, 0.999, 1.0, 0.4)
        out_bright = refit.apply_look(bright, 0.0, 0.999, 1.0, 0.4)
        self.assertLess(out_dark.mean(), out_bright.mean())


class TestLoadPairs(unittest.TestCase):
    def test_missing_manifest_is_skipped_not_raised(self):
        grids, tg, confirms, tc, names = refit.load_pairs(
            ["datasets/__does_not_exist__"])
        self.assertEqual((grids, tg, confirms, tc, names), ([], [], [], [], []))


class TestRecordedRefit(unittest.TestCase):
    """EVALUATION.md의 Leica/Sony 재적합 숫자가 커밋된 리포트와 일치하는지."""

    def _load(self, name):
        path = os.path.join(DATASETS, name)
        if not os.path.exists(path):
            raise unittest.SkipTest(f"리포트 없음: {path}")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_leica_real_is_edge_hit_and_weakly_significant(self):
        d = self._load("refit_borrowed_leica.json")
        self.assertEqual(d["n_pairs"], 15)
        self.assertEqual(d["full_sample_combo"], [0.999, 1.25])
        self.assertEqual(d["params_on_grid_edge"], ["shoulder_start"])
        self.assertTrue(d["loo_unanimous"])
        s = d["stats"]
        self.assertAlmostEqual(s["mean_base"], 8.1163, places=4)
        self.assertAlmostEqual(s["mean_new"], 8.0432, places=4)
        self.assertEqual((s["wins"], s["losses"]), (10, 5))
        self.assertGreater(s["p_value"], 0.05)  # 부호검정 자체는 유의하지 않음
        self.assertGreater(s["ci_lo"], 0.0)  # 그래도 CI는 0을 배제
        self.assertFalse(s["inconclusive"])
        self.assertFalse(d["is_positive_control"])

    def test_sony_real_is_null(self):
        d = self._load("refit_borrowed_sony.json")
        self.assertEqual(d["n_pairs"], 22)
        self.assertEqual(d["params_on_grid_edge"], [])
        s = d["stats"]
        self.assertLessEqual(s["ci_lo"], 0.0)
        self.assertGreaterEqual(s["ci_hi"], 0.0)
        self.assertTrue(s["inconclusive"])
        self.assertFalse(d["criterion_passed"])
        self.assertFalse(d["is_positive_control"])

    def test_leica_control_detects_injected_regression(self):
        d = self._load("refit_borrowed_leica_control.json")
        self.assertTrue(d["is_positive_control"])
        s = d["stats"]
        self.assertEqual(s["verdict"], "재적합 우세")
        self.assertLess(s["p_value"], 0.01)
        self.assertGreater(s["ci_lo"], 0.0)

    def test_sony_control_detects_injected_regression(self):
        d = self._load("refit_borrowed_sony_control.json")
        self.assertTrue(d["is_positive_control"])
        s = d["stats"]
        self.assertEqual(s["verdict"], "재적합 우세")
        self.assertLess(s["p_value"], 0.01)
        self.assertGreater(s["ci_lo"], 0.0)

    def test_neither_real_run_modifies_shipped_code(self):
        for name in ("refit_borrowed_leica.json", "refit_borrowed_sony.json"):
            d = self._load(name)
            self.assertFalse(d["modifies_shipped_code"])


if __name__ == "__main__":
    unittest.main()
