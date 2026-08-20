"""`.claude/hooks/protect_destructive.py` 테스트 - `rm -r`+`-f` 콤보(스크래치
경로 예외), `git reset --hard`, `git clean` force, `git branch -D`를
잡는지, override 마커로 뚚리는지, 로그가 실제 git-tracked 파일을
오염시키지 않는지 확인."""
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
import protect_destructive as hook  # noqa: E402


class TestDestructiveReason(unittest.TestCase):
    def test_rm_rf_on_real_path_flagged(self):
        self.assertIsNotNone(hook.destructive_reason("rm -rf /home/user/Hncs/some/dir"))

    def test_rm_rf_under_tmp_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("rm -rf /tmp/scratch_dir"))

    def test_rm_rf_under_scratchpad_not_flagged(self):
        self.assertIsNone(hook.destructive_reason(
            "rm -rf /tmp/claude-0/x/scratchpad/foo"))

    def test_rm_force_only_no_recursive_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("rm -f single_file.txt"))

    def test_rm_no_flags_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("rm somefile.txt"))

    def test_git_reset_hard_flagged(self):
        self.assertIsNotNone(hook.destructive_reason("git reset --hard"))

    def test_git_reset_hard_with_ref_flagged(self):
        self.assertIsNotNone(hook.destructive_reason("git reset --hard origin/main"))

    def test_git_reset_soft_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("git reset --soft HEAD~1"))

    def test_git_clean_force_flagged(self):
        self.assertIsNotNone(hook.destructive_reason("git clean -fd"))

    def test_git_clean_dry_run_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("git clean -n"))

    def test_git_branch_capital_d_flagged(self):
        self.assertIsNotNone(hook.destructive_reason("git branch -D old-branch"))

    def test_git_branch_lowercase_d_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("git branch -d merged-branch"))

    def test_heredoc_prose_mention_not_flagged(self):
        cmd = ('git commit -m "$(cat <<XEOF\n'
               'explains that rm -rf / would be catastrophic\n'
               'XEOF\n)"')
        self.assertIsNone(hook.destructive_reason(cmd))

    def test_safe_command_not_flagged(self):
        self.assertIsNone(hook.destructive_reason("ls -la"))


class TestProtectDestructiveEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._tmpdir, "violations.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._tmpdir, "override_audit.jsonl"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(self._tmpdir, ".pending_decision_record.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_decision_record(self, target):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env["HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_destructive", "CRITICAL", 0.9, "테스트 자기평가", "테스트 위험", target=target)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def _run_hook(self, command, agent_id=None):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "protect_destructive.py")],
            input=json.dumps(payload), env=self._env, capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_git_reset_hard_denied_end_to_end(self):
        self.assertEqual(self._run_hook("git reset --hard"), "deny")

    def test_safe_command_allowed_end_to_end(self):
        self.assertEqual(self._run_hook("ls -la"), "allow")

    def test_override_allows_and_is_audited(self):
        cmd = "git reset --hard  # HNCS-OVERRIDE: protect_destructive: 의도된 초기화"
        self._write_decision_record(cmd)
        self.assertEqual(self._run_hook(cmd), "allow")
        audit_path = os.path.join(self._tmpdir, "override_audit.jsonl")
        with open(audit_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_destructive")
        self.assertEqual(entry["severity"], "CRITICAL")
        self.assertEqual(entry["reason"], "의도된 초기화")

    def test_override_without_decision_record_still_denied(self):
        """2026-08-16 필수 게이트: 유효한 override가 있어도 decision
        record 없으면 무조건 deny - 예외 없음."""
        cmd = "git reset --hard  # HNCS-OVERRIDE: protect_destructive: 의도된 초기화"
        self.assertEqual(self._run_hook(cmd), "deny")

    def test_wrong_rule_override_still_denied(self):
        cmd = "git reset --hard  # HNCS-OVERRIDE: protect_never_touch: 사유"
        self._write_decision_record(cmd)
        self.assertEqual(self._run_hook(cmd), "deny")

    def test_subagent_call_denied_even_with_valid_override(self):
        """CRITICAL 등급: 서브에이전트발 호출은 override조차 안 받는다 -
        bash 주석은 서브에이전트 스스로도 쓸 수 있어서 self-servable
        문제가 가장 치명적인 등급이라 아예 통로를 없았다(2026-08-15)."""
        cmd = "git reset --hard  # HNCS-OVERRIDE: protect_destructive: 의도된 초기화"
        self.assertEqual(self._run_hook(cmd, agent_id="agt_1"), "deny")


if __name__ == "__main__":
    unittest.main()
