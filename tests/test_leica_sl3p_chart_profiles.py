"""커밋된 `leica_sl3p_chart.dcp`/`.icc`가 커밋된
`datasets/leica/contributed/dpreview-sl3p-studio-chart-2026-09/camera_native_matrix_report.json`
에서 올바른 변환으로 생성됐는지 확인 - 하셀블라드 쪽
`TestShippedProfileMatchesReport`/`TestShippedIccProfileMatchesReport`
와 같은 역할."""
import json
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dcp_export import read_dcp, TAG_COLOR_MATRIX_1, TAG_CALIBRATION_ILLUMINANT_1
from tests.test_icc_export import _parse_icc_tags, _xyz_tag_value

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHIPPED_DCP = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles", "leica_sl3p_chart.dcp")
_SHIPPED_ICC = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles", "leica_sl3p_chart.icc")
_REPORT_JSON = os.path.join(_REPO_ROOT, "datasets", "leica", "contributed",
                             "dpreview-sl3p-studio-chart-2026-09", "camera_native_matrix_report.json")


class TestLeicaSl3pChartDcpMatchesReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (os.path.exists(_SHIPPED_DCP) and os.path.exists(_REPORT_JSON)):
            raise unittest.SkipTest("커밋된 .dcp/리포트 JSON이 없음")
        with open(_REPORT_JSON, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.tags = read_dcp(_SHIPPED_DCP)
        cls.cm1 = cls.tags[TAG_COLOR_MATRIX_1].reshape(3, 3)
        cls.chart_m = np.array(cls.report["chart_matrix_in_sample"], dtype=np.float64)

    def test_color_matrix_1_is_inverse_transpose_not_plain_inverse(self):
        expected = np.linalg.inv(self.chart_m).T
        np.testing.assert_allclose(self.cm1, expected, atol=1e-6)
        self.assertFalse(np.allclose(self.cm1, np.linalg.inv(self.chart_m), atol=1e-6))

    def test_report_dcp_color_matrix_field_matches_the_file(self):
        np.testing.assert_allclose(
            self.cm1, np.array(self.report["dcp_color_matrix_1"], dtype=np.float64), atol=1e-6)

    def test_calibration_illuminant_is_d50(self):
        self.assertEqual(self.tags[TAG_CALIBRATION_ILLUMINANT_1], 23)


class TestLeicaSl3pChartIccMatchesReport(unittest.TestCase):
    def test_xyz_tags_match_report_matrix_rows(self):
        if not (os.path.exists(_SHIPPED_ICC) and os.path.exists(_REPORT_JSON)):
            self.skipTest("커밋된 .icc/리포트 JSON이 없음")
        with open(_REPORT_JSON, encoding="utf-8") as f:
            report = json.load(f)
        m = np.array(report["chart_matrix_in_sample"])
        parsed = _parse_icc_tags(_SHIPPED_ICC)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"rXYZ"), m[0, :], atol=1e-4)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"gXYZ"), m[1, :], atol=1e-4)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"bXYZ"), m[2, :], atol=1e-4)


if __name__ == "__main__":
    unittest.main()
