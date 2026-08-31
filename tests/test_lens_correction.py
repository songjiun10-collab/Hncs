import unittest
from unittest.mock import patch

import numpy as np

from core.lens_correction import find_camera, find_lens, correct_from_exif
from tools.lens_correction import _parse_focal_length, _parse_aperture, resolve_lens_params


def _test_image(shape=(64, 96, 3), seed=0):
    return np.random.default_rng(seed).integers(0, 256, shape, dtype=np.uint8)


class TestFindCamera(unittest.TestCase):
    def test_known_camera_matches(self):
        cam = find_camera("FUJIFILM", "X-T1")
        self.assertIsNotNone(cam)
        self.assertEqual(cam.model, "X-T1")

    def test_unknown_camera_returns_none(self):
        self.assertIsNone(find_camera("NotARealMaker", "NotARealModel"))


class TestFindLens(unittest.TestCase):
    def test_known_lens_matches(self):
        cam = find_camera("FUJIFILM", "X-T1")
        lens = find_lens(cam, "XF10-24mmF4 R OIS")
        self.assertIsNotNone(lens)

    def test_unknown_lens_returns_none(self):
        cam = find_camera("FUJIFILM", "X-T1")
        self.assertIsNone(find_lens(cam, "NotARealLens 999mm"))


class TestCorrectFromExif(unittest.TestCase):
    def test_known_camera_and_lens_corrects_image(self):
        img = _test_image()
        corrected, info = correct_from_exif(
            img, "FUJIFILM", "X-T1", "XF10-24mmF4 R OIS",
            focal_length=10.0, aperture=8.0)
        self.assertTrue(info["ok"])
        self.assertIsNotNone(corrected)
        self.assertEqual(corrected.shape, img.shape)

    def test_unknown_camera_fails_with_reason(self):
        img = _test_image()
        corrected, info = correct_from_exif(
            img, "NotARealMaker", "NotARealModel", "whatever",
            focal_length=10.0, aperture=8.0)
        self.assertIsNone(corrected)
        self.assertFalse(info["ok"])
        self.assertEqual(info["reason"], "camera_not_found")

    def test_unknown_lens_fails_with_reason(self):
        img = _test_image()
        corrected, info = correct_from_exif(
            img, "FUJIFILM", "X-T1", "NotARealLens 999mm",
            focal_length=10.0, aperture=8.0)
        self.assertIsNone(corrected)
        self.assertFalse(info["ok"])
        self.assertEqual(info["reason"], "lens_not_found")


class TestParseHelpers(unittest.TestCase):
    def test_parse_focal_length_from_exiftool_string(self):
        self.assertEqual(_parse_focal_length("10.0 mm"), 10.0)

    def test_parse_focal_length_from_number(self):
        self.assertEqual(_parse_focal_length(24.0), 24.0)

    def test_parse_aperture_from_string(self):
        self.assertEqual(_parse_aperture("8.0"), 8.0)

    def test_parse_aperture_from_number(self):
        self.assertEqual(_parse_aperture(4), 4.0)


class TestResolveLensParams(unittest.TestCase):
    _EXIF = {
        "Make": "FUJIFILM",
        "Model": "X-T1",
        "LensModel": "XF10-24mmF4 R OIS",
        "FocalLength": "10.0 mm",
        "FNumber": 8.0,
    }

    @patch("tools.lens_correction._read_exif", return_value=_EXIF)
    def test_reads_complete_parameters_from_exif(self, _read_exif):
        params = resolve_lens_params("input.RAF")
        self.assertEqual(params, {
            "make": "FUJIFILM",
            "model": "X-T1",
            "lens_model": "XF10-24mmF4 R OIS",
            "focal_length": 10.0,
            "aperture": 8.0,
        })

    @patch("tools.lens_correction._read_exif", return_value={})
    def test_explicit_parameters_allow_missing_exif(self, _read_exif):
        params = resolve_lens_params(
            "input.RAF", make="FUJIFILM", model="X-T1",
            lens="XF10-24mmF4 R OIS", focal_length=10, aperture=8,
        )
        self.assertEqual(params["focal_length"], 10.0)
        self.assertEqual(params["aperture"], 8.0)

    @patch("tools.lens_correction._read_exif", return_value={"Make": "FUJIFILM"})
    def test_missing_metadata_raises_clear_error(self, _read_exif):
        with self.assertRaisesRegex(ValueError, "FocalLength"):
            resolve_lens_params("input.RAF")


if __name__ == "__main__":
    unittest.main()
