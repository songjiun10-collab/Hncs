import os
import tempfile
import unittest

import cv2
import numpy as np

from tools.video_engine import SUPPORTED_BRANDS, brand_video_params, process_video


def _make_synthetic_video(path, num_frames=10, width=64, height=48, fps=24.0, seed=0):
    """그라디언트 배경 + 색 패치, 프레임마다 노이즈를 섞어 CLAHE 타일
    히스토그램이 프레임마다 달라지게 만든 합성 비디오 (레포에 실제
    카메라 비디오 샘플이 없어 유닛 테스트는 합성 데이터로 진행)."""
    rng = np.random.default_rng(seed)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    x = np.linspace(0, 255, width, dtype=np.uint8)
    gradient_row = np.tile(x, (height, 1))
    base = np.stack([gradient_row, gradient_row, gradient_row], axis=-1).astype(np.int16)
    for _ in range(num_frames):
        noise = rng.integers(-15, 16, base.shape, dtype=np.int16)
        frame = np.clip(base + noise, 0, 255).astype(np.uint8)
        frame[10:20, 10:20] = (200, 50, 50)  # BGR 색 패치
        writer.write(frame)
    writer.release()


class TestBrandVideoParams(unittest.TestCase):
    def test_supported_brands_has_exactly_ten(self):
        self.assertEqual(len(SUPPORTED_BRANDS), 10)
        self.assertEqual(SUPPORTED_BRANDS, frozenset({
            "canon", "leica", "nikon", "olympus", "panasonic",
            "pentax", "phaseone", "ricoh_gr", "sigma", "sony",
        }))

    def test_canon_params_match_brands_canon_defaults(self):
        toe_lift, shoulder_start, white_point = brand_video_params("canon")
        self.assertAlmostEqual(toe_lift, 15.0 / 255)
        self.assertAlmostEqual(shoulder_start, 0.78)
        self.assertAlmostEqual(white_point, 239.1 / 255)

    def test_unsupported_brand_raises_value_error(self):
        with self.assertRaises(ValueError):
            brand_video_params("fuji")

    def test_unsupported_brand_error_lists_supported_names(self):
        with self.assertRaises(ValueError) as ctx:
            brand_video_params("hasselblad")
        message = str(ctx.exception)
        for name in SUPPORTED_BRANDS:
            self.assertIn(name, message)


class TestProcessVideo(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.input_path = os.path.join(self.tmpdir, "input.mp4")
        self.output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video(self.input_path)

    def test_output_file_created_and_readable(self):
        frame_count = process_video(self.input_path, self.output_path, "canon")
        self.assertEqual(frame_count, 10)
        self.assertTrue(os.path.exists(self.output_path))
        cap = cv2.VideoCapture(self.output_path)
        self.assertTrue(cap.isOpened())
        cap.release()

    def test_output_matches_input_resolution_and_frame_count(self):
        process_video(self.input_path, self.output_path, "sony")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_WIDTH),
                          cap_out.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_HEIGHT),
                          cap_out.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_COUNT),
                          cap_out.get(cv2.CAP_PROP_FRAME_COUNT))
        cap_in.release()
        cap_out.release()

    def test_output_frames_differ_from_input(self):
        process_video(self.input_path, self.output_path, "nikon")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        ok_in, frame_in = cap_in.read()
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_in)
        self.assertTrue(ok_out)
        self.assertFalse(np.array_equal(frame_in, frame_out))
        cap_in.release()
        cap_out.release()

    def test_unsupported_brand_raises_before_writing_output(self):
        with self.assertRaises(ValueError):
            process_video(self.input_path, self.output_path, "fuji")

    def test_missing_input_file_raises_io_error(self):
        missing_path = os.path.join(self.tmpdir, "does_not_exist.mp4")
        with self.assertRaises(IOError):
            process_video(missing_path, self.output_path, "canon")

    def test_output_in_nonexistent_directory_raises_io_error(self):
        bad_output_path = os.path.join(self.tmpdir, "no_such_subdir", "output.mp4")
        with self.assertRaises(IOError):
            process_video(self.input_path, bad_output_path, "canon")


class TestVideoModeReducesFlickerVsPhotoMode(unittest.TestCase):
    def test_frame_to_frame_variation_lower_without_clahe(self):
        from brands.canon import apply_canon_look
        from core.engine import apply_population_fit_look_video_frame
        from tools.video_engine import brand_video_params

        rng = np.random.default_rng(7)
        width, height = 64, 48
        x = np.linspace(0, 255, width, dtype=np.uint8)
        gradient_row = np.tile(x, (height, 1))
        base = np.stack([gradient_row, gradient_row, gradient_row], axis=-1).astype(np.int16)
        frames = []
        for _ in range(10):
            noise = rng.integers(-15, 16, base.shape, dtype=np.int16)
            frames.append(np.clip(base + noise, 0, 255).astype(np.uint8))

        toe_lift, shoulder_start, white_point = brand_video_params("canon")

        def frame_to_frame_variation(processed_frames):
            means = [f[:, :, 0].astype(np.float64).mean() for f in processed_frames]
            diffs = [abs(means[i + 1] - means[i]) for i in range(len(means) - 1)]
            return float(np.mean(diffs))

        photo_outputs = [apply_canon_look(f) for f in frames]
        video_outputs = [
            apply_population_fit_look_video_frame(f, toe_lift, shoulder_start, white_point)
            for f in frames
        ]

        self.assertLess(frame_to_frame_variation(video_outputs),
                         frame_to_frame_variation(photo_outputs))


if __name__ == "__main__":
    unittest.main()
