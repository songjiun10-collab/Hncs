"""`.claude/hooks/_hook_common.py`의 심각도/override 메커니즘 테스트 -
순수 함수 단위(bash_override/sentinel_override/write_sentinel_override)와
`protect_never_touch.py`(CRITICAL 등급으로 재설계된 첫 훅)를 통한 end-to
-end 둘 다 검증. 감사로그(violations_log.jsonl/override_audit.jsonl)가
테스트 중 실제 git-tracked 파일을 오염시키지 않도록 매 테스트마다
HNCS_HOOK_* 환경변수로 임시 경로에 리다이렉트한다(테스트 실행이 실제
override 감사 기록을 남기면 안 됨 - 그 자체가 로그의 신뢰성을 해친다)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks")
sys.path.insert(0, _HOOKS_DIR)


class TestBashOverrideParsing(unittest.TestCase):
    def setUp(self):
        import _hook_common
        self.hc = _hook_common

    def test_matching_rule_and_reason_returns_reason(self):
        cmd = 'echo x >> brands/hasselblad.py  # HNCS-OVERRIDE: protect_never_touch: 사용자 승인, 리팩토링'
        self.assertEqual(
            self.hc.bash_override("protect_never_touch", cmd),
            "사용자 승인, 리팩토링")

    def test_wrong_rule_name_returns_none(self):
        cmd = 'echo x >> brands/hasselblad.py  # HNCS-OVERRIDE: some_other_rule: 사유'
        self.assertIsNone(self.hc.bash_override("protect_never_touch", cmd))

    def test_empty_reason_returns_none(self):
        cmd = 'echo x  # HNCS-OVERRIDE: protect_never_touch:   '
        self.assertIsNone(self.hc.bash_override("protect_never_touch", cmd))

    def test_no_marker_at_all_returns_none(self):
        self.assertIsNone(self.hc.bash_override("protect_never_touch", "git status"))


class TestIsSubagentCall(unittest.TestCase):
    def setUp(self):
        import _hook_common
        self.hc = _hook_common

    def test_agent_id_present_is_subagent(self):
        self.assertTrue(self.hc.is_subagent_call(
            {"agent_id": "agt_1", "agent_type": "general-purpose"}))

    def test_agent_id_absent_is_not_subagent(self):
        self.assertFalse(self.hc.is_subagent_call({"tool_name": "Bash"}))


class TestSentinelOverride(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._sentinel_path = os.path.join(self._tmpdir, ".pending_override.json")
        self._env_patch = {
            "HNCS_HOOK_OVERRIDE_SENTINEL": self._sentinel_path,
        }
        self._old_env = {k: os.environ.get(k) for k in self._env_patch}
        os.environ.update(self._env_patch)
        # _hook_common reads env vars at import time - force a fresh import
        # per test so the sentinel path patch actually takes effect.
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        for k, v in self._old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_fresh_matching_sentinel_returns_reason_and_is_consumed(self):
        self.hc.write_sentinel_override("protect_never_touch", "brands/x.py", "승인됨")
        reason = self.hc.sentinel_override("protect_never_touch", "brands/x.py")
        self.assertEqual(reason, "승인됨")
        self.assertFalse(os.path.exists(self._sentinel_path), "1회성 소비 - 재사용 방지")

    def test_second_check_after_consumption_returns_none(self):
        self.hc.write_sentinel_override("protect_never_touch", "brands/x.py", "승인됨")
        self.hc.sentinel_override("protect_never_touch", "brands/x.py")
        self.assertIsNone(self.hc.sentinel_override("protect_never_touch", "brands/x.py"))

    def test_mismatched_target_returns_none(self):
        self.hc.write_sentinel_override("protect_never_touch", "brands/x.py", "승인됨")
        self.assertIsNone(self.hc.sentinel_override("protect_never_touch", "brands/OTHER.py"))

    def test_mismatched_rule_returns_none(self):
        self.hc.write_sentinel_override("protect_never_touch", "brands/x.py", "승인됨")
        self.assertIsNone(self.hc.sentinel_override("some_other_rule", "brands/x.py"))

    def test_expired_sentinel_returns_none(self):
        with open(self._sentinel_path, "w", encoding="utf-8") as f:
            json.dump({"rule": "protect_never_touch", "target": "brands/x.py",
                       "reason": "오래된 승인", "timestamp": time.time() - 700}, f)
        self.assertIsNone(self.hc.sentinel_override("protect_never_touch", "brands/x.py"))

    def test_no_sentinel_file_returns_none(self):
        self.assertIsNone(self.hc.sentinel_override("protect_never_touch", "brands/x.py"))

    def test_empty_reason_in_sentinel_returns_none(self):
        self.hc.write_sentinel_override("protect_never_touch", "brands/x.py", "")
        self.assertIsNone(self.hc.sentinel_override("protect_never_touch", "brands/x.py"))


class TestProtectNeverTouchOverrideEndToEnd(unittest.TestCase):
    """protect_never_touch.py를 subprocess로 실제 실행해서, override 있을 때
    allow, 없거나 무효할 때 deny까지 전체 stdin/stdout 계약을 확인."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._tmpdir, "violations.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._tmpdir, "override_audit.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._tmpdir, ".pending_override.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run_hook(self, tool_name, tool_input, agent_id=None):
        payload = {"tool_name": tool_name, "tool_input": tool_input}
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "protect_never_touch.py")],
            input=json.dumps(payload), env=self._env, capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_bash_write_without_override_denied(self):
        decision = self._run_hook(
            "Bash", {"command": "sed -i 's/x/y/' brands/hasselblad.py"})
        self.assertEqual(decision, "deny")

    def test_bash_write_with_valid_override_allowed(self):
        cmd = ("sed -i 's/x/y/' brands/hasselblad.py"
               "  # HNCS-OVERRIDE: protect_never_touch: 테스트 승인 사유")
        decision = self._run_hook("Bash", {"command": cmd})
        self.assertEqual(decision, "allow")
        audit_path = os.path.join(self._tmpdir, "override_audit.jsonl")
        self.assertTrue(os.path.exists(audit_path))
        with open(audit_path, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_never_touch")
        self.assertEqual(entry["severity"], "CRITICAL")
        self.assertEqual(entry["reason"], "테스트 승인 사유")
        self.assertIsNotNone(entry["git_sha"])

    def test_bash_write_with_wrong_rule_override_still_denied(self):
        cmd = ("sed -i 's/x/y/' brands/hasselblad.py"
               "  # HNCS-OVERRIDE: some_other_rule: 사유")
        decision = self._run_hook("Bash", {"command": cmd})
        self.assertEqual(decision, "deny")

    def test_edit_without_sentinel_denied(self):
        decision = self._run_hook("Edit", {
            "file_path": "brands/sony_a7rvi_learned.py",
            "old_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=1.25):",
            "new_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=2.0):",
        })
        self.assertEqual(decision, "deny")

    def test_edit_with_valid_sentinel_allowed_and_consumed(self):
        target = "brands/sony_a7rvi_learned.py"
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override("protect_never_touch", target, "테스트 승인")
        del sys.modules["_hook_common"]

        decision = self._run_hook("Edit", {
            "file_path": target,
            "old_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=1.25):",
            "new_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=2.0):",
        })
        self.assertEqual(decision, "allow")
        self.assertFalse(os.path.exists(self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]))

        # second attempt without a fresh sentinel must be denied again
        decision2 = self._run_hook("Edit", {
            "file_path": target,
            "old_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=1.25):",
            "new_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=3.0):",
        })
        self.assertEqual(decision2, "deny")

    def test_profile_asset_without_override_still_denied(self):
        decision = self._run_hook("Write", {
            "file_path": "hybrid_engine/assets/profiles/hasselblad.json",
            "content": "{}",
        })
        self.assertEqual(decision, "deny")

    def test_subagent_edit_denied_even_with_valid_sentinel(self):
        """CRITICAL 등급: 서브에이전트발 호출은 sentinel override조차 안
        받는다(2026-08-15) - self-servable 문제가 가장 치명적인 등급이라
        서브에이전트 경로 자체를 override 불가로 막았다."""
        target = "brands/sony_a7rvi_learned.py"
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override("protect_never_touch", target, "테스트 승인")
        del sys.modules["_hook_common"]

        decision = self._run_hook("Edit", {
            "file_path": target,
            "old_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=1.25):",
            "new_string": "def apply_sony_a7rvi_learned(img_bgr, clahe_clip=2.0):",
        }, agent_id="agt_1")
        self.assertEqual(decision, "deny")


if __name__ == "__main__":
    unittest.main()
