import unittest

import numpy as np

from tools.evaluate_hncs_structural import _pair_names, _resize_max_dim


class TestPairNames(unittest.TestCase):
    def test_returns_13_real_pairs(self):
        names = _pair_names()
        self.assertEqual(len(names), 13)

    def test_excludes_x2dii_chart_files(self):
        names = _pair_names()
        self.assertFalse(any("x2dii-chart" in n for n in names))

    def test_names_are_jpeg_basenames(self):
        names = _pair_names()
        self.assertTrue(all(n.endswith(".jpg") for n in names))


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(1000, 2000, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertLessEqual(max(out.shape[:2]), 512)
        # aspect ratio preserved (within 1px rounding)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 2000 / 1000, places=1)

    def test_preserves_channel_count(self):
        img = np.random.default_rng(2).uniform(0, 1, size=(600, 300, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertEqual(out.shape[2], 3)


if __name__ == "__main__":
    unittest.main()
