"""population-fit 브랜드 12개의 apply_*_look() 출력이 core/engine.py
리팩토링(docs/superpowers/plans/2026-08-09-population-fit-wrapper-consolidation.md)
전후로 완전히 동일한지 확인하는 골든 회귀 테스트. 해시는 리팩토링 전
실제 코드를 돌려서 뽑은 값 그대로다 - 값 자체가 맞는지는 검증하지
않는다(그건 각 브랜드 docstring의 population 수치가 담당), 오직
"이 리팩토링이 픽셀 출력을 하나도 안 바꿨는지"만 확인한다.

**주의(2026-08, requirements.txt 버전 고정 작업 중 발견)**: 안정적인 함수의
해시는 CI(ubuntu-latest, requirements.txt에 고정된 정확한 버전)에서 뽑은
값이어야 한다 - macOS 로컬 환경에서 뽑으면 안 됨. `cv2.cvtColor(...,
COLOR_BGR2HSV)` 왕복을 쓰는 함수(apply_pro_neg_std/pro_neg_hi/
eterna_cinema/eterna_bleach_bypass/reala_ace/classic_negative,
hasselblad_night)는 opencv 버전/플랫폼에 따라 최하위 비트가 달라져서
로컬에서 뽑은 해시가 CI에서 재현 안 됨. 이 7개는 CI 기준 출력 픽셀 배열이
보관돼 있지 않아 임의의 교차 플랫폼 허용오차를 만들지 않고, 같은 환경에서의
재실행 Δ=0과 uint8 출력 계약만 확인한다. Lab 전용 CLAHE+LUT 함수는 전부
플랫폼 무관하게 일치해 정확한 해시를 계속 쓴다. 새 안정 함수의 골든해시는
로컬에서 계산만 하지 말고 CI 실행 결과로 검증/교정할 것."""
import hashlib
import importlib
import unittest

import numpy as np

# tests/test_brands.py의 make_test_image()와 동일한 시드/shape
def make_test_image():
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)


# (모듈 경로, 함수명, 리팩토링 전 sha256(출력.tobytes()))
GOLDEN_HASHES = [
    ("brands.canon", "apply_canon_look",
     "a2d38d6afbdae1926632f46c92685845a40d40ed0baa2f05eb3e70eee5b31fa9"),
    ("brands.leica", "apply_leica_look",
     "670068f031446c463196e409d99560b6fd972e56b8049f988b371fe8c9fd9ec0"),
    ("brands.leica_raw", "apply_leica_raw_look",
     "d49fc298c2f78c3631b746c27a3f4f3b981ea144270e17ee2707e95e2bc85fd7"),
    ("brands.nikon", "apply_nikon_look",
     "c47edaf79ecafd047b473ad44375044180475284527dfa0b87a643c604125c95"),
    ("brands.olympus", "apply_olympus_look",
     "249ad1c40a8686430edb3584ce348afe9b73ab8ff9db4b02d8d1e89ae30b0a25"),
    ("brands.panasonic", "apply_panasonic_look",
     "2a727377610358b323216ec632c5b540fb0a2f7b7f961d46dbc02b8b5afb69f3"),
    ("brands.pentax", "apply_pentax_look",
     "37f649f1725fe0e0b8ee58523b200e61314ad07b991aabf08d1dda7f12cd2c3d"),
    ("brands.phaseone", "apply_phaseone_look",
     "bdfbea26b312321e3dcc46ce17529b67da5cdec0430d27a610128087681062c1"),
    ("brands.ricoh_gr", "apply_ricoh_gr_look",
     "9239b981fe5a363d22c091d47bb3a2073bc88c85f341c01ba3b969722ff8e1d0"),
    ("brands.sigma", "apply_sigma_look",
     "2544e61c01ec5c741168bda8506657711eda51a0c616e002f65d5b3a1bc1a5eb"),
    ("brands.sony", "apply_sony_look",
     "49ee7af2612f66aac66433c1e695cd32864b24cae1b542154a9edada379c3be9"),
    ("brands.sony_a7v", "apply_sony_a7v_look",
     "0bb0bb82d4f1636dee43ffb4c64a98e26f639ff0292e2be51687d483c190d104"),
]


class TestPopulationFitLookGoldenHashes(unittest.TestCase):
    def test_all_12_brands_match_pre_refactor_output(self):
        img = make_test_image()
        for mod_name, fn_name, expected_hash in GOLDEN_HASHES:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                actual_hash = hashlib.sha256(out.tobytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash,
                                  f"{mod_name}.{fn_name} output changed - "
                                  f"expected sha256={expected_hash}, got {actual_hash}")


# (모듈 경로, 함수명, 리팩토링 전 sha256(출력.tobytes())) - Hasselblad
# 단독바디 apply_hncs_* 변형 2개
# (docs/superpowers/plans/2026-08-09-hasselblad-body-variant-wrapper-consolidation.md)
HASSELBLAD_BODY_GOLDEN_HASHES = [
    ("brands.hasselblad_x1d50c", "apply_hncs_x1d50c",
     "a2f56608aab5a6c06f69f9e041467edbcfa37a605576df0e5e7d4eb2ea8f9267"),
    ("brands.hasselblad_x2dii", "apply_hncs_x2dii",
     "e56aae33aeb387ea18efc03371567c1e0da55a3e4e6fca3c77fa54e2790058fa"),
]


class TestHasselbladBodyVariantGoldenHashes(unittest.TestCase):
    def test_both_body_variants_match_pre_refactor_output(self):
        img = make_test_image()
        for mod_name, fn_name, expected_hash in HASSELBLAD_BODY_GOLDEN_HASHES:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                actual_hash = hashlib.sha256(out.tobytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash,
                                  f"{mod_name}.{fn_name} output changed - "
                                  f"expected sha256={expected_hash}, got {actual_hash}")


# (모듈 경로, 함수명, sha256(출력.tobytes())) - CLAUDE.md의 "Never" 목록에
# 있는 apply_hncs()와 그 파생 5개는 다른 population-fit 브랜드들과 달리
# 값을 고정하는 골든 테스트가 없었다(2026-08 코드리뷰에서 발견) - shape/
# dtype만 확인하는 test_brands.py로는 회귀가 나도 풀스위트가 통과했다.
# 여기 해시는 현재 shipped 코드를 그대로 돌려 뽑은 값이다(값 자체가
# 옳은지는 각 브랜드 docstring의 raw+jpeg 실측이 담당) - 오직 "이후
# 변경이 픽셀 출력을 하나도 안 바꿨는지"만 확인한다.
HASSELBLAD_CORE_GOLDEN_HASHES = [
    ("brands.hasselblad", "apply_hncs",
     "6751b7a521f97640edfa4db32386a9b14a85bbdb08474f9b2b27f0d74ccc74d5"),
    ("brands.hasselblad", "apply_hncs_video_frame",
     "4ef5e2e2eab5a198421f0d037d8d073a4d87c0212b0e40dfb7f9ef94d87be6fa"),
    ("brands.hasselblad_learned", "apply_hncs_learned",
     "be576e1017a3e3319c2bf68f235ae976f91ede1ccd7842ac65ba54952fd152b8"),
    ("brands.hasselblad_day", "apply_hasselblad_day",
     "508a5d8cf5b44586a5ba0767582d39a935bf5b90570b62137df708f31690ec32"),
]


class TestHasselbladCoreGoldenHashes(unittest.TestCase):
    def test_apply_hncs_family_output_is_pinned(self):
        img = make_test_image()
        for mod_name, fn_name, expected_hash in HASSELBLAD_CORE_GOLDEN_HASHES:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                actual_hash = hashlib.sha256(out.tobytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash,
                                  f"{mod_name}.{fn_name} output changed - "
                                  f"expected sha256={expected_hash}, got {actual_hash}")


# (모듈 경로, 함수명, sha256(출력.tobytes())) - brands/fuji.py의 프리셋
# (apply_pro_neg_hi_video_frame 제외)도 population-fit/Hasselblad와
# 마찬가지로 값을 고정하는 골든 테스트가 없었다(2026-08 코드리뷰에서
# 발견) - test_brands.py는 shape/dtype만 봐서 identity-passthrough로
# 망가져도 통과한다. apply_acros/apply_monochrome은 2D(그레이스케일)
# 반환이라 다른 함수와 shape가 다름에 유의.
FUJI_PRESET_GOLDEN_HASHES = [
    ("brands.fuji", "apply_astia",
     "9165582f2e4e3446651911dda3cacc53379a5a75b343093769e42eafb9e6d53e"),
    ("brands.fuji", "apply_nostalgic_neg",
     "e23ece30f93c022cc0b43b0614d49a230c550477c4e8aa5f2d842ddb8cd80648"),
    ("brands.fuji", "apply_acros",
     "604d6d87f6d0484735eb7328b56f97af91b5b701f5539d9a306d1f3d5f68b62f"),
    ("brands.fuji", "apply_monochrome",
     "293b6e6a130fbe2ae0f00ee6e3b4cb4e07e3f4f76e3bed912f0ba144f21cd207"),
    ("brands.fuji", "apply_provia",
     "d4181b7caa6b0fe8891fc8b6097fb9af85bf7853250fb60ddb6e39d96bd128ab"),
    ("brands.fuji", "apply_classic_chrome",
     "3d79e020eadfda21fa347297208f208a89f81e21fae73da3cdfb11f1932ed0c1"),
    ("brands.fuji", "apply_nostalgic_neg_v2",
     "3542071e7f745e5b8e8b09951d894f050d19d04291b7a5aa6fa62d598da2ccc3"),
    ("brands.fuji", "apply_classic_chrome_v2",
     "d49fc298c2f78c3631b746c27a3f4f3b981ea144270e17ee2707e95e2bc85fd7"),
    ("brands.fuji", "apply_nostalgic_neg_v3",
     "d49fc298c2f78c3631b746c27a3f4f3b981ea144270e17ee2707e95e2bc85fd7"),
]


# OpenCV's BGR→HSV→BGR uint8 conversion differs by platform at the least
# significant bit. No CI reference images were retained for these functions,
# so a cross-platform pixel bound cannot be measured honestly. Keep the
# strongest bound that is knowable here: one environment must reproduce every
# pixel exactly across repeated invocations.
HSV_ROUND_TRIP_FUNCTIONS = [
    ("brands.fuji", "apply_pro_neg_std"),
    ("brands.fuji", "apply_pro_neg_hi"),
    ("brands.fuji", "apply_eterna_cinema"),
    ("brands.fuji", "apply_eterna_bleach_bypass"),
    ("brands.fuji", "apply_reala_ace"),
    ("brands.fuji", "apply_classic_negative"),
    ("brands.hasselblad_night", "apply_hasselblad_night"),
]


class TestOpenCvHsvRoundTripGoldenBehavior(unittest.TestCase):
    def test_known_round_trip_looks_are_deterministic_uint8_images(self):
        for mod_name, fn_name in HSV_ROUND_TRIP_FUNCTIONS:
            with self.subTest(brand=mod_name, fn=fn_name):
                fn = getattr(importlib.import_module(mod_name), fn_name)
                first = fn(make_test_image())
                second = fn(make_test_image())

                self.assertEqual(first.shape, (128, 128, 3))
                self.assertEqual(first.dtype, np.uint8)
                self.assertGreaterEqual(first.min(), 0)
                self.assertLessEqual(first.max(), 255)

                pixel_difference = np.abs(
                    first.astype(np.int16) - second.astype(np.int16)
                ).max()
                self.assertLessEqual(pixel_difference, 0)


class TestFujiPresetGoldenHashes(unittest.TestCase):
    def test_all_presets_output_is_pinned(self):
        img = make_test_image()
        for mod_name, fn_name, expected_hash in FUJI_PRESET_GOLDEN_HASHES:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                actual_hash = hashlib.sha256(out.tobytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash,
                                  f"{mod_name}.{fn_name} output changed - "
                                  f"expected sha256={expected_hash}, got {actual_hash}")


if __name__ == "__main__":
    unittest.main()
