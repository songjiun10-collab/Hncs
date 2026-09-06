import csv
import os
import tempfile
import unittest
from unittest import mock

import cv2
import numpy as np

from tools import evaluation_common


class TestCollectContributedPairs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name
        self.contributed = os.path.join(self.base, "datasets", "demo", "contributed")
        os.makedirs(self.contributed)

    def _write_manifest(self, set_name, rows):
        root = os.path.join(self.contributed, set_name)
        os.makedirs(os.path.join(root, "raw"))
        os.makedirs(os.path.join(root, "jpeg"))
        with open(os.path.join(root, "manifest.csv"), "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("filename_raw", "filename_jpeg", "camera"))
            writer.writeheader()
            writer.writerows(rows)
        for row in rows:
            open(os.path.join(root, "raw", row["filename_raw"]), "wb").close()
            open(os.path.join(root, "jpeg", row["filename_jpeg"]), "wb").close()

    def test_collects_sorted_first_wins_and_filters(self):
        self._write_manifest(
            "z-set",
            [
                {"filename_raw": "duplicate.raw", "filename_jpeg": "z.jpg", "camera": "Other"},
                {"filename_raw": "other.raw", "filename_jpeg": "other.jpg", "camera": "Other"},
            ],
        )
        self._write_manifest(
            "a-set",
            [
                {"filename_raw": "duplicate.raw", "filename_jpeg": "a.jpg", "camera": "Target"},
                {"filename_raw": "target.raw", "filename_jpeg": "target.jpg", "camera": "Target"},
            ],
        )

        with mock.patch.object(evaluation_common, "BASE", self.base):
            pairs = evaluation_common.collect_contributed_pairs("demo")
            target_pairs = evaluation_common.collect_contributed_pairs("demo", model_filter="Target")

        self.assertEqual([pair["name"] for pair in pairs], ["duplicate.raw", "target.raw", "other.raw"])
        self.assertEqual(pairs[0]["jpeg_path"], os.path.join(self.contributed, "a-set", "jpeg", "a.jpg"))
        self.assertEqual([pair["name"] for pair in target_pairs], ["duplicate.raw", "target.raw"])

    def test_forwards_exif_film_mode_filter(self):
        self._write_manifest(
            "set",
            [
                {"filename_raw": "pro.raw", "filename_jpeg": "pro.jpg", "camera": "Target"},
                {"filename_raw": "vel.raw", "filename_jpeg": "vel.jpg", "camera": "Target"},
            ],
        )
        expected = {
            os.path.join(self.contributed, "set", "jpeg", "pro.jpg"): "Provia",
            os.path.join(self.contributed, "set", "jpeg", "vel.jpg"): "Velvia",
        }

        with mock.patch.object(evaluation_common, "BASE", self.base), mock.patch.object(
            evaluation_common, "_exif_film_mode", side_effect=lambda path: expected[path]
        ) as exif:
            pairs = evaluation_common.collect_contributed_pairs("demo", film_mode_filter="Provia")

        self.assertEqual([pair["name"] for pair in pairs], ["pro.raw"])
        self.assertEqual(exif.call_count, 2)


class TestColorHelpers(unittest.TestCase):
    def test_converts_shape_and_dtype(self):
        with tempfile.TemporaryDirectory() as tmp:
            jpg_path = os.path.join(tmp, "target.jpg")
            bgr = np.array(
                [
                    [[0, 64, 255], [255, 128, 32]],
                    [[32, 16, 8], [200, 100, 50]],
                ],
                dtype=np.uint8,
            )
            self.assertTrue(cv2.imwrite(jpg_path, bgr))

            target = evaluation_common.load_target_linear(jpg_path, (3, 2))
            converted = evaluation_common.bgr_u8_to_linear(bgr)

        self.assertEqual(target.shape, (3, 2, 3))
        self.assertEqual(converted.shape, bgr.shape)
        self.assertEqual(target.dtype, np.float64)
        self.assertEqual(converted.dtype, np.float64)

    def test_mean_delta_e_is_zero_for_identical_arrays(self):
        linear = np.array([[[0.0, 0.25, 1.0], [0.5, 0.75, 0.1]]], dtype=np.float64)
        self.assertEqual(evaluation_common.mean_delta_e(linear, linear), 0.0)


if __name__ == "__main__":
    unittest.main()
