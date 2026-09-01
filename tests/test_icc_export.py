"""`core/icc_export.py` 검증 - 구조(순수 struct 파싱, 외부 의존성 없음),
매트릭스 방향 라운드트립, 그리고 가능하면(`transicc` 설치돼 있으면)
완전히 독립적인 lcms2 구현으로 실제 색변환까지 재확인한다."""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.icc_export import write_icc_matrix_trc_profile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SHIPPED_ICC = os.path.join(_REPO_ROOT, "hybrid_engine", "assets", "profiles",
                             "hasselblad_x2dii_chart.icc")
_REPORT_JSON = os.path.join(_REPO_ROOT, "datasets", "hasselblad", "contributed",
                             "kmichels-x2dii-2026-07", "camera_native_matrix_report.json")


def _parse_icc_tags(path):
    """순수 struct 기반 최소 파서 - 헤더 필드 일부와 태그 테이블
    {sig: (offset, size)}만 반환. write_icc_matrix_trc_profile()과
    독립적으로 구현(같은 버그를 두 번 짜지 않기 위해 write 쪽 헬퍼는
    재사용하지 않음)."""
    with open(path, "rb") as f:
        data = f.read()
    device_class = data[12:16]
    colorspace = data[16:20]
    pcs = data[20:24]
    acsp = data[36:40]
    (ntags,) = struct.unpack_from(">I", data, 128)
    tags = {}
    for i in range(ntags):
        off = 132 + 12 * i
        sig, offset, size = struct.unpack_from(">4sII", data, off)
        tags[sig] = (offset, size)
    return dict(device_class=device_class, colorspace=colorspace, pcs=pcs,
                acsp=acsp, tags=tags, data=data)


def _xyz_tag_value(parsed, sig):
    offset, size = parsed["tags"][sig]
    data = parsed["data"]
    assert data[offset:offset + 4] == b"XYZ "
    x, y, z = struct.unpack_from(">iii", data, offset + 8)
    return np.array([x, y, z], dtype=np.float64) / 65536.0


class TestIccExportStructure(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "test.icc")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_header_fields(self):
        m = np.eye(3)
        write_icc_matrix_trc_profile(self.path, m, description="test profile")
        parsed = _parse_icc_tags(self.path)
        self.assertEqual(parsed["device_class"], b"scnr")
        self.assertEqual(parsed["colorspace"], b"RGB ")
        self.assertEqual(parsed["pcs"], b"XYZ ")
        self.assertEqual(parsed["acsp"], b"acsp")

    def test_required_tags_present(self):
        m = np.eye(3)
        write_icc_matrix_trc_profile(self.path, m, description="test profile")
        parsed = _parse_icc_tags(self.path)
        for sig in (b"desc", b"cprt", b"wtpt", b"chad",
                    b"rXYZ", b"gXYZ", b"bXYZ", b"rTRC", b"gTRC", b"bTRC"):
            self.assertIn(sig, parsed["tags"], f"{sig!r} 태그 없음")

    def test_matrix_rows_round_trip_into_xyz_tags(self):
        """이 프로젝트가 DCP에서 한 번 겪은 전치 버그 재발 방지 - 매트릭스의
        각 행이 정확히 rXYZ/gXYZ/bXYZ로 그대로 들어가는지(전치 없이)
        확인한다."""
        m = np.array([
            [0.5, 0.1, -0.05],
            [0.2, 0.9, 0.15],
            [-0.1, 0.05, 1.2],
        ])
        write_icc_matrix_trc_profile(self.path, m, description="test profile")
        parsed = _parse_icc_tags(self.path)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"rXYZ"), m[0, :], atol=1e-4)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"gXYZ"), m[1, :], atol=1e-4)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"bXYZ"), m[2, :], atol=1e-4)

    def test_wtpt_and_chad_are_d50_and_identity(self):
        m = np.eye(3)
        write_icc_matrix_trc_profile(self.path, m, description="test profile")
        parsed = _parse_icc_tags(self.path)
        np.testing.assert_allclose(_xyz_tag_value(parsed, b"wtpt"),
                                    [0.9642, 1.0, 0.8249], atol=1e-4)
        offset, size = parsed["tags"][b"chad"]
        data = parsed["data"]
        self.assertEqual(data[offset:offset + 4], b"sf32")
        values = struct.unpack_from(">9i", data, offset + 8)
        chad = np.array(values, dtype=np.float64).reshape(3, 3) / 65536.0
        np.testing.assert_allclose(chad, np.eye(3), atol=1e-4)

    def test_rejects_wrong_shape(self):
        with self.assertRaises(ValueError):
            write_icc_matrix_trc_profile(self.path, np.eye(4), description="bad")


class TestShippedIccProfileMatchesReport(unittest.TestCase):
    """커밋된 `.icc`가 커밋된 리포트 JSON의 매트릭스로 만들어진 게
    맞는지 확인 - DCP 쪽 `TestShippedProfileMatchesReport`와 같은 역할."""

    @classmethod
    def setUpClass(cls):
        if not (os.path.exists(_SHIPPED_ICC) and os.path.exists(_REPORT_JSON)):
            raise unittest.SkipTest("커밋된 .icc/리포트 JSON이 없음")
        with open(_REPORT_JSON, encoding="utf-8") as f:
            cls.report = json.load(f)
        cls.parsed = _parse_icc_tags(_SHIPPED_ICC)

    def test_xyz_tags_match_report_matrix_rows(self):
        m = np.array(self.report["chart_matrix_in_sample_irls_cyan_init"])
        np.testing.assert_allclose(_xyz_tag_value(self.parsed, b"rXYZ"), m[0, :], atol=1e-4)
        np.testing.assert_allclose(_xyz_tag_value(self.parsed, b"gXYZ"), m[1, :], atol=1e-4)
        np.testing.assert_allclose(_xyz_tag_value(self.parsed, b"bXYZ"), m[2, :], atol=1e-4)


class TestIccExportViaSystemLcms(unittest.TestCase):
    """`transicc`(homebrew littlecms, 시스템에 있으면)로 이 모듈이 아닌
    완전히 독립적인 lcms2 구현이 실제로 이 프로필을 로드하고 색변환에
    쓸 수 있는지 확인 - 없으면 스킵(CI에 littlecms 없을 수 있음)."""

    def setUp(self):
        if shutil.which("transicc") is None:
            raise unittest.SkipTest("transicc(littlecms CLI) 없음")
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "test.icc")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_neutral_native_rgb_maps_near_d50_via_transicc(self):
        m = np.array([
            [2.30377598, 0.83693656, 0.06218077],
            [0.25188437, 1.18293063, -0.28687024],
            [0.18039089, -0.37842875, 2.73171984],
        ])
        write_icc_matrix_trc_profile(self.path, m, description="test profile")
        neutral_255 = np.array([0.40938373, 1.0, 0.49396209]) * 255.0
        proc = subprocess.run(
            ["transicc", "-i", self.path, "-o", "*XYZ", "-t1"],
            input=f"{neutral_255[0]} {neutral_255[1]} {neutral_255[2]}\n",
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        import re
        nums = [float(x) for x in re.findall(r"[XYZ]=(-?\d+\.?\d*)", proc.stdout)]
        self.assertEqual(len(nums), 3, proc.stdout)
        xyz = np.array(nums) / nums[1]  # Y=1 정규화
        np.testing.assert_allclose(xyz, [0.9642, 1.0, 0.8249], atol=0.02)


if __name__ == "__main__":
    unittest.main()
