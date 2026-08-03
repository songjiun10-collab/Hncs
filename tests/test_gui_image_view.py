import json
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from gui.widgets.image_view import prepare_for_display, quick_raw_preview


class TestPrepareForDisplay(unittest.TestCase):
    def test_bgr_8bit_passthrough_size(self):
        img = np.zeros((10, 20, 3), dtype=np.uint8)
        out = prepare_for_display(img, max_width=480)
        self.assertEqual(out.size, (20, 10))
        self.assertEqual(out.mode, "RGB")

    def test_grayscale_2d_converted_to_rgb(self):
        img = np.zeros((10, 20), dtype=np.uint8)
        out = prepare_for_display(img, max_width=480)
        self.assertEqual(out.mode, "RGB")

    def test_16bit_scaled_down_to_8bit(self):
        img = np.full((4, 4, 3), 65535, dtype=np.uint16)
        out = prepare_for_display(img, max_width=480)
        arr = np.array(out)
        self.assertEqual(arr.dtype, np.uint8)
        self.assertTrue((arr == 255).all())

    def test_downscale_when_wider_than_max(self):
        img = np.zeros((100, 1000, 3), dtype=np.uint8)
        out = prepare_for_display(img, max_width=480)
        self.assertEqual(out.size[0], 480)


class TestQuickRawPreview(unittest.TestCase):
    @patch("gui.widgets.image_view.rawpy.imread")
    def test_calls_postprocess_and_converts_rgb_to_bgr(self, mock_imread):
        rgb = np.zeros((4, 4, 3), dtype=np.uint8)
        rgb[:, :, 0] = 255  # R 채널만 채움
        mock_raw = MagicMock()
        mock_raw.postprocess.return_value = rgb
        mock_imread.return_value.__enter__.return_value = mock_raw

        out = quick_raw_preview("dummy.CR3")

        mock_raw.postprocess.assert_called_once_with(
            use_camera_wb=True, no_auto_bright=True, output_bps=8, half_size=True)
        self.assertEqual(out[0, 0, 2], 255)
        self.assertEqual(out[0, 0, 0], 0)


if __name__ == "__main__":
    unittest.main()
