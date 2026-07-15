import unittest

import numpy as np

from core.denoise import denoise


def _noisy_image(shape=(32, 32, 3), seed=0):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=shape, dtype=np.uint8)


class TestDenoise(unittest.TestCase):
    def test_nlm_preserves_shape_and_dtype(self):
        img = _noisy_image()
        out = denoise(img, strength=5, method="nlm")
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, img.dtype)

    def test_bilateral_preserves_shape_and_dtype(self):
        img = _noisy_image()
        out = denoise(img, strength=5, method="bilateral")
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, img.dtype)

    def test_reduces_variance_on_noisy_flat_region(self):
        # Pure uniform random noise has no spatial correlation for NLM/bilateral
        # to exploit, so use a flat base plus Gaussian noise instead - the
        # realistic case these filters are meant to clean up.
        rng = np.random.default_rng(0)
        base = np.full((48, 48, 3), 128, dtype=np.float64)
        noisy = np.clip(base + rng.normal(0, 25, base.shape), 0, 255).astype(np.uint8)
        out = denoise(noisy, strength=10, method="nlm")
        self.assertLess(out.astype(np.float64).var(), noisy.astype(np.float64).var())

    def test_unknown_method_raises(self):
        img = _noisy_image()
        with self.assertRaises(ValueError):
            denoise(img, method="bogus")


if __name__ == "__main__":
    unittest.main()
