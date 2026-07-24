import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

from core.brand_classifier import load_signatures, extract_features


def _write_signature_json(path, n_images, per_image):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"methodology": "test", "n_images": n_images, "population": {}, "per_image": per_image}, f)


def _write_full_fake_brand(brand_dir, tone_records, color_records, gamut_records, texture_records, n_images=None):
    os.makedirs(brand_dir, exist_ok=True)
    n = n_images if n_images is not None else len(tone_records)
    _write_signature_json(os.path.join(brand_dir, "tone_signature.json"), n, tone_records)
    _write_signature_json(os.path.join(brand_dir, "color_signature.json"), n, color_records)
    _write_signature_json(os.path.join(brand_dir, "gamut_signature.json"), n, gamut_records)
    _write_signature_json(os.path.join(brand_dir, "texture_signature.json"), n, texture_records)


_TONE_A = {"filename": "a.jpg", "b2": 1.0, "w995": 2.0, "median": 3.0, "dark_pct": 0.1}
_TONE_B = {"filename": "b.jpg", "b2": 4.0, "w995": 5.0, "median": 6.0, "dark_pct": 0.2}
_COLOR_A = {"filename": "a.jpg", "sat_mean": 10.0, "hue_mean": 20.0}
_COLOR_B = {"filename": "b.jpg", "sat_mean": 30.0, "hue_mean": 40.0}
_GAMUT_A = {"filename": "a.jpg", "a_p1": 1.0, "a_p99": 2.0, "b_p1": 3.0, "b_p99": 4.0,
            "a_std": 1.0, "b_std": 1.0, "chroma_mean": 5.0, "chroma_p99": 6.0}
_GAMUT_B = {"filename": "b.jpg", "a_p1": 1.0, "a_p99": 2.0, "b_p1": 3.0, "b_p99": 4.0,
            "a_std": 1.0, "b_std": 1.0, "chroma_mean": 5.0, "chroma_p99": 6.0}
_TEXTURE_A = {"filename": "a.jpg", "sharpening": 1.0, "micro_contrast": 2.0, "noise": 0.01,
              "n_edges": 10, "overshoot": 1.0, "undershoot": 1.0}
_TEXTURE_B = {"filename": "b.jpg", "sharpening": 1.0, "micro_contrast": 2.0, "noise": 0.01,
              "n_edges": 10, "overshoot": 1.0, "undershoot": 1.0}


class TestLoadSignatures(unittest.TestCase):
    def test_joins_four_files_on_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand_dir = os.path.join(tmp, "fakebrand")
            _write_full_fake_brand(brand_dir, [_TONE_A, _TONE_B], [_COLOR_A, _COLOR_B],
                                    [_GAMUT_A, _GAMUT_B], [_TEXTURE_A, _TEXTURE_B])

            records = load_signatures("fakebrand", datasets_dir=tmp)

            self.assertEqual(len(records), 2)
            by_name = {r["filename"]: r for r in records}
            self.assertEqual(by_name["a.jpg"]["b2"], 1.0)
            self.assertEqual(by_name["a.jpg"]["sat_mean"], 10.0)
            self.assertEqual(by_name["a.jpg"]["a_p1"], 1.0)
            self.assertEqual(by_name["a.jpg"]["sharpening"], 1.0)

    def test_warns_on_filename_mismatch_and_uses_intersection(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand_dir = os.path.join(tmp, "fakebrand")
            # color_signature에는 b.jpg가 없음 - 교집합은 a.jpg 하나뿐
            _write_full_fake_brand(brand_dir, [_TONE_A, _TONE_B], [_COLOR_A],
                                    [_GAMUT_A, _GAMUT_B], [_TEXTURE_A, _TEXTURE_B], n_images=2)

            buf = io.StringIO()
            with redirect_stdout(buf):
                records = load_signatures("fakebrand", datasets_dir=tmp)

            self.assertEqual(len(records), 1)
            self.assertIn("불일치", buf.getvalue())


class TestExtractFeatures(unittest.TestCase):
    def _sample_record(self, **overrides):
        rec = {
            "filename": "a.jpg", "npix": 12345678, "is_portrait": True,
            "quality": 90, "subsampling": "4:2:0",
            "b2": 1.0, "w995": 2.0, "median": 3.0, "dark_pct": 0.1,
            "sat_mean": 50.0, "hue_mean": 30.0,
            "a_p1": 1.0, "a_p99": 2.0, "b_p1": 3.0, "b_p99": 4.0,
            "a_std": 1.0, "b_std": 1.0, "chroma_mean": 5.0, "chroma_p99": 6.0,
            "sharpening": 1.0, "micro_contrast": 2.0, "noise": 0.01,
            "n_edges": 10, "overshoot": 1.0, "undershoot": 1.0,
        }
        rec.update(overrides)
        return rec

    def test_set_a_shape_and_names(self):
        X, names = extract_features([self._sample_record()], feature_set="tone_color_gamut")
        self.assertEqual(X.shape, (1, 15))
        self.assertEqual(len(names), 15)

    def test_set_b_shape_and_names(self):
        X, names = extract_features([self._sample_record()], feature_set="all")
        self.assertEqual(X.shape, (1, 21))
        self.assertEqual(len(names), 21)

    def test_excluded_fields_never_appear(self):
        for feature_set in ["tone_color_gamut", "all"]:
            _, names = extract_features([self._sample_record()], feature_set=feature_set)
            for excluded in ["npix", "is_portrait", "quality", "subsampling", "filename", "hue_mean"]:
                self.assertNotIn(excluded, names)
            self.assertIn("hue_cos", names)
            self.assertIn("hue_sin", names)

    def test_unknown_feature_set_raises(self):
        with self.assertRaises(ValueError):
            extract_features([self._sample_record()], feature_set="bogus")

    def test_circular_hue_wraps_correctly(self):
        records = [
            self._sample_record(filename="a.jpg", hue_mean=359.0),
            self._sample_record(filename="b.jpg", hue_mean=1.0),
            self._sample_record(filename="c.jpg", hue_mean=180.0),
        ]
        X, names = extract_features(records, feature_set="tone_color_gamut")
        cos_i, sin_i = names.index("hue_cos"), names.index("hue_sin")
        dist_359_to_1 = np.linalg.norm(X[0][[cos_i, sin_i]] - X[1][[cos_i, sin_i]])
        dist_359_to_180 = np.linalg.norm(X[0][[cos_i, sin_i]] - X[2][[cos_i, sin_i]])
        self.assertLess(dist_359_to_1, dist_359_to_180)

    def test_empty_records_returns_correct_2d_shape(self):
        X, names = extract_features([], feature_set="tone_color_gamut")
        self.assertEqual(X.shape, (0, 15))
        self.assertEqual(len(names), 15)

        X, names = extract_features([], feature_set="all")
        self.assertEqual(X.shape, (0, 21))
        self.assertEqual(len(names), 21)


if __name__ == "__main__":
    unittest.main()
