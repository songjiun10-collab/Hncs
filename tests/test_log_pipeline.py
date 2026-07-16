import os
import tempfile
import unittest

import numpy as np

from core.log_pipeline import (
    LOG_SPACES, apply_exposure, auto_exposure_average, to_log_space,
    apply_cube_lut, to_16bit_bgr,
)

_IDENTITY_CUBE = """TITLE "Identity"
LUT_3D_SIZE 2
0.0 0.0 0.0
1.0 0.0 0.0
0.0 1.0 0.0
1.0 1.0 0.0
0.0 0.0 1.0
1.0 0.0 1.0
0.0 1.0 1.0
1.0 1.0 1.0
"""


class TestApplyExposure(unittest.TestCase):
    def test_zero_ev_is_passthrough(self):
        img = np.full((4, 4, 3), 0.3)
        out = apply_exposure(img, ev=0.0)
        self.assertIs(out, img)

    def test_positive_ev_brightens(self):
        img = np.full((4, 4, 3), 0.1)
        out = apply_exposure(img, ev=1.0)
        np.testing.assert_allclose(out, img * 2.0)

    def test_negative_ev_darkens(self):
        img = np.full((4, 4, 3), 0.4)
        out = apply_exposure(img, ev=-1.0)
        np.testing.assert_allclose(out, img * 0.5)


class TestAutoExposureAverage(unittest.TestCase):
    def test_scales_mean_to_target_gray(self):
        img = np.full((8, 8, 3), 0.09)
        out = auto_exposure_average(img, target_gray=0.18)
        self.assertAlmostEqual(float(np.mean(out)), 0.18, places=6)

    def test_all_zero_image_is_unchanged(self):
        img = np.zeros((4, 4, 3))
        out = auto_exposure_average(img)
        np.testing.assert_array_equal(out, img)


class TestToLogSpace(unittest.TestCase):
    def test_unknown_log_space_raises(self):
        img = np.full((4, 4, 3), 0.18)
        with self.assertRaises(ValueError):
            to_log_space(img, "not-a-real-log-space")

    def test_preserves_shape(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(6, 5, 3))
        out = to_log_space(img, "V-Log")
        self.assertEqual(out.shape, img.shape)

    def test_middle_gray_encodes_to_documented_v_log_value(self):
        # Panasonic V-Log spec: 18% middle gray in a matching gamut encodes
        # to roughly 0.42-0.46 (matches core/log_pipeline.py's docstring
        # caveat that this isn't independently re-derived, just uses
        # colour-science's own curve definitions).
        img = np.full((2, 2, 3), 0.18)
        out = to_log_space(img, "V-Log")
        self.assertTrue(np.all((out > 0.3) & (out < 0.6)))

    def test_all_log_spaces_resolve_without_error(self):
        img = np.full((2, 2, 3), 0.18)
        for name in LOG_SPACES:
            with self.subTest(log_space=name):
                out = to_log_space(img, name)
                self.assertEqual(out.shape, img.shape)
                self.assertTrue(np.all(np.isfinite(out)))


class TestApplyCubeLut(unittest.TestCase):
    def test_identity_lut_roundtrips_values(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "identity.cube")
            with open(path, "w") as f:
                f.write(_IDENTITY_CUBE)
            img = np.array([[[0.2, 0.5, 0.8]]])
            out = apply_cube_lut(img, path)
            np.testing.assert_allclose(out, img, atol=1e-6)


class TestTo16BitBgr(unittest.TestCase):
    def test_dtype_and_channel_order(self):
        img = np.zeros((2, 2, 3))
        img[0, 0] = [1.0, 0.0, 0.0]  # pure red in RGB
        out = to_16bit_bgr(img)
        self.assertEqual(out.dtype, np.uint16)
        # BGR order: red channel should land in index 2, not 0
        self.assertEqual(out[0, 0, 2], 65535)
        self.assertEqual(out[0, 0, 0], 0)

    def test_out_of_range_values_are_clipped(self):
        img = np.array([[[-0.5, 1.5, 0.5]]])  # RGB: R=-0.5, G=1.5, B=0.5
        out = to_16bit_bgr(img)
        self.assertEqual(out[0, 0, 2], 0)      # R=-0.5 -> clipped to 0 (index 2 in BGR)
        self.assertEqual(out[0, 0, 1], 65535)  # G=1.5 -> clipped to 1.0 (index 1 in BGR)


if __name__ == "__main__":
    unittest.main()
