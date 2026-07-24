import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

from core.brand_classifier import load_signatures


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


if __name__ == "__main__":
    unittest.main()
