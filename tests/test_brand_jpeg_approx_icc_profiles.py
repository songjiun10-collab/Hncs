"""`<brand>_generic_jpeg_approx.icc`(2026-09-02,
`tools/fit/fit_brand_native_matrix_for_icc.py`)가 커밋된
`native_matrix_for_icc_report.json`의 매트릭스로 만들어진 게 맞는지 확인 -
`tests/test_icc_export.py`의 `TestShippedIccProfileMatchesReport`와 같은
역할.

**정정(2026-09-07)**: `_BRANDS`가 `["sony", "sigma", "leica"]`로 수동
하드코딩돼 있었는데, `fuji_generic_jpeg_approx.icc`가 실제로 배포돼
있고(`datasets/fuji/contributed/native_matrix_for_icc_report.json`도
있음) 그 목록엔 없어서 Fuji ICC가 report와 다른 바이너리로 바뀌어도 이
테스트가 못 잡는 상태였다. 브랜드/저장소가 12개까지 늘어나면서 이 레포가
반복해서 겪은 "수동 목록 drift"와 같은 종류 - Capture One 배치가
`BRAND_LOOKS`만 재사용했다가 Fuji 프리셋 13개를 통째로 빠뜨렸던 사건
(`docs/project_structure.md`의 `build_all_capture_one_look_iccs.py` 행)과
같은 실패 클래스다. 그래서 하드코딩 목록 대신 실제 배포된
`*_generic_jpeg_approx.icc` 파일을 글롭으로 찾아 브랜드를 역산한다 - 새
브랜드가 이 ICC를 배포하면 파일을 추가하는 순간 자동으로 검사 대상이
된다. report가 없는데 ICC만 있으면 이제 skip이 아니라 실패다(ICC는
gitignore 대상이 아니라 항상 커밋돼 있으므로 - report 부재는 진짜
provenance 누락)."""
import glob
import json
import os
import re
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.icc_export import srgb_linear_to_xyz_d50_matrix
from tests.test_icc_export import _parse_icc_tags, _xyz_tag_value

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROFILES_DIR = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles")


def _shipped_generic_jpeg_approx_brands():
    """`<brand>_generic_jpeg_approx.icc`로 배포된 브랜드 이름 전부 - 파일
    존재 자체가 목록이므로 새 브랜드가 추가돼도 여기를 고칠 필요가 없다."""
    brands = []
    for path in sorted(glob.glob(os.path.join(_PROFILES_DIR, "*_generic_jpeg_approx.icc"))):
        m = re.fullmatch(r"(.+)_generic_jpeg_approx\.icc",
                         os.path.basename(path))
        brands.append(m.group(1))
    return brands


class TestBrandJpegApproxIccProfiles(unittest.TestCase):
    def test_at_least_currently_known_brands_are_discovered(self):
        # 글롭이 조용히 0개(혹은 일부만)를 찾고 아래 서브테스트가 그 축소된
        # 집합만으로 "성공"하는 걸 막는 구조적 불변식. >=1로는 sony/sigma/
        # leica/fuji 중 3개가 실수로 사라져도 통과한다 - 그래서 지금 실제로
        # 배포된 4개를 하한으로 못박는다. 새 브랜드가 이 ICC를 배포하면
        # 이 숫자를 올리는 게 맞다(하드코딩 브랜드 이름 목록이 아니라 "몇
        # 개는 있어야 정상인가"라는 하한이라 목록 drift와는 다른 종류).
        self.assertGreaterEqual(len(_shipped_generic_jpeg_approx_brands()), 4)

    def test_xyz_tags_match_composed_report_matrix(self):
        for brand in _shipped_generic_jpeg_approx_brands():
            with self.subTest(brand=brand):
                icc_path = os.path.join(_PROFILES_DIR, f"{brand}_generic_jpeg_approx.icc")
                report_path = os.path.join(_REPO_ROOT, "datasets", brand, "contributed",
                                            "native_matrix_for_icc_report.json")
                self.assertTrue(
                    os.path.exists(report_path),
                    f"{brand}: ICC는 배포됐는데 report JSON이 없음 - "
                    f"provenance 없이 나간 프로필(datasets/{brand}/contributed/"
                    f"native_matrix_for_icc_report.json 없음)")
                with open(report_path, encoding="utf-8") as f:
                    report = json.load(f)
                native_to_srgb = np.array(report["native_to_srgb_linear_matrix"])
                expected_xyz = native_to_srgb @ srgb_linear_to_xyz_d50_matrix()

                parsed = _parse_icc_tags(icc_path)
                np.testing.assert_allclose(_xyz_tag_value(parsed, b"rXYZ"), expected_xyz[0, :], atol=1e-4)
                np.testing.assert_allclose(_xyz_tag_value(parsed, b"gXYZ"), expected_xyz[1, :], atol=1e-4)
                np.testing.assert_allclose(_xyz_tag_value(parsed, b"bXYZ"), expected_xyz[2, :], atol=1e-4)


if __name__ == "__main__":
    unittest.main()
