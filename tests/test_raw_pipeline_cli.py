import unittest
from unittest.mock import patch

import numpy as np

from tools.raw_pipeline import lens_correct_linear_image


class TestLensCorrectLinearImage(unittest.TestCase):
    _PARAMS = {
        "make": "FUJIFILM",
        "model": "X-T1",
        "lens_model": "XF10-24mmF4 R OIS",
        "focal_length": 10.0,
        "aperture": 8.0,
    }

    def test_resolves_exif_and_passes_linear_image_to_lensfun_layer(self):
        linear = np.full((4, 5, 3), 0.18, dtype=np.float32)
        corrected = linear + 0.01
        info = {"ok": True, "camera": "X-T1", "lens": "XF10-24mmF4 R OIS"}
        with patch("tools.raw_pipeline.resolve_lens_params", return_value=self._PARAMS) as resolve:
            with patch("tools.raw_pipeline.correct_from_exif", return_value=(corrected, info)) as correct:
                result, result_info = lens_correct_linear_image(
                    "input.RAF", linear, distance=12.5,
                )

        self.assertIs(result, corrected)
        self.assertIs(result_info, info)
        resolve.assert_called_once_with(
            "input.RAF", make=None, model=None, lens=None,
            focal_length=None, aperture=None,
        )
        correct.assert_called_once_with(linear, distance=12.5, **self._PARAMS)

    def test_lensfun_match_failure_is_not_silently_ignored(self):
        linear = np.zeros((2, 2, 3), dtype=np.float32)
        info = {"ok": False, "reason": "lens_not_found", "lens_model": "Unknown"}
        with patch("tools.raw_pipeline.resolve_lens_params", return_value=self._PARAMS):
            with patch("tools.raw_pipeline.correct_from_exif", return_value=(None, info)):
                with self.assertRaisesRegex(RuntimeError, "lens_not_found"):
                    lens_correct_linear_image("input.RAF", linear)

    def test_metadata_failure_propagates_to_cli_layer(self):
        linear = np.zeros((2, 2, 3), dtype=np.float32)
        with patch("tools.raw_pipeline.resolve_lens_params",
                   side_effect=ValueError("EXIF metadata missing")):
            with self.assertRaisesRegex(ValueError, "metadata missing"):
                lens_correct_linear_image("input.RAF", linear)


if __name__ == "__main__":
    unittest.main()
