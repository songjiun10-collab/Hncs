"""
brands/*.py의 모든 apply_* 룩 함수가 BGR np.ndarray를 받아 같은 shape/dtype의
BGR np.ndarray를 돌려주는지 확인하는 회귀 테스트. 2026-07 Canon/Sony/Nikon
추가 후 수동으로 한 번 스모크테스트했던 걸(README "브랜드 함수 QA 검증"
섹션 참고) 정식 테스트로 옮겨서 앞으로 회귀가 자동으로 잡히게 한다.

**2026-09 수동 allowlist -> 자동 발견으로 전환**: BRAND_LOOKS가 수동
목록이던 동안 fuji_provia_learned/leica_raw_learned/sigma_bf(_learned)/
sigma_fpl(_learned)/sony_a7rvi(_learned)/sony_a7v_learned 계열 apply_*
11개가 목록에 추가되지 않아 아무 테스트도 안 거치고 있었던 걸 발견(사용자
요청으로 감사, brands/CLAUDE.md가 apply_*를 "the shipped artifact"로
규정하므로 회귀 감시 사각지대였음). brands/CLAUDE.md의 "첫 인자가
이미지, 나머지는 전부 기본값" 균일 시그니처 규칙 덕에 fn(img) 한 호출로
모든 브랜드를 안전하게 스윕할 수 있다는 걸 이용해서, 목록을 손으로
관리하는 대신 brands/*.py를 순회해 공개 apply_* 콜러블을 자동으로 모으는
_discover_brand_looks()로 바꿨다 - 새 브랜드/변형 함수가 추가되면 이
목록을 깜빡 안 고쳐도 구조적으로 잡힌다. fuji.py는 자체 TestFujiPresets가
이미 동적 완전성 검사를 하므로 여기서 다시 훑지 않고 제외.
"""
import importlib
import pathlib
import unittest

import numpy as np

_BRANDS_DIR = pathlib.Path(__file__).resolve().parent.parent / "brands"

# fuji.py는 필름 시뮬레이션 프리셋이 여러 개고 아래 TestFujiPresets가
# 이미 자체 동적 완전성 검사(test_all_documented_presets_covered)를
# 갖고 있어 여기서 다시 훑지 않는다.
_EXCLUDED_MODULES = {"fuji"}

# 브랜드 모듈 네임스페이스에 들어와 있지만 "브랜드 룩"이 아니라 다른
# 모듈에서 그대로 가져다 쓰는 범용 헬퍼라 이름이 우연히 apply_*로
# 시작하는 것들. (모듈 stem, 함수명) -> 제외 사유.
_SKIP_NON_LOOK_HELPERS = {
    ("hasselblad_day", "apply_highlight_rolloff"):
        "core.curve.apply_highlight_rolloff를 그대로 import해서 내부적으로만 "
        "쓰는 범용 헬퍼 - 브랜드 룩이 아님(brands/fuji.py가 apply_highlight_"
        "rolloff/apply_lut을 제외하는 것과 같은 이유).",
}


def _discover_brand_looks():
    """brands/*.py(fuji.py 제외)를 순회해 공개 apply_* 콜러블을 모두
    모은다. 함수 def(`def apply_x(...)`)뿐 아니라 sigma_bf.py/sigma_fpl.py/
    sony_a7rvi.py처럼 팩토리 호출로 만든 `apply_x = make_population_fit_
    look(...)` 형태의 모듈 레벨 할당도 잡는다(vars(mod)로 모듈 네임스페이스를
    직접 훑으므로 정의 방식과 무관)."""
    found = []
    for path in sorted(_BRANDS_DIR.glob("*.py")):
        mod_stem = path.stem
        if mod_stem == "__init__" or mod_stem in _EXCLUDED_MODULES:
            continue
        mod_name = f"brands.{mod_stem}"
        mod = importlib.import_module(mod_name)
        for name in sorted(vars(mod)):
            if not name.startswith("apply_"):
                continue
            if (mod_stem, name) in _SKIP_NON_LOOK_HELPERS:
                continue
            obj = getattr(mod, name)
            if not callable(obj):
                continue
            found.append((mod_name, name))
    return found


# (모듈 경로, 함수명) - brands/*.py(fuji.py 제외)에서 자동 발견.
BRAND_LOOKS = _discover_brand_looks()

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

# apply_*_video_frame은 대응 프리셋의 CLAHE 생략 버전으로 tools/
# video_engine.py 전용 구현 디테일이지, 사용자에게 노출되는 별도 "필름
# 시뮬레이션 룩"이 아니다 - README가 세는 "10종"에는 포함되지 않는다(위
# FUJI_COLOR_PRESETS/FUJI_MONO_PRESETS와 별개로 다루는 이유). 그래도
# shape/dtype 회귀 커버리지 자체는 잃으면 안 된다.
#
# 원래는 이름을 손으로 나열했었는데(apply_pro_neg_hi_video_frame만),
# apply_classic_chrome_v2_video_frame/apply_nostalgic_neg_v3_video_frame이
# 나중에 추가되고 이 목록에 반영이 안 돼 테스트 없이 방치돼 있었던 걸
# 2026-09에 발견(BRAND_LOOKS를 자동 발견으로 바꾸며 같이 감사) - 이 목록도
# 이름이 "_video_frame"으로 끝나는 apply_*를 자동으로 모으도록 바꿔서
# 같은 종류의 누락이 다시 생기지 않게 한다.
def _discover_fuji_video_only_helpers(fuji_module):
    return sorted(n for n in dir(fuji_module)
                  if n.startswith("apply_") and n.endswith("_video_frame"))


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
        # apply_*_video_frame은 "프리셋"으로 세지 않지만(위
        # _discover_fuji_video_only_helpers 주석 참고) shape/dtype 회귀
        # 커버리지는 여전히 필요하므로 나머지 프리셋과 같은 스윕 패턴으로
        # 검사한다. 이름 목록은 자동 발견 - 손으로 나열하지 않는다.
        video_only_helpers = _discover_fuji_video_only_helpers(self.fuji)
        self.assertTrue(video_only_helpers,
                         "apply_*_video_frame 헬퍼가 하나도 안 잡힘 - discovery 로직 확인")
        for name in video_only_helpers:
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
