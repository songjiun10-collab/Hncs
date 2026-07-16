import unittest

import numpy as np

from core.stats import image_stats


def make_solid_bgr(value, size=(64, 64)):
    return np.full((size[0], size[1], 3), value, dtype=np.uint8)


class TestImageStats(unittest.TestCase):
    def test_solid_gray_image_percentiles_match_value(self):
        img = make_solid_bgr(128)
        s = image_stats(img)
        self.assertAlmostEqual(s["b2"], 128, delta=1)
        self.assertAlmostEqual(s["w995"], 128, delta=1)
        self.assertAlmostEqual(s["med"], 128, delta=1)

    def test_solid_gray_has_zero_saturation(self):
        img = make_solid_bgr(128)
        s = image_stats(img)
        self.assertEqual(s["sat"], 0)

    def test_black_image_has_full_dark_pct(self):
        img = make_solid_bgr(0)
        s = image_stats(img)
        self.assertAlmostEqual(s["dark_pct"], 100.0, places=1)

    def test_white_image_has_zero_dark_pct(self):
        img = make_solid_bgr(255)
        s = image_stats(img)
        self.assertAlmostEqual(s["dark_pct"], 0.0, places=1)

    def test_saturated_color_image_has_nonzero_sat(self):
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        img[:, :, 2] = 255  # pure red in BGR
        s = image_stats(img)
        self.assertGreater(s["sat"], 20)

    def test_half_dark_half_bright_gives_roughly_half_dark_pct(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:50, :, :] = 10   # dark half (< 40 threshold)
        img[50:, :, :] = 200  # bright half
        s = image_stats(img)
        self.assertAlmostEqual(s["dark_pct"], 50.0, delta=2)

    def test_returns_all_expected_keys(self):
        img = make_solid_bgr(100)
        s = image_stats(img)
        self.assertEqual(set(s.keys()), {"b2", "w995", "med", "sat", "dark_pct"})


if __name__ == "__main__":
    unittest.main()
