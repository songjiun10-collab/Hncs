import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from hybrid_engine.utils.io import decode_raw_darktable


class TestDecodeRawDarktable(unittest.TestCase):
    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_calls_darktable_cli_with_required_flags(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = np.zeros((4, 4, 3), dtype=np.float32)

        decode_raw_darktable("fake.RAF")

        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "darktable-cli")
        self.assertEqual(cmd[1], "fake.RAF")
        self.assertIn("--icc-type", cmd)
        self.assertIn("LIN_REC709", cmd)
        self.assertIn("plugins/imageio/format/tiff/bpp=32", cmd)
        self.assertIn("plugins/darkroom/workflow=none", cmd)

    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_on_nonzero_returncode(self, mock_run, mock_imread):
        mock_run.return_value = MagicMock(returncode=1, stderr="boom")

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")
        mock_imread.assert_not_called()

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=False)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_output_file_missing(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")
        mock_imread.assert_not_called()

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_imread_returns_none(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = None

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_negative_values_clipped_to_zero(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = np.array([[[-0.5, 0.2, 1.5]]], dtype=np.float32)

        result = decode_raw_darktable("fake.RAF")

        self.assertGreaterEqual(result.min(), 0.0)

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_bgr_converted_to_rgb(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # cv2 reads BGR order: blue=1.0, green=0.5, red=0.1
        mock_imread.return_value = np.array([[[1.0, 0.5, 0.1]]], dtype=np.float32)

        result = decode_raw_darktable("fake.RAF")

        # RGB order expected: red=0.1, green=0.5, blue=1.0
        np.testing.assert_allclose(result[0, 0], [0.1, 0.5, 1.0], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
