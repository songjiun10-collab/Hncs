"""`.claude/hooks/protect_hook_integrity.py` 테스트 - .claude/hooks/*.py,
session-start.sh, .claude/settings.json에 대한 Edit/Write/Bash 쓰기가
override 없이 무조건 deny되는지, README.md/CLAUDE.md(문서, 의도적 제외)
는 영향 없는지, 서브에이전트발은 override조차 안 받는지 확인.

**Why (2026-08-20, 사용자 지시)**: README "알려진 한계"가 "훅 스크립트/
설정 자체의 무결성은 이 시스템 어디에도 다뤄지지 않는다"고 기록해둔
공급망 위협 클래스에 대한 대응 - 사용자 승인 후 추가."""
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
import protect_hook_integrity as hook  # noqa: E402


class TestIsProtectedHookPath(unittest.TestCase):
    def test_hook_script_matched(self):
        self.assertTrue(hook.is_protected_hook_path(".claude/hooks/protect_never_touch.py"))

    def test_session_start_matched(self):
        self.assertTrue(hook.is_protected_hook_path(".claude/hooks/session-start.sh"))

    def test_settings_json_matched(self):
        self.assertTrue(hook.is_protected_hook_path(".claude/settings.json"))

    def test_readme_not_matched(self):
        """의도적 제외 - 보고 프로토콜이 README.md를 계속 편집하도록
        요구하는데, 그것까지 게이트에 걸리면 워크플로우가 깨짐."""
        self.assertFalse(hook.is_protected_hook_path(".claude/hooks/README.md"))

    def test_hooks_claude_md_not_matched(self):
        self.assertFalse(hook.is_protected_hook_path(".claude/hooks/CLAUDE.md"))

    def test_test_file_not_matched(self):
        self.assertFalse(hook.is_protected_hook_path("tests/test_hooks_never_touch_bash.py"))

    def test_unrelated_file_not_matched(self):
        self.assertFalse(hook.is_protected_hook_path("tools/foo.py"))


class TestBashWriteTarget(unittest.TestCase):
    def test_redirect_into_hook_script_caught(self):
        self.assertIsNotNone(
            hook.bash_write_target("echo x >> .claude/hooks/protect_never_touch.py"))

    def test_redirect_into_settings_json_caught(self):
        self.assertIsNotNone(
            hook.bash_write_target('echo \'{}\' > .claude/settings.json'))

    def test_sed_inplace_on_hook_script_caught(self):
        self.assertIsNotNone(
            hook.bash_write_target("sed -i 's/deny/allow/' .claude/hooks/protect_destructive.py"))

    def test_python_open_write_on_hook_script_caught(self):
        cmd = "python3 -c \"open('.claude/hooks/protect_branch.py','w').write(x)\""
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_heredoc_fed_directly_to_shell_still_caught(self):
        cmd = "python3 - <<'PY'\nopen(\".claude/hooks/protect_branch.py\",\"w\").write(\"x\")\nPY"
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_adjacent_literal_concat_caught(self):
        cmd = "python3 -c \"open('.claude/hooks/protect''_branch.py','w').write('x')\""
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_multihop_variable_indirection_caught(self):
        cmd = ("python3 -c \"p='.claude/hooks/protect_branch.py'; q=p; "
               "open(q,'w').write('x')\"")
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_eval_wrapped_write_caught(self):
        cmd = 'eval "echo x >> .claude/hooks/protect_never_touch.py"'
        self.assertIsNotNone(hook.bash_write_target(cmd))

    def test_readme_write_not_caught(self):
        self.assertIsNone(
            hook.bash_write_target("echo x >> .claude/hooks/README.md"))

    def test_cat_hook_script_not_flagged(self):
        self.assertIsNone(hook.bash_write_target("cat .claude/hooks/protect_never_touch.py"))

    def test_unrelated_command_not_flagged(self):
        self.assertIsNone(hook.bash_write_target("git status"))


class TestMainEndToEnd(unittest.TestCase):
    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._log_dir, ".pending.json"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(self._log_dir, ".pending_decision_record.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _write_decision_record(self, target):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env["HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_hook_integrity", "CRITICAL", 0.9, "테스트 자기평가", "테스트 위험", target=target)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def _run_hook(self, tool_name, tool_input, agent_id=None):
        payload = {"tool_name": tool_name, "tool_input": tool_input}
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=json.dumps(payload), env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_edit_hook_script_denied(self):
        target = ".claude/hooks/protect_never_touch.py"
        self._write_decision_record(target)
        decision = self._run_hook("Edit", {
            "file_path": target, "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "deny")

    def test_edit_without_decision_record_denied(self):
        decision = self._run_hook("Edit", {
            "file_path": ".claude/hooks/protect_never_touch.py",
            "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "deny")

    def test_write_settings_json_denied(self):
        target = ".claude/settings.json"
        self._write_decision_record(target)
        decision = self._run_hook("Write", {"file_path": target, "content": "{}"})
        self.assertEqual(decision, "deny")

    def test_edit_readme_allowed(self):
        decision = self._run_hook("Edit", {
            "file_path": ".claude/hooks/README.md", "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "allow")

    def test_edit_unrelated_file_allowed(self):
        decision = self._run_hook("Edit", {
            "file_path": "tools/foo.py", "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "allow")

    def test_subagent_edit_denied_even_with_valid_override(self):
        target = ".claude/hooks/protect_never_touch.py"
        self._write_decision_record(target)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override("protect_hook_integrity", target, "사용자 확인함")
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_OVERRIDE_SENTINEL", None)
        decision = self._run_hook("Edit", {
            "file_path": target, "old_string": "a", "new_string": "b",
        }, agent_id="agt_1")
        self.assertEqual(decision, "deny")

    def test_override_allows_and_audited(self):
        target = ".claude/hooks/protect_never_touch.py"
        self._write_decision_record(target)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override("protect_hook_integrity", target, "사용자 확인함")
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_OVERRIDE_SENTINEL", None)
        decision = self._run_hook("Edit", {
            "file_path": target, "old_string": "a", "new_string": "b",
        })
        self.assertEqual(decision, "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_hook_integrity")
        self.assertEqual(entry["severity"], "CRITICAL")

    def test_bash_write_to_hook_script_denied(self):
        target = ".claude/hooks/protect_never_touch.py"
        self._write_decision_record(target)
        decision = self._run_hook("Bash", {
            "command": f"echo x >> {target}",
        })
        self.assertEqual(decision, "deny")

    def test_bash_unrelated_command_allowed(self):
        decision = self._run_hook("Bash", {"command": "git status"})
        self.assertEqual(decision, "allow")

    def test_non_matching_tool_allowed(self):
        decision = self._run_hook("Read", {"file_path": ".claude/hooks/protect_never_touch.py"})
        self.assertEqual(decision, "allow")


if __name__ == "__main__":
    unittest.main()
