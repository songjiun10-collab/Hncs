import unittest

import numpy as np

from core.lut import apply_lut, ensure_uint8


class TestEnsureUint8(unittest.TestCase):
    def test_uint8_input_passed_through_unchanged(self):
        rng = np.random.default_rng(0)
        img = rng.integers(0, 256, (4, 4, 3), dtype=np.uint8)
        out = ensure_uint8(img)
        self.assertIs(out, img)

    def test_float_zero_one_is_scaled_to_uint8_range(self):
        img = np.array([[[0.0, 0.5, 1.0]]], dtype=np.float64)
        out = ensure_uint8(img)
        self.assertEqual(out.dtype, np.uint8)
        np.testing.assert_array_equal(out, [[[0, 127, 255]]])

    def test_float_out_of_range_is_clipped(self):
        img = np.array([[[-1.0, 2.0]]], dtype=np.float64)
        out = ensure_uint8(img)
        np.testing.assert_array_equal(out, [[[0, 255]]])


class TestApplyLut(unittest.TestCase):
    def test_identity_lut_returns_same_values(self):
        rng = np.random.default_rng(1)
        img = rng.integers(0, 256, (8, 8, 3), dtype=np.uint8)
        identity = np.arange(256, dtype=np.uint8)
        out = apply_lut(img, identity)
        np.testing.assert_array_equal(out, img)
        self.assertEqual(out.shape, img.shape)

    def test_converts_float_input_before_applying_lut(self):
        img = np.array([[[0.0, 1.0, 0.5]]], dtype=np.float64)
        identity = np.arange(256, dtype=np.uint8)
        out = apply_lut(img, identity)
        self.assertEqual(out.dtype, np.uint8)
        np.testing.assert_array_equal(out, [[[0, 255, 127]]])

    def test_lut_remaps_values(self):
        img = np.full((4, 4, 3), 100, dtype=np.uint8)
        invert = np.array([255 - i for i in range(256)], dtype=np.uint8)
        out = apply_lut(img, invert)
        self.assertTrue(np.all(out == 155))


if __name__ == "__main__":
    unittest.main()
