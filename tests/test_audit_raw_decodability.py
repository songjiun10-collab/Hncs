"""`tools/audit_raw_decodability.py` 단위 테스트 + 기록된 실행 회귀 테스트.

이 감사가 잡아낸 것: 소니 `dpreview-a7v-preprod-2026-08`의 실효 표본이
매니페스트 62행이 아니라 **22쌍**이다(나머지 40개는 LibRaw 0.22.1이
미지원하는 `Sony Compressed RAW 2` 손실 압축). 그 숫자가
`hybrid_engine/EVALUATION.md`에 실려 있으므로 커밋된 리포트에서 다시
확인한다.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import audit_raw_decodability as ard

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(BASE, "datasets", "raw_decodability_audit.json")


class TestAuditSet(unittest.TestCase):
    def test_reports_non_raw_files_as_failures(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "notaraw.arw"), "wb") as f:
                f.write(b"this is not a raw file")
            ok, failures = ard.audit_set(d)
            self.assertEqual(ok, [])
            self.assertEqual(len(failures), 1)
            self.assertEqual(failures[0]["filename"], "notaraw.arw")
            self.assertIn("Error", failures[0]["error"])
            self.assertEqual(failures[0]["size_bytes"], 22)

    def test_empty_directory_yields_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ard.audit_set(d), ([], []))

    def test_skips_dotfiles(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".DS_Store"), "wb") as f:
                f.write(b"\x00")
            self.assertEqual(ard.audit_set(d), ([], []))

    def test_skips_subdirectories(self):
        with tempfile.TemporaryDirectory() as d:
            os.mkdir(os.path.join(d, "nested"))
            self.assertEqual(ard.audit_set(d), ([], []))

    def test_failure_entries_carry_the_fields_the_report_needs(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x.arw"), "wb") as f:
                f.write(b"nope")
            _, failures = ard.audit_set(d)
            for key in ("filename", "size_bytes", "error", "raw_subtype"):
                self.assertIn(key, failures[0])


class TestRecordedAudit(unittest.TestCase):
    """EVALUATION.md의 소니 22/40 분할이 커밋된 리포트와 일치하는지."""

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(REPORT):
            raise unittest.SkipTest(f"리포트 없음: {REPORT}")
        with open(REPORT, encoding="utf-8") as f:
            cls.rep = json.load(f)

    def test_total_failures_match_evaluation_md(self):
        self.assertEqual(self.rep["total_failed"], 40)

    def test_sony_effective_sample_is_22_not_62(self):
        sony = [s for s in self.rep["sets"] if "sony" in s["set"]]
        self.assertEqual(len(sony), 1)
        self.assertEqual((sony[0]["n_ok"], sony[0]["n_failed"]), (22, 40))

    def test_every_sony_failure_is_lossy_compressed_not_corruption(self):
        sony = next(s for s in self.rep["sets"] if "sony" in s["set"])
        for f_ in sony["failures"]:
            self.assertIn("Sony Compressed RAW 2", f_["raw_subtype"])
            self.assertIn("LibRawFileUnsupportedError", f_["error"])

    def test_no_other_set_has_failures(self):
        for s in self.rep["sets"]:
            if "sony" not in s["set"]:
                self.assertEqual(s["n_failed"], 0, msg=s["set"])

    def test_records_the_decoder_version_that_produced_the_result(self):
        # 판정이 LibRaw 버전에 달려 있으므로 리포트가 버전을 남겨야 한다
        self.assertEqual(self.rep["libraw_version"], [0, 22, 1])
        self.assertTrue(self.rep["rawpy_version"])


if __name__ == "__main__":
    unittest.main()
