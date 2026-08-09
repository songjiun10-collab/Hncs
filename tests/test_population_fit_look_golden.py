"""population-fit 브랜드 12개의 apply_*_look() 출력이 core/engine.py
리팩토링(docs/superpowers/plans/2026-08-09-population-fit-wrapper-consolidation.md)
전후로 완전히 동일한지 확인하는 골든 회귀 테스트. 해시는 리팩토링 전
실제 코드를 돌려서 뽑은 값 그대로다 - 값 자체가 맞는지는 검증하지
않는다(그건 각 브랜드 docstring의 population 수치가 담당), 오직
"이 리팩토링이 픽셀 출력을 하나도 안 바꿨는지"만 확인한다."""
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


if __name__ == "__main__":
    unittest.main()
