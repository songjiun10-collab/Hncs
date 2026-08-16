"""MEDIUM tier의 "상위 에이전트가 허용하면 실행 에이전트가 실행, 단
주의사항 전달" 메커니즘(2026-08-15) 테스트 - 3개 조각을 각각, 그리고
`protect_generated_files.py`를 통해 end-to-end로 확인한다:

1. `_hook_common.medium_approval()`/`write_medium_approval()` - sentinel
   파일 자체의 순수 함수 계약(fresh/matching/consumed).
2. `record_agent_approval.py` (PostToolUse, Agent matcher) - 디스패치된
   서브에이전트 응답에서 `MEDIUM-APPROVE: <rule> :: <target> ::
   <caution>` 마커를 파싱해 승인을 기록. sonnet/opus만 인정, haiku/모델
   미지정은 기록 안 함.
3. `deliver_caution.py` (PostToolUse, Edit|Write|MultiEdit matcher) -
   `tool_use_id`로 큐잉된 caution을 `additionalContext`로 전달.

로그/sentinel 파일이 실제 git-tracked 파일을 오염시키지 않도록 매
테스트마다 HNCS_HOOK_* 환경변수로 격리한다."""
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


class TestMediumApprovalSentinel(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, ".pending_medium_approval.json")
        os.environ["HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL"] = self._path
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        os.environ.pop("HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL", None)
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_fresh_matching_approval_returns_caution_and_is_consumed(self):
        self.hc.write_medium_approval("protect_generated_files", "brands/x.py", "주의해")
        caution = self.hc.medium_approval("protect_generated_files", "brands/x.py")
        self.assertEqual(caution, "주의해")
        self.assertFalse(os.path.exists(self._path))

    def test_mismatched_target_returns_none(self):
        self.hc.write_medium_approval("protect_generated_files", "brands/x.py", "주의해")
        self.assertIsNone(self.hc.medium_approval("protect_generated_files", "brands/OTHER.py"))

    def test_mismatched_rule_returns_none(self):
        self.hc.write_medium_approval("protect_generated_files", "brands/x.py", "주의해")
        self.assertIsNone(self.hc.medium_approval("some_other_rule", "brands/x.py"))

    def test_expired_approval_returns_none(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({"rule": "protect_generated_files", "target": "brands/x.py",
                       "caution": "주의해", "timestamp": time.time() - 700}, f)
        self.assertIsNone(self.hc.medium_approval("protect_generated_files", "brands/x.py"))

    def test_no_approval_file_returns_none(self):
        self.assertIsNone(self.hc.medium_approval("protect_generated_files", "brands/x.py"))


class TestPendingCaution(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._path = os.path.join(self._tmpdir, ".pending_caution.json")
        os.environ["HNCS_HOOK_PENDING_CAUTION"] = self._path
        sys.modules.pop("_hook_common", None)
        import _hook_common
        self.hc = _hook_common

    def tearDown(self):
        os.environ.pop("HNCS_HOOK_PENDING_CAUTION", None)
        sys.modules.pop("_hook_common", None)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_matching_tool_use_id_returns_caution_and_is_consumed(self):
        self.hc.write_pending_caution("tu_1", "조심해")
        self.assertEqual(self.hc.pop_pending_caution("tu_1"), "조심해")
        self.assertFalse(os.path.exists(self._path))

    def test_mismatched_tool_use_id_returns_none(self):
        self.hc.write_pending_caution("tu_1", "조심해")
        self.assertIsNone(self.hc.pop_pending_caution("tu_2"))

    def test_no_file_returns_none(self):
        self.assertIsNone(self.hc.pop_pending_caution("tu_1"))


class TestRecordAgentApproval(unittest.TestCase):
    """record_agent_approval.py를 subprocess로 실제 실행."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._approval_path = os.path.join(self._tmpdir, ".pending_medium_approval.json")
        self._env = dict(os.environ, HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL=self._approval_path)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run(self, tool_response):
        payload = json.dumps({"tool_name": "Agent", "tool_response": tool_response})
        subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "record_agent_approval.py")],
            input=payload, env=self._env, capture_output=True, text=True, timeout=15,
        )

    def test_sonnet_response_with_marker_records_approval(self):
        self._run({
            "resolvedModel": "claude-sonnet-5",
            "content": [{"type": "text", "text":
                         "검토 결과 문제없음.\n"
                         "MEDIUM-APPROVE: protect_generated_files :: brands/x.py :: "
                         "fold 3 재적합, monotonic 확인 필요\n"}],
        })
        with open(self._approval_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["rule"], "protect_generated_files")
        self.assertEqual(data["target"], "brands/x.py")
        self.assertIn("monotonic", data["caution"])

    def test_haiku_response_with_marker_not_recorded(self):
        self._run({
            "resolvedModel": "claude-haiku-4-5",
            "content": [{"type": "text", "text":
                         "MEDIUM-APPROVE: protect_generated_files :: brands/x.py :: 주의\n"}],
        })
        self.assertFalse(os.path.exists(self._approval_path))

    def test_missing_model_with_marker_not_recorded(self):
        self._run({
            "content": [{"type": "text", "text":
                         "MEDIUM-APPROVE: protect_generated_files :: brands/x.py :: 주의\n"}],
        })
        self.assertFalse(os.path.exists(self._approval_path))

    def test_sonnet_response_without_marker_not_recorded(self):
        self._run({
            "resolvedModel": "claude-sonnet-5",
            "content": [{"type": "text", "text": "다 괜찮아 보입니다."}],
        })
        self.assertFalse(os.path.exists(self._approval_path))


class TestDeliverCaution(unittest.TestCase):
    """deliver_caution.py를 subprocess로 실제 실행."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._caution_path = os.path.join(self._tmpdir, ".pending_caution.json")
        self._env = dict(os.environ, HNCS_HOOK_PENDING_CAUTION=self._caution_path)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_pending(self, tool_use_id, caution):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        os.environ["HNCS_HOOK_PENDING_CAUTION"] = self._caution_path
        import _hook_common
        _hook_common.write_pending_caution(tool_use_id, caution)
        del sys.modules["_hook_common"]

    def _run(self, tool_use_id):
        payload = json.dumps({"tool_name": "Edit", "tool_use_id": tool_use_id})
        proc = subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "deliver_caution.py")],
            input=payload, env=self._env, capture_output=True, text=True, timeout=15,
        )
        return proc.stdout.strip()

    def test_matching_tool_use_id_delivers_caution(self):
        self._write_pending("tu_1", "monotonic 확인 필요")
        out = self._run("tu_1")
        self.assertTrue(out, "additionalContext should be printed")
        data = json.loads(out)
        self.assertIn("monotonic", data["hookSpecificOutput"]["additionalContext"])

    def test_no_pending_caution_prints_nothing(self):
        out = self._run("tu_1")
        self.assertEqual(out, "")

    def test_non_edit_tool_prints_nothing(self):
        self._write_pending("tu_1", "monotonic 확인 필요")
        payload = json.dumps({"tool_name": "Bash", "tool_use_id": "tu_1"})
        proc = subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "deliver_caution.py")],
            input=payload, env=self._env, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(proc.stdout.strip(), "")


class TestProtectGeneratedFilesMediumApprovalEndToEnd(unittest.TestCase):
    """protect_generated_files.py가 medium_approval()을 실제로 소비해서
    통과시키고, caution을 tool_use_id로 큐잉하는지 subprocess로 확인."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._env = dict(os.environ, **{
            "HNCS_HOOK_VIOLATIONS_LOG": os.path.join(self._tmpdir, "v.jsonl"),
            "HNCS_HOOK_OVERRIDE_AUDIT_LOG": os.path.join(self._tmpdir, "o.jsonl"),
            "HNCS_HOOK_OVERRIDE_SENTINEL": os.path.join(self._tmpdir, ".pending_override.json"),
            "HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL": os.path.join(
                self._tmpdir, ".pending_medium_approval.json"),
            "HNCS_HOOK_PENDING_CAUTION": os.path.join(self._tmpdir, ".pending_caution.json"),
        })

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_approval(self, target, caution):
        sys.path.insert(0, _HOOKS_DIR)
        sys.modules.pop("_hook_common", None)
        for k, v in self._env.items():
            if k.startswith("HNCS_HOOK_"):
                os.environ[k] = v
        import _hook_common
        _hook_common.write_medium_approval("protect_generated_files", target, caution)
        del sys.modules["_hook_common"]

    def test_medium_approval_allows_and_queues_caution(self):
        brands_dir = os.path.join(self._tmpdir, "brands")
        os.makedirs(brands_dir, exist_ok=True)
        target = os.path.join(brands_dir, "sony_a7rvi_learned.py")
        old_string = "_LEARNED_LUT = np.array([1, 2, 3])"
        with open(target, "w", encoding="utf-8") as f:
            f.write(old_string + "\n")

        self._write_approval(target, "fold 3 재적합, monotonic 확인 필요")

        payload = json.dumps({
            "tool_name": "Edit",
            "tool_use_id": "tu_1",
            "tool_input": {
                "file_path": target,
                "old_string": old_string,
                "new_string": "_LEARNED_LUT = np.array([1, 2, 4])",
            },
        })
        proc = subprocess.run(
            [sys.executable, os.path.join(_HOOKS_DIR, "protect_generated_files.py")],
            input=payload, env=self._env, capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "allow")

        with open(self._env["HNCS_HOOK_PENDING_CAUTION"], encoding="utf-8") as f:
            queued = json.load(f)
        self.assertEqual(queued["tool_use_id"], "tu_1")
        self.assertIn("monotonic", queued["caution"])


if __name__ == "__main__":
    unittest.main()
