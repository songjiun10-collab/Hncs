import unittest
from unittest.mock import patch

import numpy as np

from tools.build_hybrid_engine_demo_more import BAR_H, ROW_PAD, build_grid, build_row


class TestBuildRow(unittest.TestCase):
    def test_row_dimensions_scale_to_half_width(self):
        rng = np.random.default_rng(0)
        original = rng.integers(0, 255, (60, 90, 3), dtype=np.uint8)
        rendered = rng.integers(0, 255, (60, 90, 3), dtype=np.uint8)
        row = build_row(original, rendered, "label", half_width=40)
        expected_h = round(60 * (40 / 90))
        self.assertEqual(row.size, (2 * 40, expected_h + BAR_H))


class TestBuildGrid(unittest.TestCase):
    def test_stacks_rows_with_consistent_width(self):
        rng = np.random.default_rng(1)

        def fake_render(raw_path, profile):
            return rng.integers(0, 255, (60, 90, 3), dtype=np.uint8)

        def fake_load(jpeg_path, max_dim=900):
            return rng.integers(0, 255, (60, 90, 3), dtype=np.uint8)

        pairs = [("a.RAF", "a.jpg"), ("b.RAF", "b.jpg"), ("c.RAF", "c.jpg")]
        with patch("tools.build_hybrid_engine_demo_more.render_with_profile", side_effect=fake_render), \
             patch("tools.build_hybrid_engine_demo_more._load_bgr_exif_corrected", side_effect=fake_load):
            grid = build_grid(pairs)

        # 모든 행이 같은 너비(HALF_WIDTH*2)로 정규화되므로 검은 여백 없이 쌓인다.
        expected_row_count = len(pairs)
        self.assertGreater(grid.height, expected_row_count * BAR_H)
        self.assertEqual((grid.height + ROW_PAD) % expected_row_count, 0)


if __name__ == "__main__":
    unittest.main()
