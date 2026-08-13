"""tools/evaluate_hybrid_switch.py의 _build_lut() 최소 표본 수 가드 테스트 -
tools/fit_final_lut.py와 동일한 가드/버그였던 부분(tools/CLAUDE.md 관례상
evaluate_*.py끼리 서로 import 안 하고 로직을 각자 복사 유지하므로 테스트도
따로 둔다). 실제 raw+jpeg 이미지 없이 순수 numpy 배열만으로 검증
가능(tests/CLAUDE.md "unit-test the pure parts")."""
import unittest

import numpy as np

from tools.evaluate_hybrid_switch import MIN_BIN_SAMPLES, N_BINS, _build_lut


class TestBuildLut(unittest.TestCase):
    def test_well_filled_bins_use_direct_average(self):
        sum_target = np.full(N_BINS, 100.0 * 50)
        sum_weight = np.full(N_BINS, 50.0)
        lut = _build_lut(sum_target, sum_weight)
        self.assertTrue(np.all(lut == 100))

    def test_sparse_bin_below_threshold_is_interpolated_not_averaged(self):
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        sum_target[99] = 100.0 * 50
        sum_weight[99] = 50
        sum_target[100] = 250.0 * 1  # 표본 1개, MIN_BIN_SAMPLES(30) 미달
        sum_weight[100] = 1
        sum_target[101] = 100.0 * 50
        sum_weight[101] = 50
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut[99], 100)
        self.assertEqual(lut[101], 100)
        self.assertEqual(lut[100], 100)  # 250이 아니라 보간된 100이어야 함

    def test_bin_exactly_at_threshold_uses_direct_average(self):
        # 임계값 경계 확인은 단조 계단 형태로 구성한다(낮은 값 -> 높은
        # 값으로 한 번만 증가) - 그래야 PAVA(단조성 보정)가 이 값을
        # 다시 깎아내리지 않고, 순수하게 "임계값 bin이 직접평균을
        # 쓰는지"만 볼 수 있다.
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        sum_target[:100] = 100.0 * 50
        sum_weight[:100] = 50
        sum_target[100:] = 200.0 * MIN_BIN_SAMPLES
        sum_weight[100:] = MIN_BIN_SAMPLES
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut[99], 100)
        self.assertEqual(lut[100], 200)

    def test_non_monotonic_dip_gets_smoothed_by_isotonic_regression(self):
        # 실제 발견된 버그 패턴 재현: 표본은 충분(가드를 통과)하지만
        # 인접 bin과 비교해 비단조적으로 급락하는 구간 - PAVA가 최종
        # 출력을 non-decreasing으로 강제하는지 확인한다.
        sum_target = np.full(N_BINS, 100.0 * 50)
        sum_weight = np.full(N_BINS, 50.0)
        sum_target[0] = 150.0 * 50
        sum_target[1] = 150.0 * 50
        sum_target[2] = 150.0 * 50
        sum_target[3] = 10.0 * 50  # 급락 - 표본은 충분하니 가드로는 안 걸러짐
        lut = _build_lut(sum_target, sum_weight)
        self.assertTrue(np.all(np.diff(lut.astype(int)) >= 0),
                         f"단조 non-decreasing이어야 하는데 아님: {lut[:6]}")

    def test_zero_weight_bin_is_still_interpolated(self):
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        sum_target[99] = 100.0 * 50
        sum_weight[99] = 50
        sum_target[101] = 200.0 * 50
        sum_weight[101] = 50
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut[100], 150)

    def test_output_shape_and_dtype(self):
        sum_target = np.full(N_BINS, 100.0 * 50)
        sum_weight = np.full(N_BINS, 50.0)
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut.shape, (N_BINS,))
        self.assertEqual(lut.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
