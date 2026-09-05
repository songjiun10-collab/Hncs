"""`tools/audit_repo_integrity.py`의 프로필 헤더 검사 회귀 테스트.

이 검사가 따로 있는 이유는 `exiftool -validate`가 DCP 매직이 틀린 파일에도
`Validate: OK`를 내기 때문이다(`tests/test_dcp_export.py`의
`test_header_uses_dcp_magic_not_standard_tiff_magic` 주석 - 2026-08-31에
Lightroom이 프로필을 못 읽던 실제 원인). 그래서 여기서는 "정상 파일이
통과한다"만 보지 않고 **그 버그를 그대로 재현한 파일이 실제로 걸리는지**를
같이 본다(`tests/CLAUDE.md`: 테스트는 틀릴 수 있어야 한다).
"""
import os
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from core.dcp_export import write_dcp
from core.icc_export import write_icc_matrix_trc_profile
from tools.audit_repo_integrity import (check_profiles, dcp_header_problems,
                                        icc_header_problems)

_CM1 = np.array([[0.9, -0.2, -0.1], [-0.3, 1.2, 0.05], [0.02, -0.25, 0.8]])
_NATIVE_TO_XYZ = np.array([[0.6, 0.3, 0.02], [0.2, 0.7, 0.1], [0.15, 0.05, 0.7]])


class TestDcpHeaderProblems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sample.dcp")
        write_dcp(self.path, "X2D II 100C", "test", _CM1, 21)

    def _patch_header(self, byte_order=b"II", magic=0x4352, first_ifd=8):
        with open(self.path, "r+b") as f:
            f.write(struct.pack("<2sHI", byte_order, magic, first_ifd))

    def test_written_dcp_passes(self):
        self.assertEqual(dcp_header_problems(self.path), [])

    def test_standard_tiff_magic_is_caught(self):
        # 실제로 배포됐던 버그: 42는 표준 TIFF 매직이고 DCP는 0x4352를
        # 요구한다. exiftool은 이걸 통과시킨다.
        self._patch_header(magic=42)
        problems = dcp_header_problems(self.path)
        self.assertEqual(len(problems), 1)
        self.assertIn("0x4352", problems[0])
        self.assertIn("표준 TIFF 매직 42", problems[0])

    def test_big_endian_byte_order_is_caught(self):
        self._patch_header(byte_order=b"MM")
        self.assertEqual(len(dcp_header_problems(self.path)), 1)

    def test_first_ifd_offset_past_end_of_file_is_caught(self):
        self._patch_header(first_ifd=os.path.getsize(self.path) + 1)
        problems = dcp_header_problems(self.path)
        self.assertEqual(len(problems), 1)
        self.assertIn("첫 IFD 오프셋이 파일 밖", problems[0])

    def test_truncated_header_is_caught(self):
        short = os.path.join(self.tmp.name, "short.dcp")
        with open(short, "wb") as f:
            f.write(b"II\x52\x43")
        self.assertEqual(len(dcp_header_problems(short)), 1)


class TestIccHeaderProblems(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sample.icc")
        write_icc_matrix_trc_profile(self.path, _NATIVE_TO_XYZ, "test")

    def test_written_icc_passes(self):
        self.assertEqual(icc_header_problems(self.path), [])

    def test_size_field_not_matching_file_is_caught(self):
        # 잘린 채 커밋된 프로필이 이렇게 보인다 - 헤더의 크기 필드는 원본
        # 그대로인데 파일이 짧다.
        with open(self.path, "r+b") as f:
            f.truncate(os.path.getsize(self.path) - 4)
        problems = icc_header_problems(self.path)
        self.assertTrue(any("프로필 크기가 실제와 다름" in p for p in problems))

    def test_missing_acsp_signature_is_caught(self):
        with open(self.path, "r+b") as f:
            f.seek(36)
            f.write(b"junk")
        problems = icc_header_problems(self.path)
        self.assertEqual(len(problems), 1)
        self.assertIn("acsp", problems[0])

    def test_tag_pointing_past_end_of_file_is_caught(self):
        size = os.path.getsize(self.path)
        with open(self.path, "r+b") as f:
            f.seek(132 + 4)  # 첫 태그 엔트리의 offset 필드
            f.write(struct.pack(">I", size))
        problems = icc_header_problems(self.path)
        self.assertTrue(any("태그가 파일 밖" in p for p in problems))

    def test_tag_count_larger_than_file_is_caught(self):
        with open(self.path, "r+b") as f:
            f.seek(128)
            f.write(struct.pack(">I", 100000))
        problems = icc_header_problems(self.path)
        self.assertTrue(any("태그 테이블이 파일 밖" in p for p in problems))


class TestCheckProfilesSkipsWithoutExiftool(unittest.TestCase):
    """exiftool이 없는 환경에서 traceback으로 죽지 않고 "건너뜀"을 반환해야
    한다 - 이상 없음(빈 리스트)과 구분돼야 마지막 줄에서 검증 범위를
    부풀리지 않는다."""

    def test_returns_none_when_exiftool_is_absent(self):
        with patch("tools.audit_repo_integrity.shutil.which", return_value=None):
            self.assertIsNone(check_profiles())

    def test_returns_list_when_exiftool_is_present(self):
        with patch("tools.audit_repo_integrity.shutil.which",
                   return_value="/usr/bin/exiftool"), \
             patch("tools.audit_repo_integrity.subprocess.run") as run:
            run.return_value.stdout = "OK\n"
            self.assertEqual(check_profiles(), [])
        self.assertTrue(run.called)


if __name__ == "__main__":
    unittest.main()
