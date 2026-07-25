import unittest

import colour
import numpy as np

from hybrid_engine.core.chart_baseline import (
    D50_XY, reference_patches_linear_srgb, reference_patches_xyz_d50,
    patch_delta_e_xyz_d50,
)


class TestReferencePatchesXyzD50(unittest.TestCase):
    def test_shape(self):
        ref = reference_patches_xyz_d50()
        self.assertEqual(ref.shape, (24, 3))

    def test_neutral_patches_cluster_at_d50_whitepoint(self):
        # PATCH_NAMES의 마지막 6개(인덱스 18~23)가 무채색 패치 - D50으로
        # 색순응했으면 이들의 xy 색도가 D50 백색점 근처로 모여야 한다.
        # 주의: 이 colour-science 버전의 데이터셋은 cc.illuminant 자체가
        # 이미 D50에 가까운 값이라, 이 테스트는 색순응이 "제대로 걸렸는지"를
        # 가르지 못한다(chromatic_adaptation() 호출을 통째로 지워도 이
        # 값 범위 안에 들어온다) - 그냥 출력이 상식적인 범위에 있는지를
        # 확인하는 sanity check. 색순응 메커니즘 자체의 검증은
        # TestChromaticAdaptationMechanism을 참고.
        ref = reference_patches_xyz_d50()
        neutrals = ref[18:24]
        xy = neutrals[:, :2] / neutrals.sum(axis=1, keepdims=True)
        mean_xy = xy.mean(axis=0)
        np.testing.assert_allclose(mean_xy, D50_XY, atol=0.002)

    def test_differs_from_linear_srgb_reference(self):
        # 같은 데이터셋이지만 최종 공간이 달라야 한다 - 값이 같으면
        # 변환이 안 걸린 것.
        xyz = reference_patches_xyz_d50()
        srgb = reference_patches_linear_srgb()
        self.assertFalse(np.allclose(xyz, srgb, atol=1e-6))


class TestChromaticAdaptationMechanism(unittest.TestCase):
    """reference_patches_xyz_d50()가 쓰는 colour.chromatic_adaptation()
    호출 패턴 자체를, 실제 데이터셋과 무관한 합성 케이스로 검증한다.

    ColorChecker24 데이터셋의 cc.illuminant는 D50에 너무 가까워서
    (TestReferencePatchesXyzD50 참고) 실제 데이터로는 색순응이 걸렸는지
    안 걸렸는지 구분이 안 된다. 여기서는 원본과 뚜렷이 다른 실제
    Illuminant C를 소스로, D50을 타깃으로 잡고 무채색이 아닌(색순응이
    항등변환이 되지 않는) 합성 XYZ 점 하나를 변환해서, Bradford CAT이
    실제로 값을 유의미하게 바꾸는지 확인한다."""

    def test_adaptation_from_illuminant_c_to_d50_changes_chromatic_point(self):
        illuminant_c_xy = colour.CCS_ILLUMINANTS[
            "CIE 1931 2 Degree Standard Observer"
        ]["C"]
        source_xyz = colour.xy_to_XYZ(illuminant_c_xy)
        target_xyz = colour.xy_to_XYZ(D50_XY)

        # 무채색이 아닌 임의의 합성 XYZ - 흰색/회색이면 색순응 전후로도
        # 크게 안 움직일 수 있어서 판별력이 없다.
        xyz = np.array([0.25, 0.40, 0.10])

        adapted = colour.chromatic_adaptation(
            xyz, source_xyz, target_xyz,
            method="Von Kries", transform="Bradford",
        )

        self.assertFalse(np.allclose(adapted, xyz, atol=1e-3))
        # 절대 위치도 확인 - 그냥 "달라지기만" 하는 게 아니라 상식적인
        # 크기의 변화인지(값이 폭주하거나 0이 되지 않는지)까지 본다.
        self.assertTrue(np.all(np.isfinite(adapted)))
        self.assertGreater(np.linalg.norm(adapted - xyz), 0.01)


class TestPatchDeltaEXyzD50(unittest.TestCase):
    def test_identical_input_gives_zero(self):
        ref = reference_patches_xyz_d50()
        de = patch_delta_e_xyz_d50(ref, ref)
        self.assertEqual(de.shape, (24,))
        np.testing.assert_allclose(de, np.zeros(24), atol=1e-9)

    def test_perturbed_input_gives_nonzero(self):
        ref = reference_patches_xyz_d50()
        perturbed = ref * 1.2
        de = patch_delta_e_xyz_d50(perturbed, ref)
        self.assertTrue(np.all(de > 0.5))

    def test_defaults_to_official_reference(self):
        ref = reference_patches_xyz_d50()
        explicit = patch_delta_e_xyz_d50(ref, ref)
        implicit = patch_delta_e_xyz_d50(ref)
        np.testing.assert_allclose(explicit, implicit, atol=1e-12)


class TestFitRecoversKnownMatrix(unittest.TestCase):
    def test_fit_color_matrix_recovers_the_matrix_used_to_make_targets(self):
        # 피팅 경로 자체가 정상인지 확인 - 알려진 3x3으로 타깃을 만들면
        # fit_color_matrix()가 그 3x3을 되찾아야 한다. (24, 3) 패치 샘플
        # 형태로 검증하는 게 중요하다: 실제 사용처가 (H, W, 3) 이미지가
        # 아니라 차트 패치 배열이기 때문.
        from hybrid_engine.core.raw_baseline import fit_color_matrix

        rng = np.random.default_rng(0)
        known = np.array([
            [0.8123, -0.1456, 0.0321],
            [-0.2345, 1.1234, 0.0987],
            [0.0456, -0.1987, 0.9012],
        ])
        sources = [rng.uniform(0.02, 0.9, size=(24, 3)) for _ in range(3)]
        targets = [s @ known for s in sources]

        fitted = fit_color_matrix(sources, targets)

        self.assertEqual(fitted.shape, (3, 3))
        np.testing.assert_allclose(fitted, known, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
