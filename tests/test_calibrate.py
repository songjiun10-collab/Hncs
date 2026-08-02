import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calibrate import _generation_for


class TestGenerationFor(unittest.TestCase):
    def test_cfv_passthrough(self):
        self.assertEqual(_generation_for("CFV 100C/907X"), "CFV 100C/907X")

    def test_x2d_passthrough(self):
        self.assertEqual(_generation_for("X2D 100C"), "X2D 100C")

    def test_x1d_ii_mapped(self):
        self.assertEqual(_generation_for("Hasselblad X1D II 50C"), "X1D II 50C")

    def test_x1d_mapped(self):
        self.assertEqual(_generation_for("Hasselblad X1D"), "X1D")

    def test_unknown_camera_passthrough(self):
        self.assertEqual(_generation_for("Some New Camera"), "Some New Camera")


if __name__ == "__main__":
    unittest.main()
