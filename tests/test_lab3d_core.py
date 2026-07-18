import unittest

import numpy as np

from hybrid_engine.core.lab3d_core import apply_lab3d_lut


def _identity_table(grid_size, domain):
    lo, hi = domain
    coords = np.stack(np.meshgrid(
        np.linspace(lo[0], hi[0], grid_size),
        np.linspace(lo[1], hi[1], grid_size),
        np.linspace(lo[2], hi[2], grid_size),
        indexing="ij"), axis=-1)
    return coords


class TestApplyLab3dLut(unittest.TestCase):
    def test_identity_table_leaves_lab_unchanged(self):
        domain = np.array([[0.0, -50.0, -50.0], [100.0, 50.0, 50.0]])
        table = _identity_table(5, domain)
        L = np.array([[50.0, 10.0]])
        a = np.array([[0.0, -30.0]])
        b = np.array([[0.0, 20.0]])
        L2, a2, b2 = apply_lab3d_lut(L, a, b, table, domain)
        np.testing.assert_allclose(L2, L, atol=1e-6)
        np.testing.assert_allclose(a2, a, atol=1e-6)
        np.testing.assert_allclose(b2, b, atol=1e-6)

    def test_shape_preserved(self):
        domain = np.array([[0.0, -50.0, -50.0], [100.0, 50.0, 50.0]])
        table = _identity_table(4, domain)
        rng = np.random.default_rng(0)
        L = rng.uniform(0, 100, size=(6, 7))
        a = rng.uniform(-50, 50, size=(6, 7))
        b = rng.uniform(-50, 50, size=(6, 7))
        L2, a2, b2 = apply_lab3d_lut(L, a, b, table, domain)
        self.assertEqual(L2.shape, (6, 7))
        self.assertEqual(a2.shape, (6, 7))
        self.assertEqual(b2.shape, (6, 7))

    def test_out_of_domain_input_is_clipped_not_extrapolated(self):
        domain = np.array([[0.0, -50.0, -50.0], [100.0, 50.0, 50.0]])
        table = _identity_table(5, domain)
        # 도메인 밖(L=200) 입력 - clip 후 적용되니 L=100(도메인 상한)과 같아야 함
        L = np.array([[200.0]])
        a = np.array([[0.0]])
        b = np.array([[0.0]])
        L2, a2, b2 = apply_lab3d_lut(L, a, b, table, domain)
        np.testing.assert_allclose(L2, [[100.0]], atol=1e-6)

    def test_constant_offset_table_shifts_output(self):
        domain = np.array([[0.0, -50.0, -50.0], [100.0, 50.0, 50.0]])
        table = _identity_table(5, domain) + np.array([5.0, -2.0, 1.0])
        L = np.array([[50.0]])
        a = np.array([[0.0]])
        b = np.array([[0.0]])
        L2, a2, b2 = apply_lab3d_lut(L, a, b, table, domain)
        np.testing.assert_allclose(L2, [[55.0]], atol=1e-6)
        np.testing.assert_allclose(a2, [[-2.0]], atol=1e-6)
        np.testing.assert_allclose(b2, [[1.0]], atol=1e-6)


class TestLearnLab3dLutFunction(unittest.TestCase):
    """calibrate_profile.learn_lab3d_lut - 합성 페어로 학습 로직 자체를
    검증(raw 디코드는 필요 없음: dataset 튜플을 직접 구성)."""

    def test_learns_near_identity_when_target_equals_source(self):
        from hybrid_engine.calibrate_profile import learn_lab3d_lut
        from hybrid_engine.pipeline.engine import HybridCameraEngine
        import colour

        rng = np.random.default_rng(20)
        img = rng.uniform(0.1, 0.8, size=(16, 16, 3))
        profile = {"correct_color_cast": False, "use_color_unification": False}
        engine = HybridCameraEngine(profile=profile)
        L2, a2, b2 = engine.to_pre_hue_lab(img)
        lab = np.stack([L2, a2, b2], axis=-1)
        target = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)

        dataset = [(img, None, target)]
        table, domain = learn_lab3d_lut(dataset, profile, grid_size=5)
        identity = _identity_table(5, domain)
        # 표본이 있는(채워진) 격자점만 항등에 가까워야 함 - 빈 격자점은
        # 애초에 identity로 초기화돼서 항상 통과하므로 별 의미 없는 비교지만
        # 최소한 발산은 없어야 함
        self.assertTrue(np.all(np.isfinite(table)))
        self.assertLess(float(np.mean(np.abs(table - identity))), 5.0)

    def test_constant_offset_is_recovered(self):
        from hybrid_engine.calibrate_profile import learn_lab3d_lut
        from hybrid_engine.pipeline.engine import HybridCameraEngine
        import colour

        rng = np.random.default_rng(21)
        img = rng.uniform(0.1, 0.8, size=(16, 16, 3))
        profile = {"correct_color_cast": False, "use_color_unification": False}
        engine = HybridCameraEngine(profile=profile)
        L2, a2, b2 = engine.to_pre_hue_lab(img)

        offset_L = 8.0
        lab_target = np.stack([np.clip(L2 + offset_L, 0.0, 100.0), a2, b2], axis=-1)
        target = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab_target), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)

        dataset = [(img, None, target)]
        table, domain = learn_lab3d_lut(dataset, profile, grid_size=5)
        identity = _identity_table(5, domain)
        counts_proxy = np.abs(table - identity)[..., 0]
        filled = counts_proxy > 1e-9
        self.assertTrue(filled.any())
        # 채워진 격자점의 L 보정량 median이 대략 offset_L 근방이어야 함 -
        # L을 올리면 원래 a/b와의 조합이 sRGB 색역 밖으로 나가는 셀이
        # 일부 생겨서(RGB round-trip 시 clip) 개별 셀 단위로는 노이즈가
        # 있을 수 있어 median으로 확인(개별 atol 비교보다 이상치에 강함)
        learned_L_shift = (table[..., 0] - identity[..., 0])[filled]
        self.assertAlmostEqual(float(np.median(learned_L_shift)), offset_L, delta=2.0)


if __name__ == "__main__":
    unittest.main()
