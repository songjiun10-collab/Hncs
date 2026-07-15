import unittest

import numpy as np

from tools.iso_noise import estimate_noise_flat_patch, estimate_noise_sigma


class TestEstimateNoiseSigma(unittest.TestCase):
    def test_constant_image_has_zero_noise(self):
        gray = np.full((16, 16), 128, dtype=np.uint8)
        self.assertAlmostEqual(estimate_noise_sigma(gray), 0.0, places=6)

    def test_noisy_image_has_positive_noise(self):
        rng = np.random.default_rng(0)
        gray = rng.integers(0, 256, size=(32, 32), dtype=np.uint8)
        self.assertGreater(estimate_noise_sigma(gray), 0.0)


class TestEstimateNoiseFlatPatch(unittest.TestCase):
    def test_dimension_exactly_divisible_by_patch_size_is_not_skipped(self):
        # Regression test for the 2026-07 off-by-one fix: when h (or w) is an
        # exact multiple of patch_size, range(0, h - patch_size, patch_size)
        # drops the last row/column of patches entirely. A single
        # patch_size x patch_size image is the minimal case that triggers it
        # (h - patch_size == 0, so the old range was empty and the function
        # returned None instead of a value).
        gray = np.full((32, 32), 100, dtype=np.uint8)
        result = estimate_noise_flat_patch(gray, patch_size=32)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_last_row_of_patches_is_included_in_flat_selection(self):
        # 64x64 image split into a 2x2 patch grid at patch_size=32. Only the
        # bottom-right patch (y=32, x=32) is flat; the other three are noisy.
        # If the last row (y=32) were dropped by an off-by-one bug, the flat
        # patch would never be considered and the result would not be ~0.
        rng = np.random.default_rng(1)
        gray = rng.integers(60, 200, size=(64, 64)).astype(np.uint8)
        gray[32:64, 32:64] = 100  # flat, lowest-variance patch
        result = estimate_noise_flat_patch(gray, patch_size=32, flat_fraction=0.1)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.0, places=6)

    def test_picks_lowest_variance_patches(self):
        rng = np.random.default_rng(2)
        gray = rng.integers(0, 256, size=(64, 64)).astype(np.uint8)
        gray[0:16, 0:16] = 50  # one flat 16x16 patch among noisy 16x16 patches
        noisy_only = estimate_noise_flat_patch(
            rng.integers(0, 256, size=(64, 64)).astype(np.uint8), patch_size=16, flat_fraction=0.1
        )
        flat_included = estimate_noise_flat_patch(gray, patch_size=16, flat_fraction=0.1)
        self.assertIsNotNone(noisy_only)
        self.assertIsNotNone(flat_included)
        self.assertLess(flat_included, noisy_only)

    def test_image_smaller_than_patch_size_returns_none(self):
        gray = np.full((8, 8), 100, dtype=np.uint8)
        self.assertIsNone(estimate_noise_flat_patch(gray, patch_size=32))


if __name__ == "__main__":
    unittest.main()
