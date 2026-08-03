import importlib.util
import os
import unittest

import numpy as np

from gui.tabs.brand_preview import list_shipped_looks, run_brand_preview

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
