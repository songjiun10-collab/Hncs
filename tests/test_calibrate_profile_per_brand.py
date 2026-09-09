"""`hybrid_engine/calibrate_profile_<brand>.py` 6개가 서로의 복사본이라
생기는 브랜드 오기를 잡는다.

이 파일들은 `hybrid_engine/CLAUDE.md`가 명시한 "복사하되 결합하지 않는다"
컨벤션에 따라 의도적으로 서로의 복사본이다(공유 import 아님). 대신
복붙 특유의 실패 모드가 생긴다 - 실제로 2026-09-06에 leica 원본을 복사한
5개(canon/fuji/nikon/sigma/sony) 전부가 `leica` 문자열을 3곳씩 총 15곳
그대로 들고 있었고, 그중 하나는 페어를 못 찾았을 때 **사용자에게 남의
브랜드 디렉토리를 확인하라고 안내하는 런타임 메시지**였다(코드가 읽는
경로는 자기 브랜드가 맞았으므로 조용한 오안내였다).

`_CONTRIBUTED_ROOT`가 자기 브랜드를 가리키는지, 그리고 파일 어디에도 다른
브랜드 이름이 남아있지 않은지 본다. 해셀블라드는 예외 - 이 스크립트들이
공통으로 재사용하는 원본(`calibrate_profile.py`)이 해셀블라드 전용이라
독스트링이 정당하게 언급한다.
"""
import os
import re
import unittest

_HYBRID = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "hybrid_engine")
_BRANDS = ["canon", "fuji", "leica", "nikon", "sigma", "sony"]
# 원본 calibrate_profile.py가 해셀블라드 전용이라 모든 복사본이 정당하게 언급한다.
_ALLOWED_OTHER = {"hasselblad"}


def _source(brand):
    with open(os.path.join(_HYBRID, f"calibrate_profile_{brand}.py"), encoding="utf-8") as f:
        return f.read()


class TestPerBrandCalibrateScripts(unittest.TestCase):
    def test_contributed_root_points_at_its_own_brand(self):
        for brand in _BRANDS:
            with self.subTest(brand=brand):
                self.assertIn(f'"datasets", "{brand}", "contributed"', _source(brand))

    def test_no_other_brand_name_leaks_into_the_copy(self):
        for brand in _BRANDS:
            others = [b for b in _BRANDS if b != brand] + sorted(
                {"hasselblad", "olympus", "panasonic", "pentax", "phaseone", "ricoh_gr"}
                - _ALLOWED_OTHER)
            source = _source(brand)
            for line_no, line in enumerate(source.splitlines(), start=1):
                for other in others:
                    with self.subTest(brand=brand, other=other, line=line_no):
                        self.assertNotIn(
                            other, line,
                            f"calibrate_profile_{brand}.py:{line_no}에 다른 브랜드"
                            f" '{other}'가 남아있다 (복붙 잔재): {line.strip()}")

    def test_missing_pairs_message_names_its_own_dataset_directory(self):
        """페어가 없을 때 찍는 안내 경로가 실제로 읽는 경로와 같아야 한다 -
        여기가 15곳 중 유일하게 사용자 눈에 보이던 오기였다."""
        for brand in _BRANDS:
            with self.subTest(brand=brand):
                messages = re.findall(r'print\("페어를 못 찾음[^"]*"\)', _source(brand))
                self.assertEqual(len(messages), 1, f"{brand}: 안내 메시지가 1개가 아님")
                self.assertIn(f"datasets/{brand}/contributed", messages[0])


if __name__ == "__main__":
    unittest.main()
