import unittest

import numpy as np

from tools.build_hybrid_engine_demo import BAR_H, _load_profile, _resize_max_dim, build_before_after


class TestLoadProfile(unittest.TestCase):
    def test_loads_hasselblad_profile_without_comment_key(self):
        profile = _load_profile("hasselblad")
        self.assertNotIn("_comment", profile)
        self.assertIsInstance(profile, dict)
        self.assertGreater(len(profile), 0)


class TestResizeMaxDim(unittest.TestCase):
    def test_downsamples_when_over_limit(self):
        img = np.zeros((200, 100, 3), dtype=np.uint8)
        out = _resize_max_dim(img, max_dim=50)
        self.assertEqual(max(out.shape[:2]), 50)

    def test_leaves_small_image_untouched(self):
        img = np.zeros((30, 20, 3), dtype=np.uint8)
        out = _resize_max_dim(img, max_dim=50)
        self.assertEqual(out.shape, img.shape)


class TestBuildBeforeAfter(unittest.TestCase):
    def test_crops_to_shared_min_dimensions(self):
        rng = np.random.default_rng(0)
        original = rng.integers(0, 255, (60, 90, 3), dtype=np.uint8)
        rendered = rng.integers(0, 255, (50, 80, 3), dtype=np.uint8)
        canvas = build_before_after(original, rendered, "test label")
        self.assertEqual(canvas.size, (2 * 80, 50 + BAR_H))


if __name__ == "__main__":
    unittest.main()
