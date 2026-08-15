"""`.claude/hooks/protect_claim_evidence.py` 테스트 - README/CLAUDE.md/
EVALUATION.md에 근거 마커 없는 수치 주장이 추가되면 ask()(MID)로 걸리는지."""
import json
import os
import subprocess
import sys
import unittest

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks")
sys.path.insert(0, _HOOKS_DIR)
import protect_claim_evidence as hook  # noqa: E402


class TestUnbackedClaimReason(unittest.TestCase):
    def test_percent_without_evidence_flagged(self):
        self.assertIsNotNone(hook.unbacked_claim_reason("성능이 +9.12% 개선됨."))

    def test_percent_with_backtick_command_not_flagged(self):
        text = "+9.12% 개선(`python3 -m tests.test_x` 실행 결과)."
        self.assertIsNone(hook.unbacked_claim_reason(text))

    def test_brand_count_without_evidence_flagged(self):
        self.assertIsNotNone(hook.unbacked_claim_reason("이제 15 brands를 지원한다."))

    def test_no_numeric_claim_not_flagged(self):
        self.assertIsNone(hook.unbacked_claim_reason("이 기능은 아직 실험적이다."))

    def test_verified_keyword_counts_as_evidence(self):
        text = "3배 빨라짐(verified against the recorded run)."
        self.assertIsNone(hook.unbacked_claim_reason(text))


class TestIsClaimBearingDoc(unittest.TestCase):
    def test_root_readme_matches(self):
        self.assertTrue(hook.is_claim_bearing_doc("README.md"))

    def test_readme_ko_matches(self):
        self.assertTrue(hook.is_claim_bearing_doc("README.ko.md"))

    def test_nested_claude_md_matches(self):
        self.assertTrue(hook.is_claim_bearing_doc("hybrid_engine/CLAUDE.md"))

    def test_evaluation_md_matches(self):
        self.assertTrue(hook.is_claim_bearing_doc("hybrid_engine/EVALUATION.md"))

    def test_unrelated_file_not_matched(self):
        self.assertFalse(hook.is_claim_bearing_doc("brands/hasselblad.py"))
        self.assertFalse(hook.is_claim_bearing_doc("docs/brands.md"))


class TestProtectClaimEvidenceEndToEnd(unittest.TestCase):
    def _run_hook(self, tool_input):
        payload = json.dumps({"tool_name": "Edit", "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_unbacked_claim_asks(self):
        decision = self._run_hook({
            "file_path": "README.md", "old_string": "old",
            "new_string": "새로 15 brands 지원.",
        })
        self.assertEqual(decision, "ask")

    def test_backed_claim_allowed(self):
        decision = self._run_hook({
            "file_path": "README.md", "old_string": "old",
            "new_string": "15 brands 지원 (`tests/test_brands.py` 확인됨).",
        })
        self.assertEqual(decision, "allow")

    def test_non_scoped_file_allowed(self):
        decision = self._run_hook({
            "file_path": "brands/hasselblad.py", "old_string": "old",
            "new_string": "15% 개선",
        })
        self.assertEqual(decision, "allow")

    def test_non_matching_tool_allowed(self):
        payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
