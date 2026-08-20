"""`.claude/hooks/protect_decision_record_bypass.py` 테스트 -
`.pending_decision_record.json`에 대한 직접 Write/Edit가 override 없이
무조건 deny되는지, 다른 파일/툴은 영향 없는지 확인."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks")
sys.path.insert(0, _HOOKS_DIR)
import protect_decision_record_bypass as hook  # noqa: E402


class TestIsDecisionRecordPath(unittest.TestCase):
    def test_matches_default_path(self):
        import _hook_common
        self.assertTrue(hook.is_decision_record_path(_hook_common._DECISION_RECORD_PATH))

    def test_other_file_not_matched(self):
        self.assertFalse(hook.is_decision_record_path("README.md"))

    def test_empty_path_not_matched(self):
        self.assertFalse(hook.is_decision_record_path(""))


class TestProtectDecisionRecordBypassEndToEnd(unittest.TestCase):
    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        self._sentinel_path = os.path.join(self._log_dir, ".pending_decision_record.json")
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": self._sentinel_path,
        })

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _run_hook(self, tool_name, tool_input):
        payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_write_to_sentinel_denied(self):
        decision = self._run_hook("Write", {
            "file_path": self._sentinel_path, "content": '{"rule": "x"}',
        })
        self.assertEqual(decision, "deny")

    def test_edit_to_sentinel_denied(self):
        decision = self._run_hook("Edit", {
            "file_path": self._sentinel_path, "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "deny")

    def test_other_file_allowed(self):
        decision = self._run_hook("Write", {"file_path": "README.md", "content": "x"})
        self.assertEqual(decision, "allow")

    def test_non_matching_tool_allowed(self):
        decision = self._run_hook("Read", {"file_path": self._sentinel_path})
        self.assertEqual(decision, "allow")


if __name__ == "__main__":
    unittest.main()
