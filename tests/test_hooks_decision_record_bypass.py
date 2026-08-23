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

    def test_matches_whole_branch_review_sha_path(self):
        """2026-08-20 정정 (README 2차 라운드 #8, 가장 약한 고리): 이전엔
        이 경로가 어떤 훅으로도 보호 안 됐음 - 격리 scratch repo에서
        `echo -n $(git rev-parse HEAD) > .last_whole_branch_review_sha`
        한 줄로 "최종 리뷰 통과"를 완전히 위조할 수 있었다."""
        import _hook_common
        self.assertIsNotNone(
            hook.protected_sentinel_writer(_hook_common._WHOLE_BRANCH_REVIEW_SHA_PATH))

    def test_other_file_not_matched(self):
        self.assertIsNone(hook.protected_sentinel_writer("README.md"))

    def test_empty_path_not_matched(self):
        self.assertIsNone(hook.protected_sentinel_writer(""))


class TestBashWriteTarget(unittest.TestCase):
    """2026-08-20 정정 (README 1차 라운드 finding): 이 훅이 원래
    Edit|Write|MultiEdit matcher에만 등록돼 있어서, Bash로 직접
    `python3 -c "...open('.pending_decision_record.json','w')..."`
    같은 명령을 실행하면 아예 안 걸렸다 - Bash 커버리지 추가."""

    def test_python_open_write_detected(self):
        target = hook.bash_write_target(
            "python3 -c \"open('.claude/hooks/.pending_decision_record.json','w').write('{}')\"")
        self.assertIsNotNone(target)

    def test_redirect_detected(self):
        target = hook.bash_write_target(
            "echo '{}' > .claude/hooks/.pending_consensus.json")
        self.assertIsNotNone(target)

    def test_unrelated_command_not_matched(self):
        self.assertIsNone(hook.bash_write_target("ls -la"))

    def test_read_only_reference_not_matched(self):
        # cp/mv dest-only matching means a read of the sentinel (not the
        # last positional arg of cp/mv, no redirect/open-for-write) is fine.
        self.assertIsNone(hook.bash_write_target(
            "cat .claude/hooks/.pending_decision_record.json"))


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

    def _run_bash_hook(self, command):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_bash_python_write_to_decision_record_sentinel_denied(self):
        decision = self._run_bash_hook(
            f"python3 -c \"open('{self._sentinel_path}','w').write('{{}}')\"")
        self.assertEqual(decision, "deny")

    def test_bash_redirect_to_consensus_sentinel_denied(self):
        decision = self._run_bash_hook(f"echo '{{}}' > {self._consensus_path}")
        self.assertEqual(decision, "deny")

    def test_bash_unrelated_command_allowed(self):
        self.assertEqual(self._run_bash_hook("ls -la"), "allow")


if __name__ == "__main__":
    unittest.main()
