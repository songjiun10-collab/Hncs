"""`.claude/hooks/must_hook_server.py` 테스트 - write_decision_record MCP
툴의 파라미터 스키마가 잘못된 호출을 거부하는지, 정상 호출이
`_hook_common.write_decision_record()`에 위임돼서 기존
`decision_record()` 리더와 호환되는 포맷으로 쓰이는지 확인."""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks")
sys.path.insert(0, _HOOKS_DIR)


class TestMustHookServer(unittest.TestCase):
    def setUp(self):
        self._log_dir = tempfile.mkdtemp()
        self._sentinel_path = os.path.join(self._log_dir, ".pending_decision_record.json")
        os.environ["HNCS_HOOK_DECISION_RECORD_SENTINEL"] = self._sentinel_path
        for mod in ("_hook_common", "must_hook_server"):
            sys.modules.pop(mod, None)
        import must_hook_server as server
        self.server = server

    def tearDown(self):
        shutil.rmtree(self._log_dir, ignore_errors=True)
        os.environ.pop("HNCS_HOOK_DECISION_RECORD_SENTINEL", None)
        for mod in ("_hook_common", "must_hook_server"):
            sys.modules.pop(mod, None)

    def _call(self, **kwargs):
        return asyncio.run(self.server.app.call_tool("write_decision_record", kwargs))

    def test_valid_call_writes_matching_format(self):
        self._call(rule="protect_never_touch", severity="CRITICAL", confidence=0.9,
                    reason="r", expected_risk="e", target="/tmp/x")
        with open(self._sentinel_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["rule"], "protect_never_touch")
        self.assertEqual(data["target"], "/tmp/x")
        self.assertEqual(data["severity"], "CRITICAL")
        self.assertAlmostEqual(data["confidence"], 0.9)

    def test_valid_call_readable_by_decision_record(self):
        self._call(rule="protect_never_touch", severity="HIGH", confidence=0.5,
                    reason="r", expected_risk="e", target="/tmp/y")
        import _hook_common
        result = _hook_common.decision_record("protect_never_touch", target="/tmp/y")
        self.assertIsNotNone(result)
        self.assertEqual(result["severity"], "HIGH")

    def test_decision_id_path_also_works(self):
        self._call(rule="protect_agent_model_naming", severity="LOW", confidence=0.3,
                    reason="r", expected_risk="e", decision_id="dispatch-42")
        import _hook_common
        result = _hook_common.decision_record(
            "protect_agent_model_naming", decision_id="dispatch-42")
        self.assertIsNotNone(result)

    def test_confidence_above_range_rejected(self):
        with self.assertRaises(Exception):
            self._call(rule="r", severity="LOW", confidence=1.5, reason="r",
                        expected_risk="e", target="t")
        self.assertFalse(os.path.exists(self._sentinel_path))

    def test_confidence_below_range_rejected(self):
        with self.assertRaises(Exception):
            self._call(rule="r", severity="LOW", confidence=-0.1, reason="r",
                        expected_risk="e", target="t")

    def test_invalid_severity_rejected(self):
        with self.assertRaises(Exception):
            self._call(rule="r", severity="EXTREME", confidence=0.5, reason="r",
                        expected_risk="e", target="t")

    def test_missing_reason_rejected(self):
        with self.assertRaises(Exception):
            self._call(rule="r", severity="LOW", confidence=0.5,
                        expected_risk="e", target="t")

    def test_empty_reason_rejected(self):
        with self.assertRaises(Exception):
            self._call(rule="r", severity="LOW", confidence=0.5, reason="",
                        expected_risk="e", target="t")

    def test_neither_target_nor_decision_id_raises(self):
        with self.assertRaises(Exception):
            self._call(rule="r", severity="LOW", confidence=0.5, reason="r",
                        expected_risk="e")


if __name__ == "__main__":
    unittest.main()
