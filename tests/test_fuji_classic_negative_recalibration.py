"""Classic Negative 재보정 계열 도구들의 헬퍼 단위 테스트 + 기록된 실행
회귀 테스트.

`tests/test_evaluate_dcp_huesatmap_full_srgb.py`와 같은 형태다: 통계 헬퍼가
맞게 동작하는지 따로 확인하고, `hybrid_engine/EVALUATION.md`에 실린 수치를
커밋된 리포트 JSON에서 되먹여 `summarize()`가 같은 값을 다시 내는지 본다.
숫자가 재계산되지 않으면 문서의 주장이 깨진 것이다.
"""
import json
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tools import diagnose_fuji_autobright_vs_look as ab
from tools import diagnose_fuji_neutral_render_offset as neutral
from tools import evaluate_fuji_classic_negative_v2_grid as v2
from tools import probe_fuji_classic_negative_v2_boundary as boundary

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(BASE, "datasets", "fuji", "contributed", "local-work-2026-08")


def _load(name):
    p = os.path.join(SET_DIR, name)
    if not os.path.exists(p):
        raise unittest.SkipTest(f"리포트 없음: {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class TestSignTest(unittest.TestCase):
    def test_all_wins_is_two_over_two_to_the_n(self):
        # 9승 0패 -> 2 * C(9,0) / 2^9
        self.assertAlmostEqual(v2._sign_test_p(9, 0), 2.0 / 512, places=12)

    def test_even_split_is_one(self):
        self.assertEqual(v2._sign_test_p(5, 5), 1.0)

    def test_no_observations_is_one(self):
        self.assertEqual(v2._sign_test_p(0, 0), 1.0)

    def test_symmetric_in_wins_and_losses(self):
        self.assertEqual(v2._sign_test_p(12, 3), v2._sign_test_p(3, 12))

    def test_never_exceeds_one(self):
        for w in range(0, 8):
            for l in range(0, 8):
                self.assertLessEqual(v2._sign_test_p(w, l), 1.0)

    def test_two_modules_agree(self):
        # 형제 스크립트들이 각자 복사해 쓰는 구현이라 값이 갈리면 안 된다
        for w, l in ((9, 0), (5, 5), (12, 3), (1, 20)):
            self.assertAlmostEqual(v2._sign_test_p(w, l), ab._sign_test_p(w, l),
                                   places=12)


class TestSummarize(unittest.TestCase):
    def test_identical_inputs_are_inconclusive(self):
        vals = [3.0, 4.0, 5.0, 6.0]
        s = v2.summarize(vals, list(vals), "a", "b")
        self.assertTrue(s["inconclusive"])
        self.assertEqual(s["wins"], 0)
        self.assertEqual(s["losses"], 0)

    def test_uniform_improvement_excludes_zero(self):
        base = [10.0] * 30
        new = [9.0] * 30
        s = v2.summarize(base, new, "base", "new")
        self.assertFalse(s["inconclusive"])
        self.assertEqual(s["wins"], 30)
        self.assertAlmostEqual(s["mean_base"] - s["mean_new"], 1.0, places=9)

    def test_is_deterministic_under_fixed_seed(self):
        rng = np.random.default_rng(7)
        base = list(rng.normal(12, 2, 40))
        new = list(rng.normal(11, 2, 40))
        a = v2.summarize(base, new, "a", "b")
        b = v2.summarize(base, new, "a", "b")
        self.assertEqual(a["ci_lo"], b["ci_lo"])
        self.assertEqual(a["ci_hi"], b["ci_hi"])

    def test_ci_brackets_the_mean_difference(self):
        rng = np.random.default_rng(11)
        base = list(rng.normal(16, 3, 47))
        new = list(rng.normal(15, 3, 47))
        s = v2.summarize(base, new, "a", "b")
        diff = s["mean_base"] - s["mean_new"]
        self.assertLessEqual(s["ci_lo"], diff)
        self.assertGreaterEqual(s["ci_hi"], diff)


class TestEmptyFujiManifest(unittest.TestCase):
    """빈 manifest는 통계를 계산하거나 NaN 리포트를 쓰면 안 된다."""

    class _TrackingManifest(io.StringIO):
        def __init__(self):
            super().__init__("filename_jpeg,filename_raw\n")
            self.was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    def test_empty_manifest_fails_before_statistics_and_closes_csv(self):
        # 이 검사가 빠지면 빈 데이터셋이 bootstrap의 high <= 0 / min(empty)나
        # NaN 리포트까지 진행한다. manifest는 명시적으로 닫혀야 한다.
        modules = (v2, ab, neutral, boundary)
        with tempfile.TemporaryDirectory() as directory:
            for module in modules:
                manifest = self._TrackingManifest()

                def open_manifest(path, *args, **kwargs):
                    self.assertEqual(path, os.path.join(directory, "manifest.csv"))
                    return manifest

                with patch.object(module, "SET_DIR", directory), \
                     patch("builtins.open", side_effect=open_manifest), \
                     patch.object(sys, "argv", [module.__name__]), \
                     redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(ValueError, "usable.*pairs"):
                        module.main()
                self.assertTrue(manifest.was_closed, module.__name__)


class TestGridDefinition(unittest.TestCase):
    def test_white_point_cannot_exceed_one(self):
        # 이 상한이 밝기 보정 탈출구를 막는 장치다 - 넓히면 실험의 전제가 깨진다
        self.assertLessEqual(max(v2.WHITE_POINTS), 1.0)

    def test_saturation_floor_was_widened_to_020(self):
        self.assertAlmostEqual(min(v2.SAT_MULTS), 0.20, places=9)

    def test_combo_count_matches_axes(self):
        self.assertEqual(
            len(v2.COMBOS),
            len(v2.TOE_LIFTS) * len(v2.SHOULDER_STARTS)
            * len(v2.WHITE_POINTS) * len(v2.SAT_MULTS))

    def test_edge_detection_flags_only_extremes(self):
        self.assertEqual(v2._on_edge((0.0, 0.78, 1.0, 0.40)),
                         ["toe_lift", "white_point"])
        self.assertEqual(v2._on_edge((0.02, 0.78, 0.95, 0.40)), [])


class TestApplyCandidateContract(unittest.TestCase):
    def test_preserves_shape_and_dtype(self):
        rng = np.random.default_rng(3)
        img = rng.integers(0, 256, (24, 32, 3), dtype=np.uint8)
        out = v2.apply_candidate(img, 0.0, 0.78, 1.0, 0.40)
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, np.uint8)

    def test_saturation_multiplier_reduces_saturation(self):
        rng = np.random.default_rng(4)
        img = rng.integers(0, 256, (32, 32, 3), dtype=np.uint8)
        import cv2
        low = v2.apply_candidate(img, 0.0, 0.78, 1.0, 0.20)
        high = v2.apply_candidate(img, 0.0, 0.78, 1.0, 1.0)
        s_low = cv2.cvtColor(low, cv2.COLOR_BGR2HSV)[:, :, 1].mean()
        s_high = cv2.cvtColor(high, cv2.COLOR_BGR2HSV)[:, :, 1].mean()
        self.assertLess(s_low, s_high)


class TestDeltaEColorDomain(unittest.TestCase):
    def test_grid_converts_bgr_uint8_inputs_before_delta_e(self):
        """Removing the BGR-to-linear conversion must expose raw bytes here."""
        grid_bgr = np.array([[[0, 0, 255]]], dtype=np.uint8)
        target_bgr = np.array([[[128, 64, 32]]], dtype=np.uint8)
        received = []

        def capture_delta_e(actual, target):
            received.append((actual, target))
            return 0.0

        with patch.object(v2, "COMBOS", ((0.0, 0.78, 1.0, 0.40),)), \
             patch.object(v2, "mean_delta_e", side_effect=capture_delta_e):
            v2._best_combo([0], [grid_bgr], [target_bgr])

        actual, target = received[0]
        self.assertEqual(actual.dtype, np.float64)
        self.assertEqual(target.dtype, np.float64)
        self.assertLessEqual(float(actual.max()), 1.0)
        np.testing.assert_allclose(
            target,
            np.array([[[0.01444384, 0.05126946, 0.21586050]]]),
            atol=1e-8,
        )

    def test_l_channel_residual_imports_without_private_colour_helper(self):
        """The research verifier must run with colour-science 0.4.4's public API."""
        import hybrid_engine.verify_l_channel_residual as residual

        self.assertTrue(callable(residual._cie2000_intermediate_terms))

    def test_l_channel_terms_treat_signed_zero_as_achromatic(self):
        """Signed zero in an achromatic Lab input must not change CIEDE2000 terms."""
        import hybrid_engine.verify_l_channel_residual as residual

        signed_zero = np.array([[50.0, -0.0, -0.0]])
        zero = np.array([[50.0, 0.0, 0.0]])
        chromatic = np.array([[55.0, 20.0, 10.0]])
        signed_terms = residual._cie2000_intermediate_terms(signed_zero, chromatic)
        zero_terms = residual._cie2000_intermediate_terms(zero, chromatic)

        self.assertEqual(len(signed_terms), 7)
        for signed, expected in zip(signed_terms, zero_terms):
            np.testing.assert_allclose(signed, expected, atol=1e-12)


class TestRecordedV2Run(unittest.TestCase):
    """EVALUATION.md의 v2 수치가 커밋된 리포트에서 다시 계산되는지."""

    @classmethod
    def setUpClass(cls):
        cls.rep = _load("classic_negative_v2_grid_report.json")

    def test_recomputes_the_recorded_statistics(self):
        s = v2.summarize(self.rep["delta_e_current"], self.rep["delta_e_v2"],
                         "현행", "v2")
        rec = self.rep["stats"]
        for k in ("mean_base", "mean_new", "ci_lo", "ci_hi", "p_value"):
            self.assertAlmostEqual(s[k], rec[k], places=9, msg=k)
        self.assertEqual(s["wins"], rec["wins"])
        self.assertEqual(s["losses"], rec["losses"])

    def test_recorded_numbers_match_evaluation_md(self):
        rec = self.rep["stats"]
        self.assertEqual(self.rep["n_pairs"], 47)
        self.assertAlmostEqual(rec["mean_base"], 15.2787, places=3)
        self.assertAlmostEqual(rec["mean_new"], 12.3201, places=3)
        self.assertEqual((rec["wins"], rec["losses"]), (46, 1))
        self.assertAlmostEqual(rec["ci_lo"], 2.5039, places=3)
        self.assertAlmostEqual(rec["ci_hi"], 3.4143, places=3)

    def test_criterion_passed_and_ci_excludes_zero(self):
        self.assertTrue(self.rep["criterion_passed"])
        self.assertFalse(self.rep["stats"]["inconclusive"])
        self.assertGreater(self.rep["stats"]["ci_lo"], 0.0)

    def test_shipped_code_was_not_modified(self):
        self.assertFalse(self.rep["modifies_shipped_code"])

    def test_full_sample_constants_are_the_recorded_ones(self):
        self.assertEqual(self.rep["full_sample_combo"], [0.0, 0.82, 1.0, 0.2])


class TestRecordedBoundaryProbe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = _load("classic_negative_v2_boundary_probe.json")

    def test_toe_lift_boundary_is_a_true_optimum(self):
        self.assertFalse(self.rep["boundary_binds"]["toe_lift"])
        sweep = self.rep["toe_lift_sweep"]
        # 하한 밖으로 갈수록 단조 악화
        ordered = [sweep[k] for k in sorted(sweep, key=float)]
        self.assertEqual(ordered, sorted(ordered, reverse=True))

    def test_white_point_escape_is_negligible(self):
        self.assertTrue(self.rep["boundary_binds"]["white_point"])
        sweep = self.rep["white_point_sweep"]
        gain = self.rep["baseline_de00"] - min(sweep.values())
        # 현행 계열에서 같은 탈출구가 6.5 ΔE00을 가져갔던 것과 대비된다
        self.assertLess(gain, 0.15)
        self.assertAlmostEqual(gain, 0.0525, places=3)

    def test_shoulders_and_saturation_edges_are_recorded(self):
        self.assertTrue(self.rep["boundary_binds"]["shoulder_start"])
        self.assertTrue(self.rep["boundary_binds"]["sat_mult"])
        self.assertIn("0.999", self.rep["shoulder_start_sweep"])
        self.assertIn("0.15", self.rep["sat_mult_sweep"])


class TestRecordedOffsetDiagnostics(unittest.TestCase):
    def test_neutral_render_offset_is_systematic(self):
        rep = _load("neutral_render_offset_classic_negative.json")
        self.assertEqual(rep["n_pairs"], 47)
        # 다섯 지표 전부 CI가 0을 배제했다는 게 이 진단의 결론이다
        self.assertEqual(len(rep["systematic_offsets"]), 5)
        for k, s in rep["stats"].items():
            self.assertFalse(s["inconclusive"], msg=k)
        self.assertAlmostEqual(rep["stats"]["lab_L_median"]["mean_diff"],
                               74.851, places=2)
        self.assertAlmostEqual(rep["stats"]["hsv_S_mean"]["mean_diff"],
                               -19.490, places=2)

    def test_autobright_only_partially_closes_the_gap(self):
        rep = _load("autobright_vs_look_classic_negative.json")
        s = ab.summarize(rep["delta_e_neutral"], rep["delta_e_autobright"],
                         "neutral", "auto-bright")
        for k in ("mean_a", "mean_b", "ci_lo", "ci_hi"):
            self.assertAlmostEqual(s[k], rep["stats"][k], places=9, msg=k)
        # linear-RGB 도메인에서 auto-bright가 격차의 약 1/4을 닫는다.
        improvement = 100.0 * (s["mean_a"] - s["mean_b"]) / s["mean_a"]
        self.assertAlmostEqual(improvement, 25.02899516425401, places=9)


class TestRecordedCrossBrandOffset(unittest.TestCase):
    def test_brightness_bias_is_universal_saturation_is_not(self):
        p = os.path.join(BASE, "datasets", "neutral_render_offset_by_brand.json")
        if not os.path.exists(p):
            self.skipTest("리포트 없음")
        with open(p, encoding="utf-8") as f:
            rep = json.load(f)
        self.assertEqual(sorted(rep["universal_biased_metrics"]),
                         ["lab_L_mean", "lab_L_median", "white_p995"])
        self.assertNotIn("hsv_S_mean", rep["universal_biased_metrics"])
        # 밝기는 모든 세트에서 양수 + CI가 0 배제
        for s in rep["sets"]:
            st = s["stats"]["lab_L_median"]
            self.assertGreater(st["mean_diff"], 0.0, msg=s["label"])
            self.assertFalse(st["inconclusive"], msg=s["label"])


if __name__ == "__main__":
    unittest.main()
