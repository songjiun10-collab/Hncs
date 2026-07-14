"""
brands/*.py의 모든 apply_* 룩 함수가 BGR np.ndarray를 받아 같은 shape/dtype의
BGR np.ndarray를 돌려주는지 확인하는 회귀 테스트. 2026-07 Canon/Sony/Nikon
추가 후 수동으로 한 번 스모크테스트했던 걸(README "브랜드 함수 QA 검증"
섹션 참고) 정식 테스트로 옮겨서 앞으로 회귀가 자동으로 잡히게 한다.
"""
import importlib
import unittest

import numpy as np

# (모듈 경로, 함수명) - 브랜드 하나당 대표 apply_* 하나씩
BRAND_LOOKS = [
    ("brands.hasselblad", "apply_hncs"),
    ("brands.hasselblad_learned", "apply_hncs_learned"),
    ("brands.hasselblad_day", "apply_hasselblad_day"),
    ("brands.hasselblad_night", "apply_hasselblad_night"),
    ("brands.leica", "apply_leica_look"),
    ("brands.phaseone", "apply_phaseone_look"),
    ("brands.pentax", "apply_pentax_look"),
    ("brands.ricoh_gr", "apply_ricoh_gr_look"),
    ("brands.canon", "apply_canon_look"),
    ("brands.sony", "apply_sony_look"),
    ("brands.nikon", "apply_nikon_look"),
    ("brands.panasonic", "apply_panasonic_look"),
]

# fuji.py는 필름 시뮬레이션 프리셋이 여러 개라 따로 나열. apply_acros/
# apply_monochrome은 설계상 1채널 그레이스케일을 반환하므로 별도 처리.
FUJI_COLOR_PRESETS = [
    "apply_astia",
    "apply_pro_neg_std",
    "apply_pro_neg_hi",
    "apply_eterna_cinema",
    "apply_eterna_bleach_bypass",
    "apply_nostalgic_neg",
    "apply_reala_ace",
    "apply_classic_negative",
]
# 원래 여기 assertion을 9로 잘못 짰다가(README 오기를 그대로 베낌) 실제
# 개수(10 - 위 8개 컬러 + acros/monochrome 2개)와 다른 걸 이 테스트로 발견,
# README도 같이 고침(brands/fuji.py 자체 코드는 원래도 정확했음).
FUJI_MONO_PRESETS = ["apply_acros", "apply_monochrome"]


def make_test_image():
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)


class TestBrandLooksPreserveShapeAndDtype(unittest.TestCase):
    def test_all_brand_looks(self):
        img = make_test_image()
        for mod_name, fn_name in BRAND_LOOKS:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                self.assertIsNotNone(out, f"{mod_name}.{fn_name} returned None")
                self.assertEqual(out.shape, img.shape,
                                  f"{mod_name}.{fn_name} changed shape")
                self.assertEqual(out.dtype, img.dtype,
                                  f"{mod_name}.{fn_name} changed dtype")


class TestFujiPresets(unittest.TestCase):
    def setUp(self):
        self.img = make_test_image()
        import brands.fuji as fuji
        self.fuji = fuji

    def test_color_presets_preserve_shape_and_dtype(self):
        for name in FUJI_COLOR_PRESETS:
            with self.subTest(preset=name):
                fn = getattr(self.fuji, name)
                out = fn(self.img)
                self.assertEqual(out.shape, self.img.shape)
                self.assertEqual(out.dtype, self.img.dtype)

    def test_mono_presets_return_single_channel(self):
        for name in FUJI_MONO_PRESETS:
            with self.subTest(preset=name):
                fn = getattr(self.fuji, name)
                out = fn(self.img)
                self.assertEqual(out.shape, self.img.shape[:2])
                self.assertEqual(out.dtype, self.img.dtype)

    def test_all_documented_presets_covered(self):
        # brand.fuji의 apply_* 중 core.curve/core.lut에서 재노출된 범용
        # 헬퍼(apply_lut/apply_highlight_rolloff)를 뺀 진짜 프리셋 개수가
        # README에 적힌 "9종"과 일치하는지 확인 - 프리셋을 추가/삭제했는데
        # 이 테스트나 README를 깜빡하고 안 고치는 걸 방지.
        generic_helpers = {"apply_lut", "apply_highlight_rolloff"}
        preset_names = {n for n in dir(self.fuji)
                         if n.startswith("apply_") and n not in generic_helpers}
        self.assertEqual(preset_names, set(FUJI_COLOR_PRESETS) | set(FUJI_MONO_PRESETS))
        self.assertEqual(len(preset_names), 10)


if __name__ == "__main__":
    unittest.main()
