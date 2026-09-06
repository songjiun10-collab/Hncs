"""`hybrid_engine/EVALUATION.md`의 "룩 LUT 굽는 방식 - 실사진 조건부
평균은 현재 방식보다 나쁘다" 절에 실린 실제 실행 결과를 재현하는 회귀
테스트. 실험을 다시 안 돌려도(54개 룩 x 13장, 약 15분) 문서의 통계를
검증할 수 있다 - `tests/CLAUDE.md`의 `TestSummarizeRecordedRun` 패턴.

기록은 `tools/evaluate_lut_bake_conditional_mean.py` 실행 출력을 문서 표와
같은 4자리로 전사한 것이고, 단언은 그 표가 실제로 뒷받침하는 정밀도까지만
건다. 이 실험은 **가설이 기각된** 기록이다 - 조건부 평균이 현재 방식보다
나빴고, 부트스트랩 CI가 음의 방향에서 0을 제외한다.
"""
import unittest

from tools.evaluate_lut_bake_conditional_mean import summarize

# (룩, 현재 방식 ΔE00, 조건부 평균 ΔE00) - held-out 6장 평균, 2026-09-05 실행
_RECORDED_RUN = [
    ("canon.apply_canon_look", 5.0452, 5.6662),
    ("canon.apply_canon_raw_look", 6.7216, 7.0180),
    ("canon_r1_raw.apply_canon_r1_raw_look", 8.4457, 8.1387),
    ("canon_r6iii_raw.apply_canon_r6iii_raw_look", 6.9269, 7.3116),
    ("fuji.apply_astia", 0.7630, 1.6266),
    ("fuji.apply_classic_chrome", 5.0341, 5.6335),
    ("fuji.apply_classic_chrome_v2", 5.1400, 5.7095),
    ("fuji.apply_classic_negative", 0.7077, 1.3535),
    ("fuji.apply_eterna_bleach_bypass", 0.5642, 0.8707),
    ("fuji.apply_eterna_cinema", 0.6270, 1.1299),
    ("fuji.apply_nostalgic_neg", 2.0283, 3.4691),
    ("fuji.apply_nostalgic_neg_v2", 5.0446, 5.6511),
    ("fuji.apply_nostalgic_neg_v3", 5.1400, 5.7095),
    ("fuji.apply_pro_neg_hi", 3.3125, 4.9354),
    ("fuji.apply_pro_neg_std", 0.8313, 1.6624),
    ("fuji.apply_provia", 9.0204, 9.7674),
    ("fuji.apply_reala_ace", 0.2401, 1.6476),
    ("fuji_provia_learned.apply_provia_learned", 4.8207, 4.9169),
    ("fuji_provia_matrix.apply_fuji_provia_matrix_look", 8.4475, 8.8358),
    ("hasselblad.apply_hncs", 5.6847, 5.9146),
    ("hasselblad.apply_hncs_video_frame", 0.7447, 1.7574),
    ("hasselblad_day.apply_hasselblad_day", 4.1920, 4.8849),
    ("hasselblad_learned.apply_hncs_learned", 5.3625, 5.2481),
    ("hasselblad_night.apply_hasselblad_night", 1.7525, 2.4502),
    ("hasselblad_x1d.apply_hncs_x1d", 5.0622, 5.3454),
    ("hasselblad_x1d50c.apply_hncs_x1d50c", 5.3139, 5.4604),
    ("hasselblad_x1dii50c.apply_hncs_x1dii50c", 5.3122, 5.4607),
    ("hasselblad_x2dii.apply_hncs_x2dii", 5.1387, 5.4831),
    ("leica.apply_leica_look", 5.0335, 5.6530),
    ("leica_raw.apply_leica_raw_look", 5.1400, 5.7095),
    ("leica_raw_learned.apply_leica_raw_learned", 5.0154, 5.2368),
    ("leica_raw_matrix.apply_leica_raw_matrix_look", 5.6308, 5.5858),
    ("nikon.apply_nikon_look", 5.0428, 5.6608),
    ("olympus.apply_olympus_look", 5.0312, 5.6540),
    ("panasonic.apply_panasonic_look", 5.0104, 5.6382),
    ("pentax.apply_pentax_look", 5.0498, 5.6582),
    ("phaseone.apply_phaseone_look", 5.0207, 5.6430),
    ("ricoh_gr.apply_ricoh_gr_look", 5.0736, 5.6738),
    ("sigma.apply_sigma_look", 5.0309, 5.6502),
    ("sigma_bf.apply_sigma_bf_look", 8.9718, 9.7156),
    ("sigma_bf_learned.apply_sigma_bf_learned", 4.6309, 4.7816),
    ("sigma_fpl.apply_sigma_fpl_look", 5.1263, 5.7023),
    ("sigma_fpl_learned.apply_sigma_fpl_learned", 5.1754, 5.4533),
    ("sigma_raw.apply_sigma_raw_look", 9.0104, 9.7571),
    ("sigma_raw_matrix.apply_sigma_raw_matrix_look", 9.6544, 8.2830),
    ("sony.apply_sony_look", 5.0313, 5.6494),
    ("sony_a7rvi.apply_sony_a7rvi_look", 4.7952, 5.4849),
    ("sony_a7rvi_learned.apply_sony_a7rvi_learned", 3.6572, 3.8742),
    ("sony_a7rvi_learned.apply_sony_a7rvi_learned_v2", 3.3291, 3.5565),
    ("sony_a7v.apply_sony_a7v_look", 5.0985, 5.7002),
    ("sony_a7v_learned.apply_sony_a7v_learned", 4.1701, 4.4039),
    ("sony_a7v_learned.apply_sony_a7v_learned_v2", 4.0612, 4.3550),
    ("sony_raw.apply_sony_raw_look", 6.3323, 7.6546),
    ("sony_raw_matrix.apply_sony_raw_matrix_look", 8.4843, 6.3049),
]


class TestSummarizeRecordedRun(unittest.TestCase):
    def setUp(self):
        self.s = summarize(_RECORDED_RUN)

    def test_reproduces_documented_means(self):
        self.assertEqual(self.s["n"], 54)
        self.assertAlmostEqual(self.s["mean_a"], 4.8339, places=3)
        self.assertAlmostEqual(self.s["mean_b"], 5.2870, places=3)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["b_wins"], 5)
        self.assertEqual(self.s["a_wins"], 49)

    def test_reproduces_documented_improvement_and_sign_test(self):
        self.assertAlmostEqual(self.s["improvement_pct"], -9.373, places=2)
        self.assertAlmostEqual(self.s["sign_test_p"], 3.8913883e-10, places=15)

    def test_confidence_interval_excludes_zero_on_the_losing_side(self):
        lo, hi = self.s["ci_diff"]
        self.assertLess(hi, 0.0)
        self.assertAlmostEqual(lo, -0.595, places=2)
        self.assertAlmostEqual(hi, -0.290, places=2)
        self.assertFalse(self.s["inconclusive"])

    def test_verdict_is_that_the_current_method_wins(self):
        self.assertEqual(self.s["verdict"], "현재 방식이 더 낫다")

    def test_dropone_never_flips_the_direction(self):
        self.assertLess(self.s["dropone_pct_max"], 0.0)


if __name__ == "__main__":
    unittest.main()
