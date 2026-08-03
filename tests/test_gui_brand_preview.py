import unittest

import numpy as np

from gui.tabs.brand_preview import list_shipped_looks, run_brand_preview


class TestListShippedLooks(unittest.TestCase):
    def test_includes_apply_hncs(self):
        looks = list_shipped_looks()
        self.assertIn(("brands.hasselblad", "apply_hncs"), looks)

    def test_excludes_video_frame_variants(self):
        looks = list_shipped_looks()
        self.assertTrue(all("video_frame" not in name for _, name in looks))


class TestRunBrandPreview(unittest.TestCase):
    def test_apply_hncs_preserves_shape(self):
        img = np.zeros((8, 8, 3), dtype=np.uint8)
        out = run_brand_preview("brands.hasselblad", "apply_hncs", img)
        self.assertEqual(out.shape, img.shape)

    def test_mono_preset_returns_2d(self):
        img = np.zeros((8, 8, 3), dtype=np.uint8)
        out = run_brand_preview("brands.fuji", "apply_acros", img)
        self.assertEqual(out.ndim, 2)


if __name__ == "__main__":
    unittest.main()
