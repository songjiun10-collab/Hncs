import unittest

import numpy as np

from hybrid_engine.core.preset_inverse import (
    BRAND_FUNCS, TARGET_FUNCS, curve_params, remove_camera_signature,
    convert_between_brands, detect_brand_from_exif,
)


def _test_image(seed=0, shape=(24, 24, 3)):
    rng = np.random.default_rng(seed)
    return rng.integers(20, 235, size=shape, dtype=np.uint8)


class TestCurveParams(unittest.TestCase):
    def test_all_brand_funcs_have_curve_params(self):
        for brand in BRAND_FUNCS:
            with self.subTest(brand=brand):
                params = curve_params(brand)
                self.assertIn("toe_lift", params)
                self.assertIn("shoulder_start", params)
                self.assertIn("white_point", params)

    def test_unknown_brand_raises(self):
        with self.assertRaises(ValueError):
            curve_params("not-a-brand")


class TestRemoveCameraSignature(unittest.TestCase):
    def test_preserves_shape_and_dtype(self):
        img = _test_image()
        out = remove_camera_signature(img, "canon")
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, img.dtype)

    def test_lut_inversion_is_accurate_without_clahe(self):
        # film_curve 자체의 역함수 정확도만 검증(CLAHE는 의도적으로 역산
        # 안 하므로 이 테스트 범위 밖 - 모듈 docstring 참고)
        from core.curve import film_curve
        from hybrid_engine.core.preset_inverse import _inverse_lut

        params = curve_params("sony")
        x = np.linspace(0.0, 1.0, 2000)
        y = film_curve(x, **params)
        y_dom, x_range = _inverse_lut(**params)
        recovered = np.interp(y, y_dom, x_range)
        self.assertLess(float(np.max(np.abs(x - recovered))), 1e-3)


class TestConvertBetweenBrands(unittest.TestCase):
    def test_preserves_shape_and_dtype(self):
        img = _test_image()
        out = convert_between_brands(img, "canon", "hasselblad")
        self.assertEqual(out.shape, img.shape)
        self.assertEqual(out.dtype, img.dtype)

    def test_unknown_target_brand_raises(self):
        img = _test_image()
        with self.assertRaises(ValueError):
            convert_between_brands(img, "canon", "not-a-brand")

    def test_same_source_and_target_runs(self):
        img = _test_image()
        out = convert_between_brands(img, "nikon", "nikon")
        self.assertEqual(out.shape, img.shape)

    def test_fuji_targets_are_target_only(self):
        # 후지 프리셋은 타깃으로는 되고 역산 소스로는 안 됨
        img = _test_image()
        out = convert_between_brands(img, "nikon", "fuji_astia")
        self.assertEqual(out.shape, img.shape)
        self.assertNotIn("fuji_astia", BRAND_FUNCS)
        with self.assertRaises(ValueError):
            curve_params("fuji_astia")

    def test_all_fuji_targets_preserve_bgr_contract(self):
        img = _test_image()
        for name, func in TARGET_FUNCS.items():
            if not name.startswith("fuji_"):
                continue
            with self.subTest(target=name):
                out = convert_between_brands(img, "canon", name)
                self.assertEqual(out.shape, img.shape)
                self.assertEqual(out.dtype, img.dtype)


class TestDetectBrandFromExif(unittest.TestCase):
    def test_known_makes(self):
        cases = [
            ("Canon", "EOS R5", "canon"),
            ("NIKON CORPORATION", "NIKON Z6", "nikon"),
            ("SONY", "ILCE-7M4", "sony"),
            ("Panasonic", "DC-S5", "panasonic"),
            ("OLYMPUS IMAGING CORP.", "E-M1MarkIII", "olympus"),
            ("LEICA CAMERA AG", "M9", "leica"),
            ("Phase One A/S", "IQ4 150MP", "phaseone"),
            ("SIGMA", "fp L", "sigma"),
            ("Hasselblad", "X2D 100C", "hasselblad"),
        ]
        for make, model, expected in cases:
            with self.subTest(make=make, model=model):
                self.assertEqual(detect_brand_from_exif(make, model), expected)

    def test_ricoh_imaging_disambiguates_by_model(self):
        self.assertEqual(
            detect_brand_from_exif("RICOH IMAGING COMPANY, LTD.", "PENTAX K-1"),
            "pentax")
        self.assertEqual(
            detect_brand_from_exif("RICOH IMAGING COMPANY, LTD.", "RICOH GR III"),
            "ricoh_gr")

    def test_unknown_make_returns_none(self):
        self.assertIsNone(detect_brand_from_exif("FUJIFILM", "X-T5"))
        self.assertIsNone(detect_brand_from_exif(None, None))


if __name__ == "__main__":
    unittest.main()
