"""Sony/Sigma/Leica의 `<brand>_generic_jpeg_approx.icc`(2026-09-02,
`tools/fit_brand_native_matrix_for_icc.py`)가 커밋된
`native_matrix_for_icc_report.json`의 매트릭스로 만들어진 게 맞는지
확인 - `tests/test_icc_export.py`의 `TestShippedIccProfileMatchesReport`
와 같은 역할, 3브랜드 파라미터화."""
import json
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.icc_export import srgb_linear_to_xyz_d50_matrix
from tests.test_icc_export import _parse_icc_tags, _xyz_tag_value

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BRANDS = ["sony", "sigma", "leica"]


class TestBrandJpegApproxIccProfiles(unittest.TestCase):
    def test_xyz_tags_match_composed_report_matrix(self):
        for brand in _BRANDS:
            with self.subTest(brand=brand):
                icc_path = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles",
                                         f"{brand}_generic_jpeg_approx.icc")
                report_path = os.path.join(_REPO_ROOT, "datasets", brand, "contributed",
                                            "native_matrix_for_icc_report.json")
                if not (os.path.exists(icc_path) and os.path.exists(report_path)):
                    self.skipTest(f"{brand}: .icc/리포트 JSON 없음")
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
