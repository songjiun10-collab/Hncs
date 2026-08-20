import unittest

import numpy as np

from core.validation import is_image_array_usable, region_hue


def make_solid_bgr(value, size=(200, 200)):
    return np.full((size[0], size[1], 3), value, dtype=np.uint8)


class TestIsImageArrayUsable(unittest.TestCase):
    def test_none_is_unusable(self):
        self.assertFalse(is_image_array_usable(None))

    def test_too_small_is_unusable(self):
        img = make_solid_bgr(128, size=(50, 50))
        self.assertFalse(is_image_array_usable(img))

    def test_normal_textured_image_is_usable(self):
        rng = np.random.default_rng(0)
        img = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
        self.assertTrue(is_image_array_usable(img))

    def test_fully_degenerate_image_is_unusable(self):
        # 모든 행이 단색(std=0)인 이미지 - CDN 손상 패턴 재현
        img = make_solid_bgr(0)
        self.assertFalse(is_image_array_usable(img))

    def test_partial_corruption_below_threshold_still_usable(self):
        rng = np.random.default_rng(1)
        img = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
        # 상위 1%(2행)만 단색으로 손상 - 기본 threshold 2% 이하라 통과해야 함
        img[:2, :, :] = 100
        self.assertTrue(is_image_array_usable(img, max_degenerate_row_frac=0.02))

    def test_corruption_above_threshold_is_unusable(self):
        rng = np.random.default_rng(2)
        img = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
        # 하위 50%가 손상(imaging-resource CDN 패턴: 디코드가 중간에 멈추고
        # 나머지가 텅 빔) - 명백히 threshold를 넘어야 함
        img[100:, :, :] = 50
        self.assertFalse(is_image_array_usable(img, max_degenerate_row_frac=0.02))


class TestRegionHue(unittest.TestCase):
    def test_empty_box_returns_none(self):
        img = make_solid_bgr(128)
        result = region_hue(img, box=(0, 0, 0, 0))
        self.assertIsNone(result)

    def test_returns_float_for_valid_box(self):
        img = make_solid_bgr(128)
        result = region_hue(img, box=(0, 0, 100, 100))
        self.assertIsInstance(result, float)

    def test_solid_color_hue_matches_hsv_conversion(self):
        import cv2
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:, :, 2] = 200  # red-ish in BGR
        img[:, :, 1] = 50
        expected_hue = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[0, 0, 0]
        result = region_hue(img, box=(0, 0, 100, 100))
        self.assertAlmostEqual(result, float(expected_hue), delta=1)


if __name__ == "__main__":
    unittest.main()
