"""`.claude/hooks/protect_agent_model_naming.py` 테스트 - LOW/log-only
(2026-08-15 재분류: deny->ask->deny->log-only. 세션 안에서 3번 등급이
바뀌어온 것 자체가 "이건 원래 막을 정도가 아니었다"는 신호 - 비용 효율
문제라 로그만 남기고 항상 allow)."""
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
import protect_agent_model_naming as hook  # noqa: E402


class TestProtectAgentModelNamingEndToEnd(unittest.TestCase):
    def setUp(self):
        # 실제 .claude/hooks/violations_log.jsonl을 오염시키지 않도록
        # 격리된 로그 경로로 돌린다.
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
        })

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _run_hook(self, tool_input):
        payload = json.dumps({"tool_name": "Agent", "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_missing_model_still_allowed(self):
        decision = self._run_hook({"description": "x", "prompt": "y"})
        self.assertEqual(decision, "allow")

    def test_missing_model_logged(self):
        self._run_hook({"description": "x", "prompt": "y"})
        with open(os.path.join(self._log_dir, "v.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["hook"], "protect_agent_model_naming")
        self.assertEqual(entry["severity"], "LOW")
        self.assertIn("no `model` field", entry["reason"])

    def test_haiku_model_still_allowed(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "haiku"})
        self.assertEqual(decision, "allow")

    def test_haiku_model_logged(self):
        self._run_hook({"description": "x", "prompt": "y", "model": "haiku"})
        with open(os.path.join(self._log_dir, "v.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["severity"], "LOW")
        self.assertIn("haiku", entry["reason"])

    def test_sonnet_model_allowed_and_not_logged(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "sonnet"})
        self.assertEqual(decision, "allow")
        self.assertFalse(os.path.exists(os.path.join(self._log_dir, "v.jsonl")))

    def test_opus_model_allowed_and_not_logged(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "opus"})
        self.assertEqual(decision, "allow")
        self.assertFalse(os.path.exists(os.path.join(self._log_dir, "v.jsonl")))

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
