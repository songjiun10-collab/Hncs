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
    ("brands.hasselblad", "apply_hncs_video_frame"),
    ("brands.hasselblad_learned", "apply_hncs_learned"),
    ("brands.hasselblad_day", "apply_hasselblad_day"),
    ("brands.hasselblad_night", "apply_hasselblad_night"),
    ("brands.hasselblad_x1d50c", "apply_hncs_x1d50c"),
    ("brands.hasselblad_x2dii", "apply_hncs_x2dii"),
    ("brands.leica", "apply_leica_look"),
    ("brands.leica_raw", "apply_leica_raw_look"),
    ("brands.phaseone", "apply_phaseone_look"),
    ("brands.pentax", "apply_pentax_look"),
    ("brands.ricoh_gr", "apply_ricoh_gr_look"),
    ("brands.canon", "apply_canon_look"),
    ("brands.canon", "apply_canon_raw_look"),
    ("brands.sony", "apply_sony_look"),
    ("brands.sony_raw", "apply_sony_raw_look"),
    ("brands.sony_a7v", "apply_sony_a7v_look"),
    ("brands.nikon", "apply_nikon_look"),
    ("brands.panasonic", "apply_panasonic_look"),
    ("brands.olympus", "apply_olympus_look"),
    ("brands.sigma", "apply_sigma_look"),
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
    "apply_provia",
    "apply_classic_chrome",
    "apply_nostalgic_neg_v2",
    "apply_classic_chrome_v2",
    "apply_nostalgic_neg_v3",
]
# 원래 여기 assertion을 9로 잘못 짰다가(README 오기를 그대로 베낌) 실제
# 개수(10 - 당시 8개 컬러 + acros/monochrome 2개)와 다른 걸 이 테스트로
# 발견, README도 같이 고침(brands/fuji.py 자체 코드는 원래도 정확했음).
# apply_provia 추가(2026-08)로 11개(컬러 9 + 모노 2) -> apply_classic_chrome/
# apply_nostalgic_neg_v2 추가로 13개(컬러 11 + 모노 2) -> 페어 매칭 버그
# 수정 후 apply_classic_chrome_v2/apply_nostalgic_neg_v3 추가로 현재는
# 15개(컬러 13 + 모노 2).
FUJI_MONO_PRESETS = ["apply_acros", "apply_monochrome"]

# apply_pro_neg_hi_video_frame은 apply_pro_neg_hi의 CLAHE 생략 버전으로
# tools/video_engine.py 전용 구현 디테일이지, 사용자에게 노출되는 별도
# "필름 시뮬레이션 룩"이 아니다 - README가 세는 "10종"에는 포함되지
# 않는다(위 FUJI_COLOR_PRESETS/FUJI_MONO_PRESETS와 별개 리스트로 뺀 이유).
# 그래도 shape/dtype 회귀 커버리지 자체는 잃으면 안 되므로 이 리스트로
# 따로 스윕한다.
FUJI_VIDEO_ONLY_HELPERS = ["apply_pro_neg_hi_video_frame"]


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

    def test_video_only_helpers_preserve_shape_and_dtype(self):
        # apply_pro_neg_hi_video_frame은 "프리셋"으로 세지 않지만(위
        # FUJI_VIDEO_ONLY_HELPERS 주석 참고) shape/dtype 회귀 커버리지는
        # 여전히 필요하므로 나머지 프리셋과 같은 스윕 패턴으로 검사한다.
        for name in FUJI_VIDEO_ONLY_HELPERS:
            with self.subTest(preset=name):
                fn = getattr(self.fuji, name)
                out = fn(self.img)
                self.assertEqual(out.shape, self.img.shape)
                self.assertEqual(out.dtype, self.img.dtype)

    def test_all_documented_presets_covered(self):
        # brand.fuji의 apply_* 중 core.curve/core.lut에서 재노출된 범용
        # 헬퍼(apply_lut/apply_highlight_rolloff)와 tools/video_engine.py
        # 전용 CLAHE-생략 변형(이름이 "_video_frame"으로 끝남 - 별도
        # "룩"이 아니라 구현 디테일)을 뺀 진짜 프리셋 개수가 FUJI_COLOR_
        # PRESETS/FUJI_MONO_PRESETS 목록과 일치하는지 확인 - 프리셋을
        # 추가/삭제했는데 이 목록을 깜빡하고 안 고치는 걸 방지.
        generic_helpers = {"apply_lut", "apply_highlight_rolloff"}
        preset_names = {n for n in dir(self.fuji)
                         if n.startswith("apply_") and n not in generic_helpers
                         and not n.endswith("_video_frame")}
        self.assertEqual(preset_names, set(FUJI_COLOR_PRESETS) | set(FUJI_MONO_PRESETS))
        self.assertEqual(len(preset_names), 15)


if __name__ == "__main__":
    unittest.main()
