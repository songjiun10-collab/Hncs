import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

from hybrid_engine.evaluation import metrics
from hybrid_engine.utils import io as io_utils
from tools.cli import analyze as analyze_cli
from tools.cli import denoise as denoise_cli
from tools.cli import lens_correction as lens_cli
from tools.cli import raw_pipeline as raw_pipeline_cli
from tools.cli import upscale as upscale_cli


class TestCliFailureContracts(unittest.TestCase):
    def test_denoise_missing_input_exits_nonzero(self):
        argv = ["denoise", "missing.jpg", "out.jpg"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(denoise_cli.cv2, "imread", return_value=None), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                denoise_cli.main()
        self.assertEqual(raised.exception.code, 1)

    def test_denoise_imwrite_failure_exits_nonzero(self):
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        argv = ["denoise", "in.jpg", "missing/out.jpg"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(denoise_cli.cv2, "imread", return_value=image), \
                mock.patch.object(denoise_cli, "denoise", return_value=image), \
                mock.patch.object(denoise_cli.cv2, "imwrite", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                denoise_cli.main()
        self.assertEqual(raised.exception.code, 1)

    def test_upscale_imwrite_failure_exits_nonzero(self):
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        argv = ["upscale", "in.jpg", "missing/out.jpg"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(upscale_cli.cv2, "imread", return_value=image), \
                mock.patch.object(upscale_cli, "upscale", return_value=image), \
                mock.patch.object(upscale_cli.cv2, "imwrite", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                upscale_cli.main()
        self.assertEqual(raised.exception.code, 1)

    def test_lens_correction_imwrite_failure_exits_nonzero(self):
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        params = {
            "make": "Test",
            "model": "Camera",
            "lens_model": "Lens",
            "focal_length": 35.0,
            "aperture": 4.0,
        }
        info = {"ok": True, "camera": "Test Camera", "lens": "Lens"}
        argv = ["lens_correction", "in.jpg", "missing/out.jpg"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(lens_cli, "resolve_lens_params", return_value=params), \
                mock.patch.object(lens_cli, "_load_image", return_value=image), \
                mock.patch.object(lens_cli, "correct_from_exif", return_value=(image, info)), \
                mock.patch.object(lens_cli.cv2, "imwrite", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                lens_cli.main()
        self.assertEqual(raised.exception.code, 1)

    def test_raw_pipeline_tiff_imwrite_failure_exits_nonzero(self):
        linear = np.zeros((8, 8, 3), dtype=np.float64)
        bgr16 = np.zeros((8, 8, 3), dtype=np.uint16)
        argv = ["raw_pipeline", "in.dng", "missing/out.tiff", "--log-space", "S-Log3"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(raw_pipeline_cli, "raw_to_prophoto_linear", return_value=linear), \
                mock.patch.object(raw_pipeline_cli, "apply_exposure", side_effect=lambda image, ev: image), \
                mock.patch.object(raw_pipeline_cli, "to_log_space", return_value=linear), \
                mock.patch.object(raw_pipeline_cli, "to_16bit_bgr", return_value=bgr16), \
                mock.patch.object(raw_pipeline_cli.cv2, "imwrite", return_value=False), \
                contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                raw_pipeline_cli.main()
        self.assertEqual(raised.exception.code, 1)

    def test_analyze_download_reports_jpeg_write_failure(self):
        image = np.zeros((8, 8, 3), dtype=np.uint8)
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"fake-jpeg-bytes"
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "out.jpg")
            with mock.patch.object(analyze_cli.urllib.request, "urlopen", return_value=response), \
                    mock.patch.object(analyze_cli, "_check_genuine_bytes", return_value=True), \
                    mock.patch.object(analyze_cli.cv2, "imdecode", return_value=image), \
                    mock.patch.object(analyze_cli.cv2, "imwrite", return_value=False), \
                    contextlib.redirect_stdout(io.StringIO()):
                ok, reason = analyze_cli._hasselblad_download(
                    "https://example.invalid/sample.jpg", output
                )
        self.assertFalse(ok)
        self.assertEqual(reason, "write")


class TestLibraryWriteContracts(unittest.TestCase):
    def test_save_tiff16_raises_when_encoder_does_not_write(self):
        image = np.zeros((4, 4, 3), dtype=np.float64)
        with mock.patch.object(io_utils.cv2, "imwrite", return_value=False):
            with self.assertRaises(OSError):
                io_utils.save_tiff16(image, "missing/out.tiff")

    def test_save_jpeg8_raises_when_encoder_does_not_write(self):
        image = np.zeros((4, 4, 3), dtype=np.float64)
        with mock.patch.object(io_utils.cv2, "imwrite", return_value=False):
            with self.assertRaises(OSError):
                io_utils.save_jpeg8(image, "missing/out.jpg")


class TestMetricInputContracts(unittest.TestCase):
    def test_delta_e_by_zone_rejects_same_pixel_count_different_shape(self):
        a = np.zeros((1, 2, 3), dtype=np.float64)
        b = np.zeros((2, 1, 3), dtype=np.float64)
        with self.assertRaises(ValueError):
            metrics.delta_e_by_zone(a, b)

    def test_delta_e_stats_rejects_nonfinite_input(self):
        a = np.zeros((2, 2, 3), dtype=np.float64)
        b = a.copy()
        b[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            metrics.delta_e_stats(a, b)

    def test_delta_e_by_zone_rejects_empty_images(self):
        empty = np.empty((0, 2, 3), dtype=np.float64)
        with self.assertRaises(ValueError):
            metrics.delta_e_by_zone(empty, empty)


if __name__ == "__main__":
    unittest.main()
