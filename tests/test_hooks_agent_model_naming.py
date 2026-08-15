"""`.claude/hooks/protect_agent_model_naming.py` 테스트 - deny(MID)+sentinel
override(2026-08-15 정정: 원래 ask()였다가 subagent 테스트로 fail-open
발견 후 deny+override로 되돌림 - protect_generated_files.py/
protect_claim_evidence.py와 같은 사유)."""
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
        # 실제 .claude/hooks/violations_log.jsonl/override_audit.jsonl을
        # 오염시키지 않도록 모든 subprocess 호출을 격리된 로그 경로로
        # 돌린다(이전에 이 파일의 _run_hook이 env를 안 넘겨서 실제 로그를
        # 오염시켰던 버그를 정정).
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._log_dir, ".pending.json"),
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

    def test_missing_model_denied(self):
        decision = self._run_hook({"description": "x", "prompt": "y"})
        self.assertEqual(decision, "deny")

    def test_haiku_model_denied(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "haiku"})
        self.assertEqual(decision, "deny")

    def test_sonnet_model_allowed(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "sonnet"})
        self.assertEqual(decision, "allow")

    def test_opus_model_allowed(self):
        decision = self._run_hook({"description": "x", "prompt": "y", "model": "opus"})
        self.assertEqual(decision, "allow")

    def test_non_agent_tool_allowed(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_override_via_sentinel_allowed_and_audited(self):
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override(
            "protect_agent_model_naming", "test dispatch", "사용자 확인함")
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_OVERRIDE_SENTINEL", None)

        decision = self._run_hook({"description": "test dispatch", "prompt": "y"})
        self.assertEqual(decision, "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_agent_model_naming")
        self.assertEqual(entry["severity"], "MID")


if __name__ == "__main__":
    unittest.main()
