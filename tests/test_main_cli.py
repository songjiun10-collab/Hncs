import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from hybrid_engine.main import resolve_profile_name, maybe_downsample
from hybrid_engine.utils.io import save_jpeg8, load_image_linear


class TestResolveProfileName(unittest.TestCase):
    def test_explicit_valid_profile_is_used_as_is(self):
        name, error = resolve_profile_name("dummy.raw", "hasselblad")
        self.assertEqual(name, "hasselblad")
        self.assertIsNone(error)

    def test_explicit_invalid_profile_is_an_error(self):
        name, error = resolve_profile_name("dummy.raw", "nonexistent_brand")
        self.assertIsNone(name)
        self.assertIn("nonexistent_brand", error)

    @mock.patch("hybrid_engine.main.read_make_model")
    def test_exif_autodetect_recognized_camera_with_profile(self, mock_read):
        mock_read.return_value = ("Hasselblad", "X2D 100C")
        name, error = resolve_profile_name("dummy.raw", None)
        self.assertEqual(name, "hasselblad")
        self.assertIsNone(error)

    @mock.patch("hybrid_engine.main.read_make_model")
    def test_exif_autodetect_unrecognized_camera_is_an_error(self, mock_read):
        mock_read.return_value = (None, None)
        name, error = resolve_profile_name("dummy.raw", None)
        self.assertIsNone(name)
        self.assertIn("못 알아봄", error)

    @mock.patch("hybrid_engine.main.read_make_model")
    def test_exif_autodetect_recognized_camera_without_profile_is_an_error(self, mock_read):
        mock_read.return_value = ("SONY", "A7 IV")
        name, error = resolve_profile_name("dummy.raw", None)
        self.assertIsNone(name)
        self.assertIn("sony", error)


class TestSaveJpeg8(unittest.TestCase):
    def test_round_trip_preserves_midtone_value_closely(self):
        rgb = np.full((8, 8, 3), 0.5, dtype=np.float64)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.jpg")
            save_jpeg8(rgb, path, quality=95)
            self.assertTrue(os.path.exists(path))
            loaded = load_image_linear(path)
            self.assertEqual(loaded.shape, rgb.shape)
            self.assertTrue(np.allclose(loaded, rgb, atol=0.03))

    def test_clips_out_of_range_values(self):
        rgb = np.array([[[1.5, -0.2, 0.5]]], dtype=np.float64)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.jpg")
            save_jpeg8(rgb, path)
            loaded = load_image_linear(path)
            self.assertTrue(np.all(loaded >= -1e-6))


class TestMaybeDownsample(unittest.TestCase):
    def test_below_cap_is_unchanged(self):
        rgb = np.zeros((100, 200, 3), dtype=np.float64)
        out = maybe_downsample(rgb, max_megapixels=1.0)
        self.assertIs(out, rgb)

    def test_above_cap_is_downsampled_preserving_aspect_ratio(self):
        rgb = np.zeros((1000, 2000, 3), dtype=np.float64)  # 2.0MP, 1:2 종횡비
        out = maybe_downsample(rgb, max_megapixels=0.5)
        h, w = out.shape[:2]
        self.assertLessEqual(h * w / 1e6, 0.5 * 1.05)  # 반올림 여유
        self.assertAlmostEqual(w / h, 2.0, delta=0.05)

    def test_zero_means_unlimited(self):
        rgb = np.zeros((1000, 2000, 3), dtype=np.float64)
        out = maybe_downsample(rgb, max_megapixels=0)
        self.assertIs(out, rgb)


if __name__ == "__main__":
    unittest.main()
