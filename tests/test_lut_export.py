import os
import tempfile
import unittest

import numpy as np

from core.lut_export import build_identity_grid, bake_lut_from_function, write_cube_file


class TestBuildIdentityGrid(unittest.TestCase):
    def test_shape(self):
        grid = build_identity_grid(size=5)
        self.assertEqual(grid.shape, (5, 5, 5, 3))

    def test_indices_map_to_correct_channel(self):
        size = 5
        axis = np.linspace(0.0, 1.0, size)
        grid = build_identity_grid(size=size)
        for b_idx in range(size):
            for g_idx in range(size):
                for r_idx in range(size):
                    expected = [axis[r_idx], axis[g_idx], axis[b_idx]]
                    np.testing.assert_allclose(grid[b_idx, g_idx, r_idx], expected, atol=1e-12)


class TestBakeLutFromFunction(unittest.TestCase):
    def test_identity_function_reproduces_grid(self):
        size = 5
        grid = build_identity_grid(size=size)
        lut = bake_lut_from_function(lambda bgr: bgr, size=size)
        # uint8 round-trip quantization only, not exact float equality
        np.testing.assert_allclose(lut, grid, atol=1.0 / 255.0)

    def test_function_transform_flows_through_correctly(self):
        size = 5
        axis = np.linspace(0.0, 1.0, size)
        lut = bake_lut_from_function(lambda bgr: 255 - bgr, size=size)
        for b_idx in range(size):
            for g_idx in range(size):
                for r_idx in range(size):
                    expected = [1 - axis[r_idx], 1 - axis[g_idx], 1 - axis[b_idx]]
                    np.testing.assert_allclose(lut[b_idx, g_idx, r_idx], expected, atol=2.0 / 255.0)

    def test_grayscale_output_raises(self):
        def grayscale_fn(bgr):
            return bgr[..., 0]

        with self.assertRaises(ValueError):
            bake_lut_from_function(grayscale_fn, size=5)

    def test_kwargs_forwarded_to_function(self):
        def scaled_fn(bgr, factor=1.0):
            return np.clip(bgr.astype(np.float64) * factor, 0, 255).astype(np.uint8)

        lut_full = bake_lut_from_function(scaled_fn, size=5, factor=1.0)
        lut_half = bake_lut_from_function(scaled_fn, size=5, factor=0.5)
        self.assertFalse(np.allclose(lut_full, lut_half))


class TestWriteCubeFile(unittest.TestCase):
    def test_header_and_line_count(self):
        size = 4
        lut = build_identity_grid(size=size)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.cube")
            write_cube_file(lut, path, title="test preset")
            with open(path, encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            self.assertEqual(lines[0], 'TITLE "test preset"')
            self.assertEqual(lines[1], f"LUT_3D_SIZE {size}")
            self.assertEqual(len(lines), 4 + size ** 3)

    def test_no_title_omits_title_line(self):
        lut = build_identity_grid(size=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.cube")
            write_cube_file(lut, path)
            with open(path, encoding="utf-8") as f:
                first_line = f.readline()
            self.assertTrue(first_line.startswith("LUT_3D_SIZE"))

    def test_r_varies_fastest_per_adobe_spec(self):
        size = 4
        axis = np.linspace(0.0, 1.0, size)
        lut = build_identity_grid(size=size)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.cube")
            write_cube_file(lut, path)
            with open(path, encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            data_lines = lines[3:]  # no title -> header is 3 lines
            # first two data rows: b_idx=g_idx=0, r_idx=0 then r_idx=1 -
            # only the R value (first column) should change
            row0 = [float(x) for x in data_lines[0].split()]
            row1 = [float(x) for x in data_lines[1].split()]
            self.assertAlmostEqual(row0[1], row1[1], places=5)
            self.assertAlmostEqual(row0[2], row1[2], places=5)
            self.assertAlmostEqual(row1[0], axis[1], places=5)

    def test_values_are_clipped_to_unit_range(self):
        lut = np.full((2, 2, 2, 3), 5.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.cube")
            write_cube_file(lut, path)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn("5.000000", content)
            self.assertIn("1.000000", content)


if __name__ == "__main__":
    unittest.main()
