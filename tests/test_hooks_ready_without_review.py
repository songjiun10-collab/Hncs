"""`.claude/hooks/protect_ready_without_review.py` 테스트 - 리뷰 sentinel
체크 + 2026-08 HIGH/override 재설계. 실제 git repo가 필요해서(HEAD sha
비교) 임시 repo를 판다."""
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
import protect_ready_without_review as hook  # noqa: E402


class TestProtectReadyWithoutReviewEndToEnd(unittest.TestCase):
    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._log_dir, ".pending.json"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(self._log_dir, ".pending_decision_record.json"),
        })
        # The hook's current_head_sha() runs `git rev-parse HEAD` with
        # cwd=Path(__file__).parent (the real .claude/hooks/ dir) - it
        # doesn't take a repo argument, so tests run against the real repo's
        # actual current HEAD rather than an isolated fixture repo.
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_HOOKS_DIR,
                              capture_output=True, text=True, check=True)
        self._real_head_sha = out.stdout.strip()
        self._sentinel_path = os.path.join(_HOOKS_DIR, ".last_whole_branch_review_sha")
        self._sentinel_existed = os.path.exists(self._sentinel_path)
        if self._sentinel_existed:
            with open(self._sentinel_path, encoding="utf-8") as f:
                self._sentinel_backup = f.read()
        else:
            self._sentinel_backup = None

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)
        os.environ.pop("HNCS_HOOK_OVERRIDE_SENTINEL", None)
        if self._sentinel_backup is not None:
            with open(self._sentinel_path, "w", encoding="utf-8") as f:
                f.write(self._sentinel_backup)
        elif os.path.exists(self._sentinel_path):
            os.remove(self._sentinel_path)

    def _write_decision_record(self, target="x/y#1"):
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env["HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_ready_without_review", "HIGH", 0.7, "테스트 자기평가", "테스트 위험", target=target)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def _run_hook(self, draft, agent_id=None):
        payload = {
            "tool_name": "mcp__github__update_pull_request",
            "tool_input": {"draft": draft, "owner": "x", "repo": "y", "pullNumber": 1},
        }
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=json.dumps(payload), env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_not_a_ready_transition_allowed(self):
        self.assertEqual(self._run_hook(draft=True), "allow")

    def test_ready_with_no_sentinel_asks(self):
        """HIGH tier, direct call: ask(), not deny - see
        _hook_common.py's 2026-08-15 tier redesign note. decision record
        required first (2026-08-16 mandatory gate)."""
        if os.path.exists(self._sentinel_path):
            os.remove(self._sentinel_path)
        self._write_decision_record()
        self.assertEqual(self._run_hook(draft=False), "ask")

    def test_ready_without_decision_record_denied(self):
        """2026-08-16 필수 게이트: decision record 없으면 ask()도 안 뜨고
        무조건 deny."""
        if os.path.exists(self._sentinel_path):
            os.remove(self._sentinel_path)
        self.assertEqual(self._run_hook(draft=False), "deny")

    def test_ready_with_no_sentinel_from_subagent_denied(self):
        if os.path.exists(self._sentinel_path):
            os.remove(self._sentinel_path)
        self._write_decision_record()
        self.assertEqual(self._run_hook(draft=False, agent_id="agt_1"), "deny")

    def test_ready_with_matching_sentinel_allowed(self):
        with open(self._sentinel_path, "w", encoding="utf-8") as f:
            f.write(self._real_head_sha)
        self.assertEqual(self._run_hook(draft=False), "allow")

    def test_ready_with_stale_sentinel_asks(self):
        with open(self._sentinel_path, "w", encoding="utf-8") as f:
            f.write("0" * 40)
        self._write_decision_record()
        self.assertEqual(self._run_hook(draft=False), "ask")

    def test_override_via_sentinel_allowed_and_audited(self):
        if os.path.exists(self._sentinel_path):
            os.remove(self._sentinel_path)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override(
            "protect_ready_without_review", "x/y#1", "사용자 확인함")
        del sys.modules["_hook_common"]
        self._write_decision_record()

        self.assertEqual(self._run_hook(draft=False), "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_ready_without_review")
        self.assertEqual(entry["severity"], "HIGH")


if __name__ == "__main__":
    unittest.main()
