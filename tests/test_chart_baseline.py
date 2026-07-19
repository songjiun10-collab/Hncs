import unittest

import numpy as np
import colour

from hybrid_engine.core import chart_baseline


def _synthetic_chart_linear(reference_linear_rgb, patch_px=120, gap=20, border=60):
    """reference_linear_rgb의 24개 색을 표준 4x6 배치로 렌더링한 합성
    차트 이미지(선형 RGB) - 실제 raw 파일 없이 detect_and_sample()을
    결정론적으로 검증하기 위한 용도."""
    srgb = colour.cctf_encoding(np.clip(reference_linear_rgb, 0.0, 1.0), function="sRGB")
    grid_w = 6 * patch_px + 5 * gap
    grid_h = 4 * patch_px + 3 * gap
    canvas = np.zeros((grid_h + 2 * border, grid_w + 2 * border, 3), dtype=np.float64)
    for i in range(24):
        row, col = divmod(i, 6)
        y0 = border + row * (patch_px + gap)
        x0 = border + col * (patch_px + gap)
        canvas[y0:y0 + patch_px, x0:x0 + patch_px] = srgb[i]
    return colour.cctf_decoding(canvas, function="sRGB")


class TestReferencePatches(unittest.TestCase):
    def test_shape_and_order(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        self.assertEqual(ref.shape, (24, 3))
        self.assertEqual(len(chart_baseline.PATCH_NAMES), 24)

    def test_white_patch_brighter_than_black_patch(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        white_idx = chart_baseline.PATCH_NAMES.index("white 9.5 (.05 D)")
        black_idx = chart_baseline.PATCH_NAMES.index("black 2 (1.5 D)")
        self.assertGreater(ref[white_idx].mean(), ref[black_idx].mean())

    def test_neutral_patches_are_roughly_gray(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        white_idx = chart_baseline.PATCH_NAMES.index("white 9.5 (.05 D)")
        r, g, b = ref[white_idx]
        self.assertLess(max(r, g, b) - min(r, g, b), 0.06)


class TestDetectAndSample(unittest.TestCase):
    def test_recovers_known_colors_from_synthetic_chart(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        linear = _synthetic_chart_linear(ref)
        samples = chart_baseline.detect_and_sample(linear, max_dim=2000, shrink=0.5)
        self.assertIsNotNone(samples)
        self.assertEqual(samples.shape, (24, 3))
        de = chart_baseline.patch_delta_e(samples, ref)
        self.assertLess(float(np.mean(de)), 1.0)

    def test_returns_none_when_no_chart_present(self):
        blank = np.full((400, 600, 3), 0.3, dtype=np.float64)
        samples = chart_baseline.detect_and_sample(blank, max_dim=800)
        self.assertIsNone(samples)


class TestPatchDeltaE(unittest.TestCase):
    def test_zero_for_identical_arrays(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        de = chart_baseline.patch_delta_e(ref, ref)
        np.testing.assert_allclose(de, np.zeros(24), atol=1e-6)

    def test_positive_for_different_arrays(self):
        ref = chart_baseline.reference_patches_linear_srgb()
        shifted = np.clip(ref + 0.1, 0.0, 1.0)
        de = chart_baseline.patch_delta_e(shifted, ref)
        self.assertTrue(np.all(de > 0.0))


if __name__ == "__main__":
    unittest.main()
