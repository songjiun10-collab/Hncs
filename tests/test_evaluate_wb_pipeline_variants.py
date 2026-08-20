"""hybrid_engine/EVALUATION.md의 "WB 이중처리 확정 실험" 절에 기록된
실제 raw_calib_cache 13쌍 A/B leave-one-out ΔE00 재실행 결과를 재현하는
회귀 테스트 - 매번 raw 디코드를 다시 안 해도 문서의 통계 수치를
검증할 수 있다(tools/CLAUDE.md의 TestSummarizeRecordedRun 관례)."""
import unittest

from tools.evaluate_wb_pipeline_variants import summarize

# python3 -m tools.evaluate_wb_pipeline_variants 실행 결과 그대로(2026-08,
# raw_calib_cache 공식 13쌍) - leave-one-out ΔE00, 페어 순서는
# _find_pairs()의 정렬 순서(파일명 알파벳순)와 동일.
_RECORDED_A = [
    3.8548738272950791, 10.211092115885416, 12.067427371205556,
    17.31115964141717, 7.0708273406280133, 9.5294065209034251,
    9.2006760304301469, 9.1858203286837181, 8.8656241510402456,
    8.7993293988607881, 12.762598366211089, 4.7968112320089977,
    4.2684157231021507,
]
_RECORDED_B = [
    4.1923161049115949, 11.645479771633328, 12.993939592383907,
    18.939626521187243, 7.4961660580470548, 10.326638827133783,
    10.942548567757411, 11.946171055110863, 8.742457144262076,
    10.87733210874949, 14.19877419101528, 5.2505956332430577,
    4.4537253198379014,
]


class TestSummarizeRecordedRun(unittest.TestCase):
    def setUp(self):
        self.s = summarize("A", _RECORDED_A, "B", _RECORDED_B)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_a"], 9.071, places=3)
        self.assertAlmostEqual(self.s["mean_b"], 10.154, places=3)

    def test_reproduces_documented_improvement_pct(self):
        self.assertAlmostEqual(self.s["improvement_pct"], -11.94, places=1)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["wins"], 1)
        self.assertEqual(self.s["losses"], 12)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["p_value"], 0.0034, places=4)

    def test_reproduces_documented_ci_excludes_zero(self):
        ci_lo, ci_hi = self.s["ci"]
        self.assertLess(ci_hi, 0.0)
        self.assertFalse(self.s["inconclusive"])


if __name__ == "__main__":
    unittest.main()
