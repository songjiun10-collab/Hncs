"""tools/validate_dpreview_chart_brand.py - unit tests for the pure ΔE00/
RMSE helpers (no RAW/cv2 dependency, runs under default python3) plus an
import smoke test."""
import unittest
import os
import tempfile

import numpy as np

from tools.validate_dpreview_chart_brand import _find_raw_paths, _mean_de, _rmse_xyz


class TestFindRawPaths(unittest.TestCase):
    def test_extension_matching_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.rw2"), "wb").close()
            open(os.path.join(tmp, "b.RW2"), "wb").close()
            open(os.path.join(tmp, "c.Rw2"), "wb").close()
            self.assertEqual(
                [os.path.basename(p) for p in _find_raw_paths(tmp, "RW2")],
                ["a.rw2", "b.RW2", "c.Rw2"],
            )


class TestMeanDe(unittest.TestCase):
    def test_zero_for_identical_patches(self):
        ref = np.tile(np.array([50.0, 60.0, 40.0]), (24, 1))
        self.assertAlmostEqual(_mean_de(ref, ref), 0.0, places=6)

    def test_positive_for_differing_patches(self):
        ref = np.tile(np.array([50.0, 60.0, 40.0]), (24, 1))
        samples = ref + 10.0
        self.assertGreater(_mean_de(samples, ref), 0.0)


class TestRmseXyz(unittest.TestCase):
    def test_zero_for_identical_patches(self):
        ref = np.tile(np.array([0.4, 0.4, 0.4]), (24, 1))
        self.assertAlmostEqual(_rmse_xyz(ref, ref), 0.0, places=10)

    def test_matches_hand_computed_value(self):
        ref = np.zeros((2, 3))
        samples = np.array([[3.0, 4.0, 0.0], [0.0, 0.0, 0.0]])
        # sqrt(mean((3,4,0,0,0,0)^2)) = sqrt((9+16)/6)
        expected = np.sqrt(25.0 / 6.0)
        self.assertAlmostEqual(_rmse_xyz(samples, ref), expected, places=10)


if __name__ == "__main__":
    unittest.main()
