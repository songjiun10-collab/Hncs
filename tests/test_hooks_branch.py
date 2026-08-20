"""`.claude/hooks/protect_branch.py` 테스트 - main/master/detached HEAD에서
commit/push 시도 시 걸리는지, override로 뚚리는지, 실제 작업 브랜치에서는
조용히 통과하는지."""
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
import protect_branch as hook  # noqa: E402


class TestBranchRiskReason(unittest.TestCase):
    def test_main_flagged(self):
        self.assertIsNotNone(hook.branch_risk_reason("main"))

    def test_master_flagged(self):
        self.assertIsNotNone(hook.branch_risk_reason("master"))

    def test_detached_head_flagged(self):
        self.assertIsNotNone(hook.branch_risk_reason("HEAD"))

    def test_feature_branch_not_flagged(self):
        self.assertIsNone(hook.branch_risk_reason("claude/hncs-v13-dpreview-calibration"))


class TestProtectBranchEndToEnd(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(self._log_dir, ".pending_decision_record.json"),
        })
        run = lambda *args: subprocess.run(  # noqa: E731
            args, cwd=self.repo, capture_output=True, text=True, check=True)
        run("git", "init", "-q", "-b", "main")
        run("git", "config", "user.email", "x@example.com")
        run("git", "config", "user.name", "x")
        with open(os.path.join(self.repo, "f.txt"), "w") as f:
            f.write("x")
        run("git", "add", "f.txt")
        run("git", "commit", "-q", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _write_decision_record(self, target):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env["HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_branch", "HIGH", 0.7, "테스트 자기평가", "테스트 위험", target=target)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def _run_hook(self, command, agent_id=None):
        payload = {"tool_name": "Bash", "tool_input": {"command": command}}
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, hook.__file__], cwd=self.repo, input=json.dumps(payload),
            env=self._env, capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_commit_on_main_asks(self):
        """HIGH tier, direct orchestrator call (no agent_id): real ask()
        prompt, not a hard deny - see _hook_common.py's 2026-08-15 tier
        redesign note. Requires a decision record first (2026-08-16
        mandatory gate)."""
        self._write_decision_record("main")
        self.assertEqual(self._run_hook('git commit -m "x"'), "ask")

    def test_push_on_main_asks(self):
        self._write_decision_record("main")
        self.assertEqual(self._run_hook("git push origin main"), "ask")

    def test_commit_on_main_from_subagent_denied(self):
        """HIGH tier, subagent-originated call (agent_id present): hard
        deny, no ask fallback - ask() fails open inside a subagent's own
        turn (confirmed live 2026-08-15), so this path must never route
        there."""
        self._write_decision_record("main")
        self.assertEqual(
            self._run_hook('git commit -m "x"', agent_id="agt_1"), "deny")

    def test_commit_on_main_without_decision_record_denied(self):
        """2026-08-16 필수 게이트: decision record 없으면 ask()도 안 띄고
        무조건 deny - override/ask 여부와 무관, 예외 없음."""
        self.assertEqual(self._run_hook('git commit -m "x"'), "deny")

    def test_commit_on_feature_branch_allowed(self):
        subprocess.run(["git", "checkout", "-b", "feature/x"], cwd=self.repo,
                        capture_output=True, text=True, check=True)
        self.assertEqual(self._run_hook('git commit -m "x"'), "allow")

    def test_non_commit_command_allowed(self):
        self.assertEqual(self._run_hook("git status"), "allow")

    def test_override_allows_commit_on_main(self):
        self._write_decision_record("main")
        cmd = 'git commit -m "x"  # HNCS-OVERRIDE: protect_branch: main이 작업 브랜치임'
        self.assertEqual(self._run_hook(cmd), "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_branch")
        self.assertEqual(entry["severity"], "HIGH")

    def test_heredoc_prose_mentioning_commit_not_flagged(self):
        cmd = ('echo "$(cat <<XEOF\n'
               'you should run git commit -m carefully\n'
               'XEOF\n)"')
        self.assertEqual(self._run_hook(cmd), "allow")


if __name__ == "__main__":
    unittest.main()
