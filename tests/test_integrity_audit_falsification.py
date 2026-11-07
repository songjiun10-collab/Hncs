import builtins
import os
import tempfile
import unittest
from unittest import mock

from tools.maintenance import audit_repo_integrity as audit


class TestIntegrityAuditReadFailures(unittest.TestCase):
    def test_unreadable_python_source_is_reported_not_silently_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, "probe.py")
            with open(source_path, "w", encoding="utf-8") as handle:
                # 확장자를 쪼개 둔다 - 통째로 쓰면 이 파일 자체가 실제 저장소
                # 감사(check_asset_refs)에 '참조 대상 없음'으로 잡힌다.
                handle.write('PROFILE = "hybrid_engine/assets/profiles/missing.' + 'json"\n')

            real_open = builtins.open

            def failing_open(path, *args, **kwargs):
                if os.fspath(path) == source_path:
                    raise PermissionError("falsification probe")
                return real_open(path, *args, **kwargs)

            with mock.patch.object(audit, "BASE", tmp), \
                    mock.patch("builtins.open", side_effect=failing_open):
                problems = audit.check_asset_refs()

        self.assertEqual(len(problems), 1)
        self.assertIn("읽기 실패", problems[0])
        self.assertIn("probe.py", problems[0])

    def test_exiftool_nonzero_exit_is_failure_even_if_stdout_says_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = os.path.join(tmp, "probe.dcp")
            with open(profile_path, "wb") as handle:
                handle.write(b"probe")

            result = mock.Mock(returncode=1, stdout="OK\n", stderr="synthetic failure")
            with mock.patch.object(audit, "PROFILES", tmp), \
                    mock.patch.object(audit.shutil, "which", return_value="/usr/bin/exiftool"), \
                    mock.patch.object(audit.subprocess, "run", return_value=result):
                problems = audit.check_profiles()

        self.assertEqual(len(problems), 1)
        self.assertIn("exiftool 종료코드", problems[0])
        self.assertIn("probe.dcp", problems[0])


if __name__ == "__main__":
    unittest.main()
