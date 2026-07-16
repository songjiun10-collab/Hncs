import unittest

import numpy as np

from hybrid_engine.core.normalizer import (
    gray_world_normalize, normalize_exposure, normalize,
)
from hybrid_engine.core.tone_core import apply_tone
from hybrid_engine.core.color_core import (
    luma_saturation_boost, gamut_clamp, apply_color,
)
from hybrid_engine.core.color_matrix import estimate_source_white_xy, unify_to_d65
from hybrid_engine.pipeline.engine import HybridCameraEngine
from hybrid_engine.utils.evaluate import mean_delta_e


class TestNormalizer(unittest.TestCase):
    def test_gray_world_removes_channel_bias(self):
        img = np.zeros((8, 8, 3))
        img[..., 0] = 0.5   # R skewed high
        img[..., 1] = 0.2
        img[..., 2] = 0.2
        out = gray_world_normalize(img)
        means = out.reshape(-1, 3).mean(axis=0)
        self.assertAlmostEqual(means[0], means[1], places=6)
        self.assertAlmostEqual(means[1], means[2], places=6)

    def test_normalize_exposure_hits_target_gray(self):
        img = np.full((4, 4, 3), 0.05)
        out = normalize_exposure(img, target_gray=0.18)
        self.assertAlmostEqual(float(np.mean(out)), 0.18, places=6)

    def test_normalize_exposure_zero_mean_is_noop(self):
        img = np.zeros((4, 4, 3))
        out = normalize_exposure(img)
        np.testing.assert_array_equal(out, img)

    def test_normalize_pipeline_runs(self):
        img = np.random.default_rng(0).uniform(0, 0.5, size=(6, 6, 3))
        out = normalize(img)
        self.assertEqual(out.shape, img.shape)


class TestToneCore(unittest.TestCase):
    def test_preserves_shape_and_range(self):
        L = np.random.default_rng(1).uniform(0, 100, size=(5, 5))
        out = apply_tone(L)
        self.assertEqual(out.shape, L.shape)
        self.assertTrue(np.all(out >= 0.0))
        self.assertTrue(np.all(out <= 100.0))

    def test_black_and_white_endpoints_preserved(self):
        L = np.array([[0.0, 100.0]])
        out = apply_tone(L, shadow_lift_amt=0.0)
        self.assertAlmostEqual(out[0, 0], 0.0, places=3)
        self.assertAlmostEqual(out[0, 1], 100.0, places=3)

    def test_shadow_lift_raises_near_black(self):
        L = np.array([[0.0]])
        lifted = apply_tone(L, shadow_lift_amt=0.05)
        unlifted = apply_tone(L, shadow_lift_amt=0.0)
        self.assertGreater(lifted[0, 0], unlifted[0, 0])


class TestColorCore(unittest.TestCase):
    def test_midtone_gets_more_boost_than_shadow(self):
        L_mid = np.array([50.0])
        L_shadow = np.array([5.0])
        a = np.array([10.0])
        b = np.array([10.0])
        a_mid, _ = luma_saturation_boost(L_mid, a, b, gain=0.5, center=50, width=20)
        a_shadow, _ = luma_saturation_boost(L_shadow, a, b, gain=0.5, center=50, width=20)
        self.assertGreater(a_mid[0], a_shadow[0])

    def test_gamut_clamp_limits_chroma(self):
        a = np.array([200.0])
        b = np.array([200.0])
        a2, b2 = gamut_clamp(a, b, max_chroma=110.0)
        chroma = np.sqrt(a2 ** 2 + b2 ** 2)
        self.assertAlmostEqual(float(chroma[0]), 110.0, places=3)

    def test_gamut_clamp_leaves_small_chroma_untouched(self):
        a = np.array([5.0])
        b = np.array([5.0])
        a2, b2 = gamut_clamp(a, b, max_chroma=110.0)
        np.testing.assert_allclose(a2, a)
        np.testing.assert_allclose(b2, b)

    def test_apply_color_shape_preserved(self):
        L = np.full((4, 4), 50.0)
        a = np.full((4, 4), 20.0)
        b = np.full((4, 4), 20.0)
        a2, b2 = apply_color(L, a, b)
        self.assertEqual(a2.shape, a.shape)
        self.assertEqual(b2.shape, b.shape)


class TestColorMatrix(unittest.TestCase):
    def test_neutral_whitebalance_gives_near_d65_white_point(self):
        # R=G=B 배수(중립 WB)면 sRGB 백색점(D65 근방)으로 추정돼야 함
        xy = estimate_source_white_xy([1.0, 1.0, 1.0, 0.0])
        np.testing.assert_allclose(xy, [0.3127, 0.3290], atol=0.01)

    def test_unify_to_d65_is_near_identity_when_already_d65(self):
        xyz = np.random.default_rng(2).uniform(0.1, 0.9, size=(3, 3, 3))
        out = unify_to_d65(xyz, source_white_xy=np.array([0.3127, 0.3290]))
        np.testing.assert_allclose(out, xyz, atol=1e-3)

    def test_unify_to_d65_preserves_shape(self):
        xyz = np.random.default_rng(3).uniform(0.1, 0.9, size=(4, 5, 3))
        out = unify_to_d65(xyz, source_white_xy=np.array([0.35, 0.36]))
        self.assertEqual(out.shape, xyz.shape)


class TestHybridCameraEngine(unittest.TestCase):
    def test_process_preserves_shape(self):
        rng = np.random.default_rng(4)
        img = rng.uniform(0, 1, size=(10, 10, 3))
        engine = HybridCameraEngine()
        out = engine.process(img)
        self.assertEqual(out.shape, img.shape)

    def test_process_output_is_finite_and_nonnegative(self):
        rng = np.random.default_rng(5)
        img = rng.uniform(0, 1, size=(10, 10, 3))
        engine = HybridCameraEngine()
        out = engine.process(img)
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertTrue(np.all(out >= 0.0))

    def test_profile_overrides_defaults(self):
        engine = HybridCameraEngine(profile={"sat_gain": 0.0})
        self.assertEqual(engine.params["sat_gain"], 0.0)
        self.assertEqual(engine.params["target_gray"], 0.18)  # 기본값 유지

    def test_process_with_camera_whitebalance_runs_phase0(self):
        rng = np.random.default_rng(6)
        img = rng.uniform(0.05, 0.9, size=(8, 8, 3))
        engine = HybridCameraEngine()
        out = engine.process(img, camera_whitebalance=[2.0, 1.0, 1.5, 0.0])
        self.assertEqual(out.shape, img.shape)
        self.assertTrue(np.all(np.isfinite(out)))

    def test_use_color_unification_false_skips_phase0_without_error(self):
        rng = np.random.default_rng(7)
        img = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        engine = HybridCameraEngine(profile={"use_color_unification": False})
        out = engine.process(img, camera_whitebalance=[2.0, 1.0, 1.5, 0.0])
        self.assertEqual(out.shape, img.shape)


class TestEvaluate(unittest.TestCase):
    def test_self_comparison_is_zero(self):
        rng = np.random.default_rng(8)
        img = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        self.assertAlmostEqual(mean_delta_e(img, img), 0.0, places=6)

    def test_shape_mismatch_raises(self):
        a = np.zeros((4, 4, 3))
        b = np.zeros((5, 5, 3))
        with self.assertRaises(ValueError):
            mean_delta_e(a, b)

    def test_different_colors_give_positive_delta_e(self):
        a = np.full((3, 3, 3), 0.5)
        b = a.copy()
        b[..., 0] = 0.1  # 붉은기 뺌
        self.assertGreater(mean_delta_e(a, b), 0.0)


if __name__ == "__main__":
    unittest.main()
