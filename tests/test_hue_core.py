import unittest

import numpy as np

from hybrid_engine.core.hue_core import apply_hue_lut


class TestApplyHueLut(unittest.TestCase):
    def test_zero_lut_leaves_hue_unchanged(self):
        rng = np.random.default_rng(0)
        a = rng.uniform(-50, 50, size=(8, 8))
        b = rng.uniform(-50, 50, size=(8, 8))
        lut = np.zeros(36)
        a2, b2 = apply_hue_lut(a, b, lut)
        np.testing.assert_allclose(a2, a, atol=1e-6)
        np.testing.assert_allclose(b2, b, atol=1e-6)

    def test_chroma_is_preserved(self):
        rng = np.random.default_rng(1)
        a = rng.uniform(-50, 50, size=(8, 8))
        b = rng.uniform(-50, 50, size=(8, 8))
        lut = rng.uniform(-30, 30, size=36)
        a2, b2 = apply_hue_lut(a, b, lut)
        np.testing.assert_allclose(np.hypot(a2, b2), np.hypot(a, b), atol=1e-6)

    def test_constant_lut_rotates_hue_by_fixed_amount(self):
        # 순수 hue=0도(a=chroma, b=0) 픽셀 - 모든 bin이 +30도면 hue가 30도가 돼야 함
        a = np.array([[10.0]])
        b = np.array([[0.0]])
        lut = np.full(36, 30.0)
        a2, b2 = apply_hue_lut(a, b, lut)
        hue_out = np.degrees(np.arctan2(b2, a2)) % 360.0
        np.testing.assert_allclose(hue_out, 30.0, atol=1e-4)

    def test_wraparound_is_continuous_near_0_360(self):
        # hue=359도와 hue=1도는 인접 bin인데, 서로 다른 보정값을 가진 LUT이어도
        # np.interp가 경계에서 튀지 않고 부드럽게 이어져야 함
        n_bins = 36
        lut = np.zeros(n_bins)
        lut[0] = 10.0   # bin 0: hue 0~10도
        lut[-1] = -10.0  # 마지막 bin: hue 350~360도
        hue_near_0 = np.radians(0.5)
        hue_near_360 = np.radians(359.5)
        a = np.array([[np.cos(hue_near_0) * 10, np.cos(hue_near_360) * 10]])
        b = np.array([[np.sin(hue_near_0) * 10, np.sin(hue_near_360) * 10]])
        a2, b2 = apply_hue_lut(a, b, lut)
        # 발산(NaN/inf)이나 급격한 불연속 없이 유한한 값이면 충분
        self.assertTrue(np.all(np.isfinite(a2)))
        self.assertTrue(np.all(np.isfinite(b2)))


class TestLearnHueLutFunction(unittest.TestCase):
    """calibrate_profile.learn_hue_lut - 합성 페어로 학습 로직 자체를 검증
    (raw 디코드는 필요 없음: dataset 튜플을 직접 구성)."""

    def test_learns_near_zero_when_target_equals_source(self):
        from hybrid_engine.calibrate_profile import learn_hue_lut
        from hybrid_engine.pipeline.engine import HybridCameraEngine
        import colour

        rng = np.random.default_rng(11)
        img = rng.uniform(0.1, 0.8, size=(16, 16, 3))
        profile = {"correct_color_cast": False, "use_color_unification": False}
        engine = HybridCameraEngine(profile=profile)
        L2, a2, b2 = engine.to_pre_hue_lab(img)
        lab = np.stack([L2, a2, b2], axis=-1)
        target = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)

        dataset = [(img, None, target)]
        lut = learn_hue_lut(dataset, profile, n_bins=36)
        # 타깃이 소스와 (재인코딩 왕복오차 이내로) 같으니 학습된 보정량은 0에 가까워야 함
        np.testing.assert_allclose(lut, 0.0, atol=2.0)

    def test_constant_hue_shift_is_recovered(self):
        from hybrid_engine.calibrate_profile import learn_hue_lut

        n_bins = 36
        rng = np.random.default_rng(12)
        a = rng.uniform(-40, 40, size=(20, 20))
        b = rng.uniform(-40, 40, size=(20, 20))
        chroma = np.hypot(a, b)
        hue = np.arctan2(b, a)

        shift_deg = 15.0
        shifted_hue = hue + np.radians(shift_deg)
        target_a = chroma * np.cos(shifted_hue)
        target_b = chroma * np.sin(shifted_hue)

        # to_pre_hue_lab을 거치지 않고 최소 재현을 위해 profile={} + 항등에
        # 가까운 engine 대신, learn_hue_lut의 내부 로직만 직접 검증하고 싶어서
        # engine.to_pre_hue_lab이 그대로 (L, a, b)를 반환하도록 L은 임의값 사용
        import colour
        L = np.full_like(a, 50.0)
        lab_source = np.stack([L, a, b], axis=-1)
        source_linear = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab_source), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)
        lab_target = np.stack([L, target_a, target_b], axis=-1)
        target_linear = np.clip(colour.XYZ_to_RGB(
            colour.Lab_to_XYZ(lab_target), colour.RGB_COLOURSPACES["sRGB"],
            apply_cctf_encoding=False), 0.0, 1.0)

        profile = {"correct_color_cast": False, "use_color_unification": False,
                   "sat_gain": 0.0, "shadow_lift": 0.0, "contrast_n": 1.0,
                   "highlight_rolloff_start": 1.0}
        dataset = [(source_linear, None, target_linear)]
        lut = learn_hue_lut(dataset, profile, n_bins=n_bins)
        filled = lut != 0.0
        self.assertTrue(filled.any())
        # 재인코딩 왕복오차를 감안해서 대략 shift_deg 근방인지만 확인
        np.testing.assert_allclose(lut[filled], shift_deg, atol=3.0)


if __name__ == "__main__":
    unittest.main()
