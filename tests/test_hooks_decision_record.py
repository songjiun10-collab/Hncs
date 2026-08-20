"""Decision Record 파이프라인(2026-08-16) 테스트 - `_hook_common.py`의
`write_decision_record()`/`decision_record()` 순수 함수 계약, 그
결과가 `deny()`/`ask()`/`log_and_allow()`/`allow_with_override()`/
`allow_with_medium_approval()`을 거쳐 로그 항목에 실제로 붙는지(그리고
decision record가 없을 때는 기존과 완전히 같은 모양으로 남는지),
`allow_with_override()`가 `_log_event()`/`_record_override()`에 조회를
한 번만 공유한다는 것(두 번 조회하면 1회성 sentinel이 첫 호출에서
소비돼 두 번째 로그는 항상 못 붙는다), 그리고 deny -> override 재시도
사이에 새 decision record를 안 쓰면 override 쪽엔 안 붙는다는 알려진
한계를 검증한다. 로그/sentinel 파일이 실제 git-tracked 파일을 오염시키지
않도록 매 테스트마다 HNCS_HOOK_* 환경변수로 격리한다."""
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


class TestDecisionRecordSentinel(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, ".pending_decision_record.json")
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._path
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_fresh_matching_by_target_returns_record_and_is_consumed(self):
        self.hc.write_decision_record(
            "protect_generated_files", "MEDIUM", 0.8, "reason x", "risk x",
            target="brands/x.py")
        record = self.hc.decision_record("protect_generated_files", target="brands/x.py")
        self.assertEqual(record["severity"], "MEDIUM")
        self.assertEqual(record["confidence"], 0.8)
        self.assertFalse(os.path.exists(self._path))

    def test_fresh_matching_by_decision_id_returns_record(self):
        self.hc.write_decision_record(
            "protect_agent_model_naming", "LOW", 0.3, "reason x", "risk x",
            decision_id="slug-1")
        record = self.hc.decision_record("protect_agent_model_naming", decision_id="slug-1")
        self.assertEqual(record["decision_id"], "slug-1")

    def test_mismatched_rule_returns_none(self):
        self.hc.write_decision_record(
            "protect_generated_files", "MEDIUM", 0.8, "r", "e", target="brands/x.py")
        self.assertIsNone(self.hc.decision_record("some_other_rule", target="brands/x.py"))

    def test_mismatched_target_returns_none(self):
        self.hc.write_decision_record(
            "protect_generated_files", "MEDIUM", 0.8, "r", "e", target="brands/x.py")
        self.assertIsNone(self.hc.decision_record("protect_generated_files", target="brands/OTHER.py"))

    def test_mismatched_decision_id_returns_none(self):
        self.hc.write_decision_record(
            "protect_agent_model_naming", "LOW", 0.3, "r", "e", decision_id="slug-1")
        self.assertIsNone(self.hc.decision_record("protect_agent_model_naming", decision_id="slug-2"))

    def test_expired_record_returns_none(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"rule": "protect_generated_files", "target": "brands/x.py",
                       "decision_id": None, "severity": "MEDIUM", "confidence": 0.8,
                       "reason": "r", "expected_risk": "e",
                       "timestamp": time.time() - 700}, f)
        self.assertIsNone(self.hc.decision_record("protect_generated_files", target="brands/x.py"))

    def test_no_record_file_returns_none(self):
        self.assertIsNone(self.hc.decision_record("protect_generated_files", target="brands/x.py"))

    def test_no_target_or_decision_id_returns_none_without_touching_file(self):
        self.hc.write_decision_record(
            "protect_generated_files", "MEDIUM", 0.8, "r", "e", target="brands/x.py")
        self.assertIsNone(self.hc.decision_record("protect_generated_files"))
        # 조회 자체가 target/decision_id 없이는 시도조차 안 하므로 소비되지 않음
        self.assertTrue(os.path.exists(self._path))

    def test_write_requires_target_or_decision_id(self):
        with self.assertRaises(ValueError):
            self.hc.write_decision_record(
                "protect_generated_files", "MEDIUM", 0.8, "r", "e")

    def test_write_rejects_confidence_out_of_range(self):
        with self.assertRaises(ValueError):
            self.hc.write_decision_record(
                "protect_generated_files", "MEDIUM", 1.5, "r", "e", target="x")
        with self.assertRaises(ValueError):
            self.hc.write_decision_record(
                "protect_generated_files", "MEDIUM", -0.1, "r", "e", target="x")

    def test_write_rejects_non_numeric_confidence(self):
        with self.assertRaises(ValueError):
            self.hc.write_decision_record(
                "protect_generated_files", "MEDIUM", "high", "r", "e", target="x")

    def test_intended_scope_and_deviation_round_trip(self):
        """2026-08-19 스키마 확장: 쓸 때 넘긴 intended_scope/deviation이
        그대로 조회 결과에 담겨 나오는지."""
        self.hc.write_decision_record(
            "protect_branch", "HIGH", 0.7, "r", "e", target="feature-x",
            intended_scope="feature-x 브랜치에서만 커밋", deviation="범위 안 - 이탈 없음")
        record = self.hc.decision_record("protect_branch", target="feature-x")
        self.assertEqual(record["intended_scope"], "feature-x 브랜치에서만 커밋")
        self.assertEqual(record["deviation"], "범위 안 - 이탈 없음")

    def test_intended_scope_and_deviation_default_to_none(self):
        self.hc.write_decision_record(
            "protect_branch", "HIGH", 0.7, "r", "e", target="feature-x")
        record = self.hc.decision_record("protect_branch", target="feature-x")
        self.assertIsNone(record["intended_scope"])
        self.assertIsNone(record["deviation"])


class TestLogEventDecisionEnrichment(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        os.environ["HNCS_HOOK_VIOLATIONS_LOG"] = os.path.join(self._tmpdir, "v.jsonl")
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = os.path.join(
            self._tmpdir, ".pending_decision_record.json")
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        for k in ("HNCS_HOOK_VIOLATIONS_LOG", "HNCS_HOOK_DECISION_RECORD_SENTINEL"):
            os.environ.pop(k, None)
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _last_log_entry(self):
        with open(os.environ["HNCS_HOOK_VIOLATIONS_LOG"], encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        return lines[-1]

    def test_deny_without_decision_record_has_no_decision_key(self):
        """하위 호환: decision record가 없으면 기존과 완전히 같은 모양."""
        self.hc.deny("some_hook", "reason", severity="HIGH", target="x.py")
        entry = self._last_log_entry()
        self.assertNotIn("decision", entry)
        self.assertEqual(entry["decision_kind"], "deny")
        self.assertEqual(entry["target"], "x.py")

    def test_deny_with_matching_decision_record_attaches_it(self):
        self.hc.write_decision_record(
            "some_hook", "HIGH", 0.9, "내 판단", "위험 설명", target="x.py")
        self.hc.deny("some_hook", "reason", severity="HIGH", target="x.py")
        entry = self._last_log_entry()
        self.assertEqual(entry["decision"], {
            "self_severity": "HIGH", "confidence": 0.9,
            "reason": "내 판단", "expected_risk": "위험 설명",
        })

    def test_ask_with_matching_decision_record_attaches_it(self):
        self.hc.write_decision_record(
            "some_hook", "HIGH", 0.5, "r", "e", target="x.py")
        self.hc.ask("some_hook", "HIGH", "reason", target="x.py")
        entry = self._last_log_entry()
        self.assertEqual(entry["decision_kind"], "ask")
        self.assertEqual(entry["decision"]["confidence"], 0.5)

    def test_log_and_allow_with_matching_decision_record_attaches_it(self):
        self.hc.write_decision_record(
            "some_hook", "LOW", 0.2, "r", "e", decision_id="slug-1")
        self.hc.log_and_allow("some_hook", "LOW", "reason", decision_id="slug-1")
        entry = self._last_log_entry()
        self.assertEqual(entry["decision_kind"], "log_and_allow")
        self.assertEqual(entry["decision"]["self_severity"], "LOW")

    def test_mismatched_decision_record_not_attached(self):
        self.hc.write_decision_record(
            "some_hook", "HIGH", 0.9, "r", "e", target="OTHER.py")
        self.hc.deny("some_hook", "reason", severity="HIGH", target="x.py")
        entry = self._last_log_entry()
        self.assertNotIn("decision", entry)

    def test_decision_record_with_intended_scope_and_deviation_attached(self):
        """2026-08-19 스키마 확장: 값이 있으면 로그 payload에 붙는다 -
        기존 4개 필드(self_severity/confidence/reason/expected_risk)에
        추가되는 형태지 대체가 아님."""
        self.hc.write_decision_record(
            "some_hook", "HIGH", 0.9, "내 판단", "위험 설명", target="x.py",
            intended_scope="x.py 한 파일만", deviation="없음")
        self.hc.deny("some_hook", "reason", severity="HIGH", target="x.py")
        entry = self._last_log_entry()
        self.assertEqual(entry["decision"], {
            "self_severity": "HIGH", "confidence": 0.9,
            "reason": "내 판단", "expected_risk": "위험 설명",
            "intended_scope": "x.py 한 파일만", "deviation": "없음",
        })

    def test_decision_record_without_intended_scope_or_deviation_stays_four_keys(self):
        """하위 호환 명시적 lock-in: intended_scope/deviation을 안 쓰면
        (이 파일의 다른 모든 기존 테스트가 그렇듯) decision payload가
        여전히 정확히 4개 키다 - 신규 필드가 항상 붙는 게 아님."""
        self.hc.write_decision_record(
            "some_hook", "HIGH", 0.9, "내 판단", "위험 설명", target="x.py")
        self.hc.deny("some_hook", "reason", severity="HIGH", target="x.py")
        entry = self._last_log_entry()
        self.assertEqual(set(entry["decision"].keys()),
                          {"self_severity", "confidence", "reason", "expected_risk"})


class TestRecordOverrideDecisionEnrichment(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        os.environ["HNCS_HOOK_VIOLATIONS_LOG"] = os.path.join(self._tmpdir, "v.jsonl")
        os.environ["HNCS_HOOK_OVERRIDE_AUDIT_LOG"] = os.path.join(self._tmpdir, "o.jsonl")
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = os.path.join(
            self._tmpdir, ".pending_decision_record.json")
        os.environ["HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"] = os.path.join(
            self._tmpdir, ".pending_medium_approval.json")
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        for k in ("HNCS_HOOK_VIOLATIONS_LOG", "HNCS_HOOK_OVERRIDE_AUDIT_LOG",
                   "HNCS_HOOK_DECISION_RECORD_SENTINEL", "HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"):
            os.environ.pop(k, None)
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _last_entry(self, path_env):
        with open(os.environ[path_env], encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
        return lines[-1]

    def test_allow_with_override_attaches_decision_to_both_logs(self):
        """핵심 회귀 테스트: 조회를 한 번만 공유해야 override_audit.jsonl
        쪽에도 decision이 붙는다 - 각자 따로 조회하면 1회성 sentinel이
        첫 호출에서 소비돼 두 번째는 항상 못 붙는다(2026-08-16 정정)."""
        self.hc.write_decision_record(
            "protect_never_touch", "CRITICAL", 0.95, "확신함", "돌이킬 수 없음",
            target="brands/x.py")
        self.hc.allow_with_override(
            "protect_never_touch", "CRITICAL", "protect_never_touch",
            "brands/x.py", "사용자 승인")

        violations_entry = self._last_entry("HNCS_HOOK_VIOLATIONS_LOG")
        audit_entry = self._last_entry("HNCS_HOOK_OVERRIDE_AUDIT_LOG")
        self.assertEqual(violations_entry["decision"]["confidence"], 0.95)
        self.assertEqual(audit_entry["decision"]["confidence"], 0.95)

    def test_allow_with_medium_approval_attaches_decision_to_both_logs(self):
        self.hc.write_decision_record(
            "protect_generated_files", "MEDIUM", 0.6, "r", "e", target="brands/y.py")
        self.hc.allow_with_medium_approval(
            "protect_generated_files", "MEDIUM", "protect_generated_files",
            "brands/y.py", "caution 문구")

        violations_entry = self._last_entry("HNCS_HOOK_VIOLATIONS_LOG")
        audit_entry = self._last_entry("HNCS_HOOK_OVERRIDE_AUDIT_LOG")
        self.assertEqual(violations_entry["decision"]["confidence"], 0.6)
        self.assertEqual(audit_entry["decision"]["confidence"], 0.6)

    def test_no_decision_record_no_decision_key_on_either_log(self):
        self.hc.allow_with_override(
            "protect_never_touch", "CRITICAL", "protect_never_touch",
            "brands/z.py", "사용자 승인")
        violations_entry = self._last_entry("HNCS_HOOK_VIOLATIONS_LOG")
        audit_entry = self._last_entry("HNCS_HOOK_OVERRIDE_AUDIT_LOG")
        self.assertNotIn("decision", violations_entry)
        self.assertNotIn("decision", audit_entry)


class TestDecisionRecordSingleUseAcrossDenyThenOverride(unittest.TestCase):
    """알려진 한계를 명시적으로 lock-in: deny() 한 번에 decision record가
    소비되고 나면, 곧이어 override로 재시도해도(같은 rule/target이라도)
    새로 decision record를 안 쓰면 override 쪽엔 안 붙는다 - 나중에
    "버그"로 재발견되지 않도록."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        os.environ["HNCS_HOOK_VIOLATIONS_LOG"] = os.path.join(self._tmpdir, "v.jsonl")
        os.environ["HNCS_HOOK_OVERRIDE_AUDIT_LOG"] = os.path.join(self._tmpdir, "o.jsonl")
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = os.path.join(
            self._tmpdir, ".pending_decision_record.json")
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        for k in ("HNCS_HOOK_VIOLATIONS_LOG", "HNCS_HOOK_OVERRIDE_AUDIT_LOG",
                   "HNCS_HOOK_DECISION_RECORD_SENTINEL"):
            os.environ.pop(k, None)
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_decision_attaches_to_deny_not_to_subsequent_override(self):
        self.hc.write_decision_record(
            "protect_never_touch", "CRITICAL", 0.9, "r", "e", target="brands/x.py")
        self.hc.deny("protect_never_touch", "denied", severity="CRITICAL", target="brands/x.py")
        self.hc.allow_with_override(
            "protect_never_touch", "CRITICAL", "protect_never_touch",
            "brands/x.py", "사용자 승인")

        with open(os.environ["HNCS_HOOK_VIOLATIONS_LOG"], encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
        deny_entry = entries[0]
        override_entry = entries[1]
        self.assertIn("decision", deny_entry)
        self.assertNotIn("decision", override_entry)


class TestProtectGeneratedFilesDecisionEndToEnd(unittest.TestCase):
    """실제 protect_generated_files.py를 subprocess로 실행해서 decision
    record가 진짜 훅 스크립트를 거쳐 로그에 붙는지 확인."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        brands_dir = os.path.join(self._tmpdir, "brands")
        os.makedirs(brands_dir)
        self._file = os.path.join(brands_dir, "x_learned.py")
        with open(self._file, "w") as f:
            f.write("_LEARNED_LUT = np.array([1, 2, 3])\n")
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._tmpdir, "v.jsonl"),
            "HNCS_HOOK_DECISION_RECORD_SENTINEL": os.path.join(
                self._tmpdir, ".pending_decision_record.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_decision_record(self):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._env[
            "HNCS_HOOK_DECISION_RECORD_SENTINEL"]
        import _hook_common
        _hook_common.write_decision_record(
            "protect_generated_files", "MEDIUM", 0.4,
            "LUT 값 하나만 바꾸는 사소한 수정으로 보임", "재적합 안 해도 될 듯",
            target=self._file)
        del sys.modules["_hook_common"]
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)

    def test_deny_carries_decision_record_through_real_hook(self):
        self._write_decision_record()
        payload = json.dumps({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": self._file,
                "old_string": "_LEARNED_LUT = np.array([1, 2, 3])",
                "new_string": "_LEARNED_LUT = np.array([1, 2, 4])",
            },
        })
        proc = subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "protect_generated_files.py")],
            input=payload, env=self._env, capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

        with open(self._env["HNCS_HOOK_VIOLATIONS_LOG"], encoding="utf-8") as f:
            entry = json.loads(f.readline())
        self.assertEqual(entry["decision"]["confidence"], 0.4)
        self.assertEqual(entry["target"], self._file)


if __name__ == "__main__":
    unittest.main()
