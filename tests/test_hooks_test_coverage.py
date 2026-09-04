"""`.claude/hooks/protect_test_coverage.py` 테스트 - 새 소스 파일을 테스트
없이 커밋하려 할 때 걸리는지, 기존 파일 수정/제외 디렉토리/override는
통과하는지 실제 임시 git repo의 staged 상태로 확인."""
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
import protect_test_coverage as hook  # noqa: E402


class TestProtectTestCoverageEndToEnd(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._log_dir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._log_dir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._log_dir, "o.jsonl"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(self._log_dir, ".pending_decision_record.json"),
        })
        self._run("git", "init", "-q")
        self._run("git", "config", "user.email", "x@example.com")
        self._run("git", "config", "user.name", "x")
        for d in ("tools", "brands", "core", "hybrid_engine", "hybrid_engine/research", "tests"):
            os.makedirs(os.path.join(self.repo, d), exist_ok=True)
        self._write("README.md", "x")
        self._run("git", "add", "README.md")
        self._run("git", "commit", "-q", "-m", "init")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(args, cwd=self.repo, capture_output=True,
                               text=True, check=True)

    def _write(self, rel_path, content):
        with open(os.path.join(self.repo, rel_path), "w") as f:
            f.write(content)

    def _write_decision_record(self, target):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env["HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_test_coverage", "HIGH", 0.7, "테스트 자기평가", "테스트 위험", target=target)
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

    def test_new_tools_file_without_test_asks(self):
        """HIGH tier, direct call: ask(), not deny - see
        _hook_common.py's 2026-08-15 tier redesign note. decision record
        required first (2026-08-16 mandatory gate)."""
        self._write("tools/new_thing.py", "x = 1\n")
        self._run("git", "add", "tools/new_thing.py")
        self._write_decision_record("tools/new_thing.py")
        self.assertEqual(self._run_hook('git commit -m "add"'), "ask")

    def test_new_tools_file_without_test_from_subagent_denied(self):
        self._write("tools/new_thing.py", "x = 1\n")
        self._run("git", "add", "tools/new_thing.py")
        self._write_decision_record("tools/new_thing.py")
        self.assertEqual(
            self._run_hook('git commit -m "add"', agent_id="agt_1"), "deny")

    def test_new_tools_file_without_decision_record_denied(self):
        """2026-08-16 필수 게이트: decision record 없으면 ask()도 안 띄고
        무조건 deny."""
        self._write("tools/new_thing.py", "x = 1\n")
        self._run("git", "add", "tools/new_thing.py")
        self.assertEqual(self._run_hook('git commit -m "add"'), "deny")

    def test_new_tools_file_with_test_allowed(self):
        self._write("tools/new_thing.py", "x = 1\n")
        self._write("tests/test_new_thing.py", "x = 1\n")
        self._run("git", "add", "tools/new_thing.py", "tests/test_new_thing.py")
        self.assertEqual(self._run_hook('git commit -m "add"'), "allow")

    def test_new_research_file_excluded(self):
        self._write("hybrid_engine/research/scratch.py", "x = 1\n")
        self._run("git", "add", "hybrid_engine/research/scratch.py")
        self.assertEqual(self._run_hook('git commit -m "add"'), "allow")

    def test_new_calibrate_profile_copy_excluded(self):
        self._write("hybrid_engine/calibrate_profile_newbrand.py", "x = 1\n")
        self._run("git", "add", "hybrid_engine/calibrate_profile_newbrand.py")
        self.assertEqual(self._run_hook('git commit -m "add"'), "allow")

    def test_modifying_existing_file_not_flagged(self):
        self._write("tools/existing.py", "x = 1\n")
        self._run("git", "add", "tools/existing.py")
        self._run("git", "commit", "-q", "-m", "add existing")
        self._write("tools/existing.py", "x = 2\n")
        self._run("git", "add", "tools/existing.py")
        self.assertEqual(self._run_hook('git commit -m "modify"'), "allow")

    def test_new_docs_file_not_flagged(self):
        self._write("docs_readme.md", "x")
        self._run("git", "add", "docs_readme.md")
        self.assertEqual(self._run_hook('git commit -m "add doc"'), "allow")

    def test_non_commit_command_allowed(self):
        self.assertEqual(self._run_hook("git status"), "allow")

    def test_override_allows_and_audited(self):
        self._write("tools/scratch_oneoff.py", "x = 1\n")
        self._run("git", "add", "tools/scratch_oneoff.py")
        self._write_decision_record("tools/scratch_oneoff.py")
        cmd = 'git commit -m "add"  # HNCS-OVERRIDE: protect_test_coverage: 일회성 스크립트'
        self.assertEqual(self._run_hook(cmd), "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_test_coverage")
        self.assertEqual(entry["severity"], "HIGH")

    def test_eval_wrapped_commit_still_asks(self):
        """2026-08-20 정정 (README 2차 라운드 #4, 실증): eval "git commit
        ..."가 _STMT_START 요건을 못 맞춰서 완전히 안 걸렸다."""
        self._write("tools/new_thing.py", "x = 1\n")
        self._run("git", "add", "tools/new_thing.py")
        self._write_decision_record("tools/new_thing.py")
        self.assertEqual(self._run_hook('eval "git commit -m add"'), "ask")


if __name__ == "__main__":
    unittest.main()
