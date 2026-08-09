import unittest

import cv2
import numpy as np

from core.curve import film_curve
from core.engine import (
    apply_population_fit_look, apply_population_fit_look_video_frame,
    make_population_fit_look,
)


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
        out_high = apply_population_fit_look(self.img, toe_lift=20 / 255,
                                              shoulder_start=0.78,
                                              white_point=230 / 255, clahe_clip=1.25)
        self.assertFalse(np.array_equal(out_low, out_high))


class TestApplyPopulationFitLookVideoFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_different_toe_lift_changes_output(self):
        out_low = apply_population_fit_look_video_frame(
            self.img, toe_lift=1 / 255, shoulder_start=0.78, white_point=230 / 255)
        out_high = apply_population_fit_look_video_frame(
            self.img, toe_lift=20 / 255, shoulder_start=0.78, white_point=230 / 255)
        self.assertFalse(np.array_equal(out_low, out_high))

    def test_matches_tone_curve_only_no_clahe(self):
        # apply_population_fit_look()의 두 단계(CLAHE + 톤커브) 중 톤커브
        # 단계만 직접 재현해서 정확히 일치하는지 확인 - CLAHE가 정말
        # 생략됐는지를 결과값으로 못박는 테스트.
        lab = cv2.cvtColor(self.img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x, 10 / 255, 0.78, 230 / 255) * 255,
                       0, 255).astype(np.uint8)
        l_expected = cv2.LUT(l, lut)
        expected = cv2.cvtColor(cv2.merge((l_expected, a, b)), cv2.COLOR_LAB2BGR)

        out = apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        np.testing.assert_array_equal(out, expected)

    def test_differs_from_photo_mode_with_clahe(self):
        photo_out = apply_population_fit_look(
            self.img, toe_lift=10 / 255, shoulder_start=0.78,
            white_point=230 / 255, clahe_clip=1.25)
        video_out = apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        self.assertFalse(np.array_equal(photo_out, video_out))


class TestMakePopulationFitLook(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_matches_direct_call_with_same_args(self):
        fn = make_population_fit_look(toe_lift=10 / 255, shoulder_start=0.78,
                                       white_point=230 / 255, clahe_clip=1.25)
        direct = apply_population_fit_look(self.img, toe_lift=10 / 255, shoulder_start=0.78,
                                            white_point=230 / 255, clahe_clip=1.25)
        via_factory = fn(self.img)
        np.testing.assert_array_equal(direct, via_factory)

    def test_signature_exposes_bound_defaults(self):
        import inspect
        fn = make_population_fit_look(toe_lift=10 / 255, shoulder_start=0.78,
                                       white_point=230 / 255, clahe_clip=1.25)
        sig = inspect.signature(fn)
        self.assertAlmostEqual(sig.parameters["toe_lift"].default, 10 / 255)
        self.assertAlmostEqual(sig.parameters["shoulder_start"].default, 0.78)
        self.assertAlmostEqual(sig.parameters["white_point"].default, 230 / 255)
        self.assertAlmostEqual(sig.parameters["clahe_clip"].default, 1.25)

    def test_caller_can_override_bound_defaults(self):
        fn = make_population_fit_look(toe_lift=10 / 255, shoulder_start=0.78,
                                       white_point=230 / 255, clahe_clip=1.25)
        default_out = fn(self.img)
        overridden_out = fn(self.img, toe_lift=20 / 255)
        self.assertFalse(np.array_equal(default_out, overridden_out))


if __name__ == "__main__":
    unittest.main()
