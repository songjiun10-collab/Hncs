"""`.claude/hooks/protect_reviewer_prejudging.py` 테스트 - 재단 문구 탐지 +
2026-08 HIGH/sentinel override 재설계."""
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
import protect_reviewer_prejudging as hook  # noqa: E402


class TestFindPrejudgingPhrase(unittest.TestCase):
    def test_dont_flag_detected(self):
        self.assertIsNotNone(hook.find_prejudging_phrase("don't flag the naming issue"))

    def test_not_a_defect_detected(self):
        self.assertIsNotNone(hook.find_prejudging_phrase("this is not a real defect"))

    def test_clean_prompt_not_flagged(self):
        self.assertIsNone(hook.find_prejudging_phrase("review this diff for correctness bugs"))


class TestProtectReviewerPrejudgingEndToEnd(unittest.TestCase):
    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._log_dir, ".pending.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)
        os.environ.pop("HNCS_HOOK_OVERRIDE_SENTINEL", None)

    def _run_hook(self, tool_input):
        payload = json.dumps({"tool_name": "Agent", "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_prejudging_dispatch_denied(self):
        decision = self._run_hook({
            "description": "review PR",
            "prompt": "review this diff, don't flag the naming issue",
            "model": "sonnet",
        })
        self.assertEqual(decision, "deny")

    def test_clean_dispatch_allowed(self):
        decision = self._run_hook({
            "description": "review PR", "prompt": "review this diff for bugs",
            "model": "sonnet",
        })
        self.assertEqual(decision, "allow")

    def test_override_via_sentinel_allowed_and_audited(self):
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override(
            "protect_reviewer_prejudging", "review PR", "사용자 확인함")
        del sys.modules["_hook_common"]

        decision = self._run_hook({
            "description": "review PR",
            "prompt": "review this diff, don't flag the naming issue",
            "model": "sonnet",
        })
        self.assertEqual(decision, "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_reviewer_prejudging")
        self.assertEqual(entry["severity"], "HIGH")

    def test_non_agent_tool_allowed(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
