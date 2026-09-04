"""tools/refit_x2dii_chart_combined_irls.py - unit test for the pure ΔE00
helper (no RAW/cv2 dependency) plus an import smoke test."""
import unittest

import numpy as np

from tools.refit_x2dii_chart_combined_irls import _mean_de


class TestMeanDe(unittest.TestCase):
    def test_zero_for_identical_patches(self):
        ref = np.tile(np.array([50.0, 60.0, 40.0]), (24, 1))
        self.assertAlmostEqual(_mean_de(ref, ref), 0.0, places=6)

    def test_positive_for_differing_patches(self):
        ref = np.tile(np.array([50.0, 60.0, 40.0]), (24, 1))
        samples = ref + 10.0
        self.assertGreater(_mean_de(samples, ref), 0.0)


if __name__ == "__main__":
    unittest.main()
