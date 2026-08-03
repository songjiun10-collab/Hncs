import importlib.util
import os
import unittest
from unittest.mock import patch

import numpy as np

from gui.tabs.brand_preview import list_shipped_looks, load_image, run_brand_preview

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DRIVER_PATH = os.path.join(_REPO_ROOT, ".claude", "skills", "run-hncs", "driver.py")


def _load_driver_module():
    """.claude/skills/run-hncs/driver.py는 점(.)으로 시작하는 디렉토리
    아래에 있어 일반적인 패키지 경로로 import할 수 없다 - 파일 경로로 직접
    로드한다."""
    spec = importlib.util.spec_from_file_location("run_hncs_driver", _DRIVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestListShippedLooks(unittest.TestCase):
    def test_includes_apply_hncs(self):
        looks = list_shipped_looks()
        self.assertIn(("brands.hasselblad", "apply_hncs"), looks)

    def test_excludes_video_frame_variants(self):
        looks = list_shipped_looks()
        self.assertTrue(all("video_frame" not in name for _, name in looks))


class TestListShippedLooksDrift(unittest.TestCase):
    def test_matches_run_hncs_driver_shipped_looks(self):
        driver = _load_driver_module()
        self.assertEqual(set(list_shipped_looks()), set(driver.shipped_looks()))


class TestLoadImage(unittest.TestCase):
    @patch("gui.tabs.brand_preview.quick_raw_preview")
    def test_raw_extension_uses_quick_raw_preview(self, mock_preview):
        expected = np.zeros((4, 4, 3), dtype=np.uint8)
        mock_preview.return_value = expected
        out = load_image("photo.3FR")
        mock_preview.assert_called_once_with("photo.3FR")
        self.assertIs(out, expected)

    @patch("gui.tabs.brand_preview.quick_raw_preview")
    def test_raw_extension_is_case_insensitive(self, mock_preview):
        mock_preview.return_value = np.zeros((4, 4, 3), dtype=np.uint8)
        load_image("photo.NEF")
        mock_preview.assert_called_once_with("photo.NEF")

    @patch("gui.tabs.brand_preview.cv2.imread")
    def test_non_raw_extension_uses_cv2_imread(self, mock_imread):
        expected = np.zeros((4, 4, 3), dtype=np.uint8)
        mock_imread.return_value = expected
        out = load_image("photo.jpg")
        mock_imread.assert_called_once_with("photo.jpg")
        self.assertIs(out, expected)


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
