import unittest

import numpy as np

from core.dcp_interpolate import (
    STANDARD_ILLUMINANT_CCT_K, _cct_from_xy, _xyz_to_xy, interpolate_dng_matrix,
)

# 임의지만 물리적으로 그럴듯한(양의 대각 우세) invertible 3x3 두 개.
# 실제 X2D II 데이터가 아니라 알고리즘 자체를 검증하는 합성 매트릭스.
_CM1 = np.array([
    [0.90, -0.20, -0.05],
    [-0.15, 1.10, 0.05],
    [0.00, -0.10, 0.85],
])
_CM2 = np.array([
    [0.70, -0.10, -0.02],
    [-0.10, 0.95, 0.10],
    [0.02, -0.15, 0.70],
])

_D65_XY = (0.3127, 0.3290)
_STD_A_XY = (0.4476, 0.4074)


def _xy_to_xyz_unit_y(xy):
    x, y = xy
    return np.array([x / y, 1.0, (1.0 - x - y) / y])


class TestCctFromXy(unittest.TestCase):
    def test_d65_chromaticity_gives_roughly_6500k(self):
        cct = _cct_from_xy(*_D65_XY)
        self.assertAlmostEqual(cct, 6504.0, delta=100.0)

    def test_standard_a_chromaticity_gives_roughly_2856k(self):
        cct = _cct_from_xy(*_STD_A_XY)
        self.assertAlmostEqual(cct, 2856.0, delta=150.0)


class TestXyzToXy(unittest.TestCase):
    def test_zero_xyz_falls_back_instead_of_dividing_by_zero(self):
        x, y = _xyz_to_xy([0.0, 0.0, 0.0])
        self.assertFalse(np.isnan(x) or np.isnan(y))

    def test_normalizes_by_sum(self):
        x, y = _xyz_to_xy([1.0, 1.0, 1.0])
        self.assertAlmostEqual(x, 1.0 / 3.0, places=9)
        self.assertAlmostEqual(y, 1.0 / 3.0, places=9)


class TestInterpolateDngMatrix(unittest.TestCase):
    def test_identical_matrices_short_circuit_without_iterating(self):
        native_to_xyz, g = interpolate_dng_matrix(
            [1.0, 1.0, 1.0], _CM1, 21, _CM1, 17)
        self.assertEqual(g, 0.5)
        np.testing.assert_allclose(native_to_xyz, np.linalg.inv(_CM1).T, atol=1e-9)

    def test_neutral_matching_illuminant_1_white_converges_near_g_1(self):
        # illuminant1(D65)의 own 표준 백색점을 CM1로 native에 투영해서
        # 그걸 그대로 camera_neutral로 넣으면, 알고리즘이 "이 중립색은
        # illuminant1 쪽 조명이다"를 스스로 복원해야 한다(g -> 1).
        xyz_d65 = _xy_to_xyz_unit_y(_D65_XY)
        native = _CM1 @ xyz_d65
        _, g = interpolate_dng_matrix(native, _CM1, 21, _CM2, 17)
        self.assertGreater(g, 0.9)

    def test_neutral_matching_illuminant_2_white_converges_near_g_0(self):
        xyz_a = _xy_to_xyz_unit_y(_STD_A_XY)
        native = _CM2 @ xyz_a
        _, g = interpolate_dng_matrix(native, _CM1, 21, _CM2, 17)
        self.assertLess(g, 0.1)

    def test_g_is_a_genuine_fixed_point(self):
        # 반환된 g로 한 번 더 수동으로 반복해도 g가 거의 안 바뀌어야
        # 한다(수렴 판정 자체가 올바른지 확인 - 종료 조건만 통과하고
        # 실제로는 안 수렴한 경우를 잡는다).
        native = [0.55, 1.0, 0.60]
        _, g = interpolate_dng_matrix(native, _CM1, 21, _CM2, 17)

        cm = g * np.asarray(_CM1) + (1 - g) * np.asarray(_CM2)
        xyz = np.linalg.inv(cm) @ np.asarray(native, dtype=np.float64)
        x, y = _xyz_to_xy(xyz)
        cct = _cct_from_xy(x, y)
        mired = 1.0e6 / cct
        mired1 = 1.0e6 / STANDARD_ILLUMINANT_CCT_K[21]
        mired2 = 1.0e6 / STANDARD_ILLUMINANT_CCT_K[17]
        g_check = float(np.clip((mired - mired2) / (mired1 - mired2), 0.0, 1.0))
        self.assertAlmostEqual(g, g_check, delta=1e-4)

    def test_returned_matrix_round_trips_to_the_interpolated_cm(self):
        native = [0.55, 1.0, 0.60]
        native_to_xyz, g = interpolate_dng_matrix(native, _CM1, 21, _CM2, 17)
        expected_cm = g * _CM1 + (1 - g) * _CM2
        # native_to_xyz는 행벡터 규약(xyz_row = native_row @ M) - DCP
        # 저장 규약(XYZ->native, 열벡터)으로 되돌리려면 inv().T.
        recovered_cm = np.linalg.inv(native_to_xyz).T
        np.testing.assert_allclose(recovered_cm, expected_cm, atol=1e-6)

    def test_g_stays_within_unit_interval_for_an_out_of_range_neutral(self):
        # 두 기준 조명 밖의 극단적인 중립색을 넣어도 g가 [0,1] 클램프를
        # 벗어나면 안 된다.
        native_to_xyz, g = interpolate_dng_matrix(
            [0.05, 1.0, 3.0], _CM1, 21, _CM2, 17)
        self.assertGreaterEqual(g, 0.0)
        self.assertLessEqual(g, 1.0)
        self.assertTrue(np.all(np.isfinite(native_to_xyz)))


if __name__ == "__main__":
    unittest.main()
