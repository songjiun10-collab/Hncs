import unittest

import cv2
import numpy as np

from core.brand_classifier import extract_features
from core.photo_signature import compute_signature


class TestComputeSignature(unittest.TestCase):
    def test_uniform_gray_image(self):
        img = np.full((20, 20, 3), 128, dtype=np.uint8)
        sig = compute_signature(img)

        self.assertEqual(sig["b2"], 128.0)
        self.assertEqual(sig["w995"], 128.0)
        self.assertEqual(sig["median"], 128.0)
        self.assertEqual(sig["dark_pct"], 0.0)
        self.assertEqual(sig["sat_mean"], 0.0)
        self.assertEqual(sig["hue_mean"], 0.0)
        self.assertEqual(sig["a_p1"], 128.0)
        self.assertEqual(sig["a_p99"], 128.0)
        self.assertEqual(sig["b_p1"], 128.0)
        self.assertEqual(sig["b_p99"], 128.0)
        self.assertEqual(sig["a_std"], 0.0)
        self.assertEqual(sig["b_std"], 0.0)
        self.assertEqual(sig["chroma_mean"], 0.0)
        self.assertEqual(sig["chroma_p99"], 0.0)

    def test_pure_red_patch(self):
        img = np.zeros((20, 20, 3), dtype=np.uint8)
        img[..., 2] = 255  # BGR - 순수 빨강

        sig = compute_signature(img)

        self.assertEqual(sig["b2"], 76.0)
        self.assertEqual(sig["w995"], 76.0)
        self.assertEqual(sig["median"], 76.0)
        self.assertEqual(sig["dark_pct"], 0.0)
        self.assertEqual(sig["sat_mean"], 255.0)
        self.assertEqual(sig["hue_mean"], 0.0)
        self.assertEqual(sig["a_p1"], 208.0)
        self.assertEqual(sig["a_p99"], 208.0)
        self.assertEqual(sig["b_p1"], 195.0)
        self.assertEqual(sig["b_p99"], 195.0)
        self.assertAlmostEqual(sig["chroma_mean"], 104.350371, places=4)
        self.assertAlmostEqual(sig["chroma_p99"], 104.350371, places=4)

    def test_circular_hue_mean_handles_wraparound(self):
        # OpenCV H=2와 H=177은 저장 단위(0~179)로는 멀어 보이지만 실제
        # 색상각으로는 4도/354도 - 0도(빨강) 바로 양옆에 붙어있는 거의
        # 같은 색이다. HSV->BGR 왕복 변환으로 정확한 H값을 보장해서
        # 이미지를 구성한다.
        top_hsv = np.zeros((10, 20, 3), dtype=np.uint8)
        top_hsv[..., 0] = 2
        top_hsv[..., 1] = 255
        top_hsv[..., 2] = 255
        bottom_hsv = np.zeros((10, 20, 3), dtype=np.uint8)
        bottom_hsv[..., 0] = 177
        bottom_hsv[..., 1] = 255
        bottom_hsv[..., 2] = 255
        top_bgr = cv2.cvtColor(top_hsv, cv2.COLOR_HSV2BGR)
        bottom_bgr = cv2.cvtColor(bottom_hsv, cv2.COLOR_HSV2BGR)
        img = np.vstack([top_bgr, bottom_bgr])

        sig = compute_signature(img)

        # 올바른 원형평균은 179.5(저장 단위, wraparound 경계) 근처여야
        # 하고, 틀린 산술평균(89.5, 저장 단위로 정반대 - 청록/녹색 쪽)과는
        # 뚜렷이 달라야 한다.
        self.assertAlmostEqual(sig["hue_mean"], 179.5, places=1)
        self.assertGreater(abs(sig["hue_mean"] - 89.5), 50)

    def test_output_feeds_directly_into_extract_features(self):
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        sig = compute_signature(img)

        X, feature_names = extract_features([sig], feature_set="tone_color_gamut")

        self.assertEqual(X.shape, (1, 15))
        self.assertEqual(len(feature_names), 15)


if __name__ == "__main__":
    unittest.main()
