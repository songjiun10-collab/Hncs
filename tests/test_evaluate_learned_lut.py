"""tools/evaluate_learned_lut.py의 _build_lut() 최소 표본 수 가드 테스트 -
tools/fit_final_lut.py와 동일한 가드/버그였던 부분(tools/CLAUDE.md 관례상
evaluate_*.py끼리 서로 import 안 하고 로직을 각자 복사 유지하므로 테스트도
따로 둔다). 실제 raw+jpeg 이미지 없이 순수 numpy 배열만으로 검증
가능(tests/CLAUDE.md "unit-test the pure parts")."""
import unittest

import numpy as np

from tools.evaluate_learned_lut import MIN_BIN_SAMPLES, N_BINS, _build_lut


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
        sum_target = np.full(N_BINS, 100.0 * 50)
        sum_weight = np.full(N_BINS, 50.0)
        sum_target[100] = 200.0 * MIN_BIN_SAMPLES
        sum_weight[100] = MIN_BIN_SAMPLES
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut[100], 200)

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
