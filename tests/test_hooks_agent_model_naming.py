"""`.claude/hooks/protect_agent_model_naming.py` 테스트 - 2026-08 MID/ask()
재설계(원래는 deny)."""
import json
import subprocess
import sys
import unittest
import os

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks")
sys.path.insert(0, _HOOKS_DIR)
import protect_agent_model_naming as hook  # noqa: E402


class TestProtectAgentModelNamingEndToEnd(unittest.TestCase):
    def _run_hook(self, tool_input):
        payload = json.dumps({"tool_name": "Agent", "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_missing_model_asks(self):
        decision = self._run_hook({"description": "x", "prompt": "y"})
        self.assertEqual(decision, "ask")

    def test_haiku_model_asks(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "haiku"})
        self.assertEqual(decision, "ask")

    def test_sonnet_model_allowed(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "sonnet"})
        self.assertEqual(decision, "allow")

    def test_opus_model_allowed(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "opus"})
        self.assertEqual(decision, "allow")

    def test_non_agent_tool_allowed(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
