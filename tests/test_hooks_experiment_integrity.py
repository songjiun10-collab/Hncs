"""`.claude/hooks/protect_experiment_integrity.py` 테스트 - EVALUATION.md에
CI/bootstrap 언급 없이 수치 결과(%/ΔE)만 추가하면 걸리는지, sentinel
override로 뚫리는지."""
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
import protect_experiment_integrity as hook  # noqa: E402


class TestMissingCiReason(unittest.TestCase):
    def test_percent_claim_without_ci_flagged(self):
        text = "개선폭 +9.12%, 학습 LUT 우세."
        self.assertIsNotNone(hook.missing_ci_reason(text))

    def test_percent_claim_with_ci_not_flagged(self):
        text = "개선폭 +9.12%, 부트스트랩 95% CI [+0.689, +2.341] - 학습 LUT 우세."
        self.assertIsNone(hook.missing_ci_reason(text))

    def test_delta_e_claim_without_ci_flagged(self):
        text = "ΔE00 2.78로 개선됨."
        self.assertIsNotNone(hook.missing_ci_reason(text))

    def test_prose_with_no_numeric_result_not_flagged(self):
        text = "이 실험은 아직 진행 중이고 결론은 다음 세션에서 다룬다."
        self.assertIsNone(hook.missing_ci_reason(text))

    def test_english_confidence_interval_recognized(self):
        text = "improvement +5%, 95% confidence interval [1, 9]."
        self.assertIsNone(hook.missing_ci_reason(text))


class TestProtectExperimentIntegrityEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._tmpdir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._tmpdir, "o.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._tmpdir, ".pending.json"),
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
            "protect_experiment_integrity", "HIGH", 0.7, "테스트 자기평가", "테스트 위험", target=target)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def _run_hook(self, tool_input, agent_id=None):
        payload = {"tool_name": "Edit", "tool_input": tool_input}
        if agent_id:
            payload["agent_id"] = agent_id
            payload["agent_type"] = "general-purpose"
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=json.dumps(payload), env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_result_without_ci_asks(self):
        """HIGH tier, direct call: ask(), not deny - see
        _hook_common.py's 2026-08-15 tier redesign note. decision record
        required first (2026-08-16 mandatory gate)."""
        self._write_decision_record("hybrid_engine/EVALUATION.md")
        decision = self._run_hook({
            "file_path": "hybrid_engine/EVALUATION.md",
            "old_string": "old", "new_string": "개선폭 +9.12%, 우세.",
        })
        self.assertEqual(decision, "ask")

    def test_result_without_decision_record_denied(self):
        """2026-08-16 필수 게이트: decision record 없으면 ask()도 안 뜨고
        무조건 deny."""
        decision = self._run_hook({
            "file_path": "hybrid_engine/EVALUATION.md",
            "old_string": "old", "new_string": "개선폭 +9.12%, 우세.",
        })
        self.assertEqual(decision, "deny")

    def test_result_without_ci_from_subagent_denied(self):
        decision = self._run_hook({
            "file_path": "hybrid_engine/EVALUATION.md",
            "old_string": "old", "new_string": "개선폭 +9.12%, 우세.",
        }, agent_id="agt_1")
        self.assertEqual(decision, "deny")

    def test_result_with_ci_allowed(self):
        decision = self._run_hook({
            "file_path": "hybrid_engine/EVALUATION.md",
            "old_string": "old",
            "new_string": "개선폭 +9.12%, 부트스트랩 95% CI [+0.6, +2.3].",
        })
        self.assertEqual(decision, "allow")

    def test_non_evaluation_file_allowed(self):
        decision = self._run_hook({
            "file_path": "README.md",
            "old_string": "old", "new_string": "개선폭 +9.12%",
        })
        self.assertEqual(decision, "allow")

    def test_override_via_sentinel_allowed_and_audited(self):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override(
            "protect_experiment_integrity", "hybrid_engine/EVALUATION.md", "정정 블록쿼트일 뿐")
        del sys.modules["_hook_common"]
        self._write_decision_record("hybrid_engine/EVALUATION.md")

        decision = self._run_hook({
            "file_path": "hybrid_engine/EVALUATION.md",
            "old_string": "old", "new_string": "개선폭 +9.12%, 우세.",
        })
        self.assertEqual(decision, "allow")
        with open(os.path.join(self._tmpdir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_experiment_integrity")
        self.assertEqual(entry["severity"], "HIGH")


if __name__ == "__main__":
    unittest.main()
