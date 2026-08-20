"""`.claude/hooks/protect_decision_record_bypass.py` 테스트 -
`.pending_decision_record.json`/`.pending_consensus.json`에 대한 직접
Write/Edit가 override 없이 무조건 deny되는지, 다른 파일/툴은 영향
없는지 확인.

**정정(2026-08-19)**: 이 훅이 단일 경로 하드코딩에서 여러 sentinel을
보호하는 테이블로 일반화되면서(HNCS Hook Evolution phase 1,
`.pending_consensus.json` 추가 보호) `is_decision_record_path()`가
`protected_sentinel_writer()`로 바뀌었다 - 아래 테스트도 그에 맞춰
갱신, `.pending_consensus.json` 케이스 추가."""
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


class TestProtectedSentinelWriter(unittest.TestCase):
    def test_matches_decision_record_path(self):
        import _hook_common
        self.assertIsNotNone(
            hook.protected_sentinel_writer(_hook_common._DECISION_RECORD_PATH))

    def test_matches_consensus_path(self):
        import _hook_common
        self.assertIsNotNone(
            hook.protected_sentinel_writer(_hook_common._CONSENSUS_PATH))

    def test_other_file_not_matched(self):
        self.assertIsNone(hook.protected_sentinel_writer("README.md"))

    def test_empty_path_not_matched(self):
        self.assertIsNone(hook.protected_sentinel_writer(""))


class TestProtectDecisionRecordBypassEndToEnd(unittest.TestCase):
    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        self._sentinel_path = os.path.join(self._log_dir, ".pending_decision_record.json")
        self._consensus_path = os.path.join(self._log_dir, ".pending_consensus.json")
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": self._sentinel_path,
            "HNCS_HOOK_CONSENSUS_SENTINEL": self._consensus_path,
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

    def test_write_to_decision_record_sentinel_denied(self):
        decision = self._run_hook("Write", {
            "file_path": self._sentinel_path, "content": '{"rule": "x"}',
        })
        self.assertEqual(decision, "deny")

    def test_edit_to_decision_record_sentinel_denied(self):
        decision = self._run_hook("Edit", {
            "file_path": self._sentinel_path, "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "deny")

    def test_write_to_consensus_sentinel_denied(self):
        decision = self._run_hook("Write", {
            "file_path": self._consensus_path, "content": '{"rule": "x"}',
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
