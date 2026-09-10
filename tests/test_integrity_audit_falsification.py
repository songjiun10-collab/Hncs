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
                handle.write('PROFILE = "hybrid_engine/assets/profiles/missing.json"\n')

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


if __name__ == "__main__":
    unittest.main()
