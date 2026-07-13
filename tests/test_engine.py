import unittest

import numpy as np

from core.engine import apply_population_fit_look


class TestApplyPopulationFitLook(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_population_fit_look(self.img, toe_lift=10 / 255,
                                         shoulder_start=0.78,
                                         white_point=230 / 255, clahe_clip=1.25)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_handles_solid_black(self):
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        out = apply_population_fit_look(img, toe_lift=10 / 255,
                                         shoulder_start=0.78,
                                         white_point=230 / 255, clahe_clip=1.25)
        self.assertEqual(out.shape, img.shape)

    def test_handles_solid_white(self):
        img = np.full((64, 64, 3), 255, dtype=np.uint8)
        out = apply_population_fit_look(img, toe_lift=10 / 255,
                                         shoulder_start=0.78,
                                         white_point=230 / 255, clahe_clip=1.25)
        self.assertEqual(out.shape, img.shape)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_population_fit_look(self.img, toe_lift=10 / 255,
                                   shoulder_start=0.78,
                                   white_point=230 / 255, clahe_clip=1.25)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_different_toe_lift_changes_output(self):
        out_low = apply_population_fit_look(self.img, toe_lift=1 / 255,
                                             shoulder_start=0.78,
                                             white_point=230 / 255, clahe_clip=1.25)
        out_high = apply_population_fit_look(self.img, toe_lift=30 / 255,
                                              shoulder_start=0.78,
                                              white_point=230 / 255, clahe_clip=1.25)
        self.assertFalse(np.array_equal(out_low, out_high))


if __name__ == "__main__":
    unittest.main()
