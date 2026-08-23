"""`.claude/hooks/protect_claim_evidence.py` 테스트 - README/CLAUDE.md/
EVALUATION.md에 근거 마커 없는 수치 주장이 추가되면 deny(MID)+sentinel
override로 걸리는지(원래 ask()였다가 subagent 테스트로 fail-open
발견 후 deny+override로 정정됨)."""
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

    def test_word_ending_in_log_is_not_evidence(self):
        """2026-08-20 정정 (README 2차 라운드 #9, 실증 2026-08-19): 원래
        `log\\b`에 앞쪽 경계가 없어서 "catalog"/"backlog" 같은 무관한
        단어에도 매칭됐다."""
        text = "성능이 15% 향상되었다 (see catalog)"
        self.assertIsNotNone(hook.unbacked_claim_reason(text))

    def test_nonexistent_md_file_mention_is_not_evidence(self):
        """2026-08-20 정정 (README 7차 라운드): .py/.md 마커가 그 파일이
        실제로 존재하는지 전혀 확인 안 해서, 존재하지 않는 파일 언급도
        근거로 통과했다."""
        text = "성능이 40% 향상되었다 (see nonexistent_totally_made_up_file.md)"
        self.assertIsNotNone(hook.unbacked_claim_reason(text))

    def test_existing_file_mention_counts_as_evidence(self):
        text = "이 프로젝트는 tests/CLAUDE.md 관련 15개 규칙을 따른다."
        self.assertIsNone(hook.unbacked_claim_reason(text))

    def test_unrelated_sentence_does_not_vouch_for_unbacked_claim(self):
        """2026-08-20 정정 (README 8차 라운드 #10, 실증): 주장-근거 짝짓기가
        "편집 텍스트 전체 어딘가"라서, 완전히 무관한 다른 문장의 진짜
        근거가 이 무근거 주장까지 무임승차시켰다 - 같은 문장으로 좁힘."""
        text = ("이 브랜드는 200% 더 빠르다. "
                "별개로 15개 프리셋을 지원한다(`ls presets/ | wc -l`로 확인).")
        reason = hook.unbacked_claim_reason(text)
        self.assertIsNotNone(reason)
        self.assertIn("200%", reason)

    def test_backtick_content_must_look_like_a_command_or_path(self):
        """2026-08-20 정정 (README 8차 라운드 #11, 실증): backtick 안
        내용을 전혀 검증 안 해서, 자기모순 텍스트도 근거로 통과했다."""
        text = "성능이 300% 향상되었다 (`거짓말임`)."
        self.assertIsNotNone(hook.unbacked_claim_reason(text))

    def test_backtick_with_path_shape_still_counts(self):
        text = "성능이 300% 향상되었다 (`tools/bench.py` 참고)."
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
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(self._log_dir, ".pending_decision_record.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)

    def _write_decision_record(self, target):
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env["HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_claim_evidence", "MEDIUM", 0.6, "테스트 자기평가", "테스트 위험", target=target)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def _run_hook(self, tool_input):
        payload = json.dumps({"tool_name": "Edit", "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_unbacked_claim_denied(self):
        decision = self._run_hook({
            "file_path": "README.md", "old_string": "old",
            "new_string": "새로 15 brands 지원.",
        })
        self.assertEqual(decision, "deny")

    def test_plain_sentinel_override_no_longer_works(self):
        """2026-08-16 정정: "그 애매한 중간단계?" - plain override가
        MEDIUM-APPROVE와 나란히 있으면 항상 더 쉬운 쪽만 쓰이니 plain
        override를 제거했다. sentinel을 심어놔도 이제 안 먹혀야 함."""
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_OVERRIDE_SENTINEL"] = self._env["HNCS_HOOK_OVERRIDE_SENTINEL"]
        import _hook_common
        _hook_common.write_sentinel_override(
            "protect_claim_evidence", "README.md", "사용자 확인함")
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_OVERRIDE_SENTINEL", None)

        decision = self._run_hook({
            "file_path": "README.md", "old_string": "old",
            "new_string": "새로 15 brands 지원.",
        })
        self.assertEqual(decision, "deny")

    def test_medium_approval_still_allows_and_audited(self):
        """MEDIUM-APPROVE(opus 디스패치 전용)만 유효한 통과 경로.
        decision record도 먼저 있어야 함(2026-08-16 필수 게이트)."""
        sys.modules.pop("_hook_common", None)
        for k, v in self._env.items():
            if k.startswith("HNCS_HOOK_"):
                os.environ[k] = v
        os.environ["HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"] = os.path.join(
            self._log_dir, ".pending_medium_approval.json")
        import _hook_common
        _hook_common.write_medium_approval(
            "protect_claim_evidence", "README.md", "opus가 승인함")
        _hook_common.write_decision_record(
            "protect_claim_evidence", "MEDIUM", 0.6, "테스트 자기평가", "테스트 위험",
            target="README.md")
        del sys.modules["_hook_common"]
        self._env["HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"] = os.environ.pop(
            "HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL")
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

        decision = self._run_hook({
            "file_path": "README.md", "old_string": "old",
            "new_string": "새로 15 brands 지원.",
        })
        self.assertEqual(decision, "allow")
        with open(os.path.join(self._log_dir, "o.jsonl"), encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["rule"], "protect_claim_evidence")
        self.assertEqual(entry["severity"], "MEDIUM")

    def test_medium_approval_without_decision_record_denied(self):
        """2026-08-16 필수 게이트: 유효한 MEDIUM-APPROVE가 있어도 decision
        record 없으면 무조건 deny."""
        sys.modules.pop("_hook_common", None)
        for k, v in self._env.items():
            if k.startswith("HNCS_HOOK_"):
                os.environ[k] = v
        os.environ["HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"] = os.path.join(
            self._log_dir, ".pending_medium_approval.json")
        import _hook_common
        _hook_common.write_medium_approval(
            "protect_claim_evidence", "README.md", "opus가 승인함")
        del sys.modules["_hook_common"]
        self._env["HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"] = os.environ.pop(
            "HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL")

        decision = self._run_hook({
            "file_path": "README.md", "old_string": "old",
            "new_string": "새로 15 brands 지원.",
        })
        self.assertEqual(decision, "deny")

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
            [sys.executable, hook.__file__], input=payload, env=self._env,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
