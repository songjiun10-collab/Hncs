import unittest

import numpy as np

from tools.build_before_after_demo import BAR_H, build_before_after


class TestBuildBeforeAfter(unittest.TestCase):
    def test_canvas_dimensions(self):
        rng = np.random.default_rng(0)
        source = rng.integers(0, 255, (80, 120, 3), dtype=np.uint8)
        canvas = build_before_after(source)
        self.assertEqual(canvas.size, (2 * 120, 80 + BAR_H))

    def test_after_side_differs_from_original(self):
        rng = np.random.default_rng(1)
        source = rng.integers(0, 255, (60, 60, 3), dtype=np.uint8)
        canvas = np.array(build_before_after(source))
        before = canvas[BAR_H:, :60]
        after = canvas[BAR_H:, 60:]
        self.assertFalse(np.array_equal(before, after))


if __name__ == "__main__":
    unittest.main()
