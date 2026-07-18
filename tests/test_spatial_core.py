import unittest

import numpy as np

from hybrid_engine.core.spatial_core import apply_local_contrast


class TestApplyLocalContrast(unittest.TestCase):
    def test_zero_amount_is_identity(self):
        rng = np.random.default_rng(0)
        L = rng.uniform(10, 90, size=(32, 32))
        out = apply_local_contrast(L, radius=20.0, amount=0.0, threshold=0.0)
        np.testing.assert_allclose(out, L)

    def test_shape_preserved(self):
        rng = np.random.default_rng(1)
        L = rng.uniform(10, 90, size=(20, 24))
        out = apply_local_contrast(L, radius=15.0, amount=0.5, threshold=0.0)
        self.assertEqual(out.shape, L.shape)

    def test_output_clipped_to_valid_L_range(self):
        L = np.full((16, 16), 95.0)
        L[8, 8] = 5.0  # 강한 국소 대비 - 증폭하면 범위를 벗어날 수 있음
        out = apply_local_contrast(L, radius=3.0, amount=5.0, threshold=0.0)
        self.assertTrue(np.all(out >= 0.0))
        self.assertTrue(np.all(out <= 100.0))

    def test_positive_amount_increases_edge_contrast(self):
        # 왼쪽 절반은 어둡고 오른쪽 절반은 밝은 계단 에지 - 언샤프 마스크는
        # 에지 근처에서 대비를 과장(오버슈트)시켜야 함
        L = np.zeros((40, 40))
        L[:, :20] = 30.0
        L[:, 20:] = 70.0
        out = apply_local_contrast(L, radius=5.0, amount=1.0, threshold=0.0)
        # 에지 바로 왼쪽(어두운 쪽)은 원본보다 더 어두워지고,
        # 에지 바로 오른쪽(밝은 쪽)은 원본보다 더 밝아져야 함(오버슈트)
        self.assertLess(out[20, 19], L[20, 19])
        self.assertGreater(out[20, 20], L[20, 20])

    def test_threshold_suppresses_small_detail(self):
        rng = np.random.default_rng(2)
        L = 50.0 + rng.uniform(-0.3, 0.3, size=(30, 30))  # 아주 미세한 노이즈만 있는 평탄면
        out_no_threshold = apply_local_contrast(L, radius=5.0, amount=2.0, threshold=0.0)
        out_high_threshold = apply_local_contrast(L, radius=5.0, amount=2.0, threshold=5.0)
        # threshold가 디테일 크기보다 훨씬 크면 사실상 무보정에 가까워야 함
        np.testing.assert_allclose(out_high_threshold, L, atol=1e-9)
        # threshold=0이면 미세한 디테일도 증폭돼서 원본과 달라짐
        self.assertFalse(np.allclose(out_no_threshold, L))


if __name__ == "__main__":
    unittest.main()
