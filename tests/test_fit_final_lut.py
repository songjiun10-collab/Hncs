"""tools/fit_final_lut.py의 _build_lut() 최소 표본 수 가드 테스트 -
표본이 적은 bin(노이즈 지배)이 그대로 튀어나오지 않고 표본 0개인 bin과
동일하게 보간 대체되는지 확인한다. 실제 raw+jpeg 이미지 없이도 순수
numpy 배열만으로 검증 가능(tests/CLAUDE.md "unit-test the pure parts")."""
import unittest

import numpy as np

from tools.fit_final_lut import MIN_BIN_SAMPLES, N_BINS, _build_lut


class TestBuildLut(unittest.TestCase):
    def test_well_filled_bins_use_direct_average(self):
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        sum_target[:] = 100.0 * 50  # 각 bin 평균 100
        sum_weight[:] = 50  # 임계값(30) 이상
        lut = _build_lut(sum_target, sum_weight)
        self.assertTrue(np.all(lut == 100))

    def test_sparse_bin_below_threshold_is_interpolated_not_averaged(self):
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        # bin 99/101은 표본 충분(값 100), bin 100은 표본 딱 1개인데
        # 노이즈로 값이 완전히 다름(250) - 가드가 없으면 100번 bin이
        # 100 -> 250 -> 100 으로 튀어야 하지만, 가드가 있으면 99/101 사이
        # 보간값(100)에 가까워야 한다.
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
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        sum_target[:] = 100.0 * 50
        sum_weight[:] = 50
        sum_target[100] = 200.0 * MIN_BIN_SAMPLES
        sum_weight[100] = MIN_BIN_SAMPLES
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut[100], 200)  # 임계값 자체는 직접평균 허용(>=)

    def test_zero_weight_bin_is_still_interpolated(self):
        sum_target = np.zeros(N_BINS)
        sum_weight = np.zeros(N_BINS)
        sum_target[99] = 100.0 * 50
        sum_weight[99] = 50
        sum_target[101] = 200.0 * 50
        sum_weight[101] = 50
        # bin 100은 표본 0개 - 기존 로직(가드 이전)도 이미 처리하던 경우
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut[100], 150)  # 99와 101 사이 선형보간

    def test_output_shape_and_dtype(self):
        sum_target = np.full(N_BINS, 100.0 * 50)
        sum_weight = np.full(N_BINS, 50.0)
        lut = _build_lut(sum_target, sum_weight)
        self.assertEqual(lut.shape, (N_BINS,))
        self.assertEqual(lut.dtype, np.uint8)


if __name__ == "__main__":
    unittest.main()
