import unittest

import numpy as np

from hybrid_engine.core.lab2d_core import apply_lab2d_lut


def _identity_table(grid_size, domain):
    lo, hi = domain
    coords = np.stack(np.meshgrid(
        np.linspace(lo[0], hi[0], grid_size),
        np.linspace(lo[1], hi[1], grid_size),
        indexing="ij"), axis=-1)
    return coords


class TestApplyLab2dLut(unittest.TestCase):
    def test_identity_table_leaves_ab_unchanged(self):
        domain = np.array([[-50.0, -50.0], [50.0, 50.0]])
        table = _identity_table(5, domain)
        a = np.array([[10.0, -30.0]])
        b = np.array([[0.0, 20.0]])
        a2, b2 = apply_lab2d_lut(a, b, table, domain)
        np.testing.assert_allclose(a2, a, atol=1e-6)
        np.testing.assert_allclose(b2, b, atol=1e-6)

    def test_shape_preserved(self):
        domain = np.array([[-50.0, -50.0], [50.0, 50.0]])
        table = _identity_table(4, domain)
        rng = np.random.default_rng(0)
        a = rng.uniform(-50, 50, size=(6, 7))
        b = rng.uniform(-50, 50, size=(6, 7))
        a2, b2 = apply_lab2d_lut(a, b, table, domain)
        self.assertEqual(a2.shape, (6, 7))
        self.assertEqual(b2.shape, (6, 7))

    def test_out_of_domain_input_is_clipped_not_extrapolated(self):
        domain = np.array([[-50.0, -50.0], [50.0, 50.0]])
        table = _identity_table(5, domain)
        a = np.array([[200.0]])
        b = np.array([[0.0]])
        a2, b2 = apply_lab2d_lut(a, b, table, domain)
        np.testing.assert_allclose(a2, [[50.0]], atol=1e-6)

    def test_constant_offset_table_shifts_output(self):
        domain = np.array([[-50.0, -50.0], [50.0, 50.0]])
        table = _identity_table(5, domain) + np.array([3.0, -4.0])
        a = np.array([[0.0]])
        b = np.array([[0.0]])
        a2, b2 = apply_lab2d_lut(a, b, table, domain)
        np.testing.assert_allclose(a2, [[3.0]], atol=1e-6)
        np.testing.assert_allclose(b2, [[-4.0]], atol=1e-6)

    def test_bilinear_interpolation_between_grid_points(self):
        # 2점(0,0)->(a=0), (1,0)->(a=10)인 2x1 격자 도메인에서 중간점은
        # 선형보간으로 5 근방이어야 함
        domain = np.array([[0.0, 0.0], [1.0, 0.0]])
        table = np.array([[[0.0, 0.0]], [[10.0, 0.0]]])  # shape (2,1,2)
        a = np.array([[0.5]])
        b = np.array([[0.0]])
        a2, b2 = apply_lab2d_lut(a, b, table, domain)
        np.testing.assert_allclose(a2, [[5.0]], atol=1e-6)


class TestLearnLab2dLutFunction(unittest.TestCase):
    """calibrate_profile.learn_lab2d_lut - 합성 페어로 학습 로직 자체를
    검증(raw 디코드는 필요 없음: dataset 튜플을 직접 구성)."""

    def test_learns_near_identity_when_target_equals_source(self):
        from hybrid_engine.calibrate_profile import learn_lab2d_lut
        from hybrid_engine.pipeline.engine import HybridCameraEngine
        import colour

        rng = np.random.default_rng(30)
        img = rng.uniform(0.1, 0.8, size=(16, 16, 3))
        profile = {"correct_color_cast": False, "use_color_unification": False}
        engine = HybridCameraEngine(profile=profile)
        L2, a2, b2 = engine.to_pre_hue_lab(img)
        lab = np.stack([L2, a2, b2], axis=-1)
        target = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)

        dataset = [(img, None, target)]
        table, domain = learn_lab2d_lut(dataset, profile, grid_size=5)
        identity = _identity_table(5, domain)
        self.assertTrue(np.all(np.isfinite(table)))
        self.assertLess(float(np.mean(np.abs(table - identity))), 5.0)

    def test_constant_offset_is_recovered(self):
        from hybrid_engine.calibrate_profile import learn_lab2d_lut
        from hybrid_engine.pipeline.engine import HybridCameraEngine
        import colour

        rng = np.random.default_rng(31)
        img = rng.uniform(0.1, 0.8, size=(16, 16, 3))
        profile = {"correct_color_cast": False, "use_color_unification": False}
        engine = HybridCameraEngine(profile=profile)
        L2, a2, b2 = engine.to_pre_hue_lab(img)

        offset_a = 4.0
        lab_target = np.stack([L2, a2 + offset_a, b2], axis=-1)
        target = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab_target), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)

        dataset = [(img, None, target)]
        table, domain = learn_lab2d_lut(dataset, profile, grid_size=5)
        identity = _identity_table(5, domain)
        filled = np.abs(table - identity)[..., 0] > 1e-9
        self.assertTrue(filled.any())
        learned_a_shift = (table[..., 0] - identity[..., 0])[filled]
        self.assertAlmostEqual(float(np.median(learned_a_shift)), offset_a, delta=2.0)


if __name__ == "__main__":
    unittest.main()
