import inspect
import os
import shutil
import subprocess
import tempfile
import unittest

import cv2
import imageio_ffmpeg
import numpy as np

from tools.video_engine import (
    SUPPORTED_BRANDS, brand_video_params, mux_audio, process_video,
    process_video_with_audio,
)
from brands.fuji import apply_pro_neg_hi, apply_pro_neg_hi_video_frame
from brands.hasselblad import apply_hncs, apply_hncs_video_frame
from core.curve import film_curve, s_curve
from core.lut import ensure_uint8


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


def _make_synthetic_video_with_audio(path, duration=1, width=64, height=48, fps=24):
    """testsrc(그라디언트 패턴 비디오) + sine(440Hz 톤 오디오)을 ffmpeg
    lavfi 소스로 직접 만든 합성 비디오 - cv2.VideoWriter는 오디오를 못
    쓰므로 오디오 트랙이 필요한 테스트에서만 이 헬퍼를 쓴다."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg_exe, "-y",
         "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-c:v", "libx264", "-c:a", "aac", path],
        capture_output=True, text=True, check=True,
    )


def _make_synthetic_video_without_audio(path, duration=1, width=64, height=48, fps=24):
    """testsrc만 있는(오디오 트랙 없는) 합성 비디오."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg_exe, "-y",
         "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={duration}",
         "-c:v", "libx264", path],
        capture_output=True, text=True, check=True,
    )


def _has_audio_stream(path):
    """ffprobe가 이 환경에 없으므로 ffmpeg -i 출력(stderr)에 "Audio:"
    문자열이 있는지로 오디오 스트림 존재 여부를 판별한다(설계 단계
    검증과 동일한 방법)."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([ffmpeg_exe, "-i", path], capture_output=True, text=True)
    return "Audio:" in result.stderr


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
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
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
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FPS), cap_out.get(cv2.CAP_PROP_FPS))
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
            means = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float64).mean()
                     for f in processed_frames]
            diffs = [abs(means[i + 1] - means[i]) for i in range(len(means) - 1)]
            return float(np.mean(diffs))

        photo_outputs = [apply_canon_look(f) for f in frames]
        video_outputs = [
            apply_population_fit_look_video_frame(f, toe_lift, shoulder_start, white_point)
            for f in frames
        ]

        self.assertLess(frame_to_frame_variation(video_outputs),
                         frame_to_frame_variation(photo_outputs))


class TestBrandFunctionsArePurePassthroughs(unittest.TestCase):
    def test_every_brand_look_is_a_pure_population_fit_passthrough(self):
        from core.engine import apply_population_fit_look
        from tools.video_engine import _BRAND_FUNCTIONS, brand_video_params

        img = np.random.default_rng(3).integers(0, 255, (64, 64, 3), dtype=np.uint8)
        for name, fn in _BRAND_FUNCTIONS.items():
            with self.subTest(brand=name):
                clahe_clip = inspect.signature(fn).parameters["clahe_clip"].default
                np.testing.assert_array_equal(
                    fn(img),
                    apply_population_fit_look(img, *brand_video_params(name), clahe_clip))


class TestMuxAudio(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_mux_with_audio_source_produces_audio_output(self):
        video_only = os.path.join(self.tmpdir, "video_only.mp4")
        audio_source = os.path.join(self.tmpdir, "audio_source.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(video_only)
        _make_synthetic_video_with_audio(audio_source)

        mux_audio(video_only, audio_source, output)

        self.assertTrue(os.path.exists(output))
        self.assertTrue(_has_audio_stream(output))

    def test_mux_with_silent_source_produces_silent_output_no_error(self):
        video_only = os.path.join(self.tmpdir, "video_only.mp4")
        audio_source = os.path.join(self.tmpdir, "audio_source.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(video_only)
        _make_synthetic_video_without_audio(audio_source)

        mux_audio(video_only, audio_source, output)  # must not raise

        self.assertTrue(os.path.exists(output))
        self.assertFalse(_has_audio_stream(output))

    def test_mux_preserves_video_stream(self):
        video_only = os.path.join(self.tmpdir, "video_only.mp4")
        audio_source = os.path.join(self.tmpdir, "audio_source.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(video_only)
        _make_synthetic_video_with_audio(audio_source)

        mux_audio(video_only, audio_source, output)

        cap = cv2.VideoCapture(output)
        self.assertTrue(cap.isOpened())
        self.assertGreater(cap.get(cv2.CAP_PROP_FRAME_COUNT), 0)
        cap.release()

    def test_mux_failure_raises_io_error(self):
        video_only = os.path.join(self.tmpdir, "does_not_exist.mp4")
        audio_source = os.path.join(self.tmpdir, "also_does_not_exist.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        with self.assertRaises(IOError):
            mux_audio(video_only, audio_source, output)

    def test_mux_failure_removes_stub_output_file(self):
        """ffmpeg의 -y는 실패 전에 output을 먼저 truncate하므로, 실패한
        mux_audio() 호출이 final_output_path에 이미 존재하던 파일을 깨진
        stub으로 남겨두면 안 된다 - 성공 여부를 os.path.exists()로만
        확인하는 순진한 호출자를 속일 수 있기 때문."""
        video_only = os.path.join(self.tmpdir, "does_not_exist.mp4")
        audio_source = os.path.join(self.tmpdir, "also_does_not_exist.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        with open(output, "wb") as f:
            f.write(b"dummy pre-existing content")

        with self.assertRaises(IOError):
            mux_audio(video_only, audio_source, output)

        self.assertFalse(os.path.exists(output))


class TestProcessVideoWithAudio(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_input_with_audio_preserves_audio_in_output(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        frame_count = process_video_with_audio(input_path, output_path, "canon")

        self.assertGreater(frame_count, 0)
        self.assertTrue(_has_audio_stream(output_path))

    def test_input_without_audio_produces_silent_output_no_error(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(input_path, duration=1, fps=24)

        frame_count = process_video_with_audio(input_path, output_path, "canon")

        self.assertGreater(frame_count, 0)
        self.assertFalse(_has_audio_stream(output_path))

    def test_output_differs_from_raw_input(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        process_video_with_audio(input_path, output_path, "canon")

        cap_in = cv2.VideoCapture(input_path)
        cap_out = cv2.VideoCapture(output_path)
        ok_in, frame_in = cap_in.read()
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_in)
        self.assertTrue(ok_out)
        self.assertFalse(np.array_equal(frame_in, frame_out))
        cap_in.release()
        cap_out.release()

    def test_output_video_matches_direct_process_video_output(self):
        """mux_audio()는 -c:v copy(재인코딩 없음)를 쓰므로
        process_video_with_audio()의 비디오 스트림은 같은 입력/브랜드에
        대한 process_video() 단독 출력과 픽셀 단위로 동일해야 한다 - 이
        비교라야 색보정 자체가 no-op이 되는 회귀를 잡는다(raw 입력과
        비교하면 h264->mp4v 코덱 교체만으로도 항상 프레임이 달라지므로
        무의미하다)."""
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        direct_output_path = os.path.join(self.tmpdir, "direct_output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        process_video_with_audio(input_path, output_path, "canon")
        process_video(input_path, direct_output_path, "canon")

        cap_out = cv2.VideoCapture(output_path)
        cap_direct = cv2.VideoCapture(direct_output_path)
        ok_out, frame_out = cap_out.read()
        ok_direct, frame_direct = cap_direct.read()
        self.assertTrue(ok_out)
        self.assertTrue(ok_direct)
        np.testing.assert_array_equal(frame_out, frame_direct)
        cap_out.release()
        cap_direct.release()

    def test_no_leftover_temp_directories(self):
        scratch_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch_root, ignore_errors=True)
        original_tempdir = tempfile.tempdir
        tempfile.tempdir = scratch_root
        self.addCleanup(setattr, tempfile, "tempdir", original_tempdir)

        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        process_video_with_audio(input_path, output_path, "canon")
        self.assertEqual(os.listdir(scratch_root), [])

    def test_no_leftover_temp_directories_after_mux_failure(self):
        scratch_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch_root, ignore_errors=True)
        original_tempdir = tempfile.tempdir
        tempfile.tempdir = scratch_root
        self.addCleanup(setattr, tempfile, "tempdir", original_tempdir)

        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        # sabotage: point output_path at a directory that doesn't exist so mux_audio() fails
        bad_output_path = os.path.join(self.tmpdir, "no_such_subdir", "output.mp4")
        with self.assertRaises((IOError, OSError)):
            process_video_with_audio(input_path, bad_output_path, "canon")
        self.assertEqual(os.listdir(scratch_root), [])

    def test_non_mp4_output_extension_raises_value_error_before_processing(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.webm")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        with self.assertRaises(ValueError):
            process_video_with_audio(input_path, output_path, "canon")

        self.assertFalse(os.path.exists(output_path))

    def test_unsupported_brand_raises_value_error(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        with self.assertRaises(ValueError):
            process_video_with_audio(input_path, output_path, "fuji")

    def test_missing_input_raises_io_error(self):
        missing_path = os.path.join(self.tmpdir, "does_not_exist.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")

        with self.assertRaises(IOError):
            process_video_with_audio(missing_path, output_path, "canon")


class TestApplyProNegHiVideoFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_pro_neg_hi_video_frame(self.img)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_pro_neg_hi_video_frame(self.img)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_differs_from_photo_mode_with_clahe(self):
        photo_out = apply_pro_neg_hi(self.img)
        video_out = apply_pro_neg_hi_video_frame(self.img)
        self.assertFalse(np.array_equal(photo_out, video_out))

    def test_matches_manual_reconstruction_without_clahe(self):
        img = ensure_uint8(self.img)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        y = s_curve(x, n=1.7)
        lut = np.clip(y * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)
        img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.10, 0, 255)
        expected = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        out = apply_pro_neg_hi_video_frame(self.img)
        np.testing.assert_array_equal(out, expected)


class TestApplyHncsVideoFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_hncs_video_frame(self.img)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_hncs_video_frame(self.img)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_differs_from_photo_mode_with_clahe(self):
        photo_out = apply_hncs(self.img)
        video_out = apply_hncs_video_frame(self.img)
        self.assertFalse(np.array_equal(photo_out, video_out))

    def test_matches_manual_reconstruction_without_clahe(self):
        lab = cv2.cvtColor(self.img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** 0.7) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)
        x2 = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x2, 0.001, 0.78, 1.0) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)
        expected = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        out = apply_hncs_video_frame(self.img)
        np.testing.assert_array_equal(out, expected)


if __name__ == "__main__":
    unittest.main()
