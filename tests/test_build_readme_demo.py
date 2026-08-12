import unittest

import numpy as np

from tools.build_readme_demo import CELL_H, CELL_W, LABEL_H, _short_label, build_grid


class TestShortLabel(unittest.TestCase):
    def test_original_entry(self):
        self.assertEqual(_short_label("(original)", "original"), "(original)")

    def test_strips_module_prefix_and_apply_prefix(self):
        self.assertEqual(_short_label("brands.fuji", "apply_classic_chrome_v2"),
                          "fuji\nclassic_chrome_v2")


class TestBuildGrid(unittest.TestCase):
    def test_grid_covers_every_shipped_look_plus_original(self):
        # 합성 이미지(실제 사진 데이터 불필요) - CLAHE 등이 너무 작은
        # 이미지에서 에러 안 내는지도 같이 확인.
        rng = np.random.default_rng(0)
        source = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
        grid = build_grid(source, cols=9)

        from gui.tabs.brand_preview import list_shipped_looks
        n = len(list_shipped_looks()) + 1  # +원본
        rows = (n + 9 - 1) // 9
        self.assertEqual(grid.size, (9 * CELL_W, rows * (CELL_H + LABEL_H)))


if __name__ == "__main__":
    unittest.main()
