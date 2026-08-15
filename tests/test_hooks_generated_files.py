"""`.claude/hooks/protect_generated_files.py` 테스트 - brands/*_learned.py의
_LEARNED_LUT* 배열을 직접 건드리는 Edit/Write가 ask()(MID, 실제 사람
확인 프롬프트로 넘김)로 걸리는지, 무관한 편집은 조용히 통과하는지."""
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

_HOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), ".claude", "hooks")
sys.path.insert(0, _HOOKS_DIR)
import protect_generated_files as hook  # noqa: E402

_SAMPLE_LEARNED_FILE = textwrap.dedent('''\
    """docstring"""
    import numpy as np

    from core.engine import apply_learned_lut_look

    _LEARNED_LUT = np.array([
        1, 2, 3, 4,
    ], dtype=np.uint8)


    def apply_x_learned(img_bgr, clahe_clip=1.25):
        return apply_learned_lut_look(img_bgr, _LEARNED_LUT, clahe_clip)
''')


class TestLutArrayRanges(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix="_learned.py", delete=False, dir="/tmp")
        self._tmp.write(_SAMPLE_LEARNED_FILE)
        self._tmp.close()

    def tearDown(self):
        os.remove(self._tmp.name)

    def test_finds_learned_lut_range(self):
        ranges = hook.lut_array_ranges(self._tmp.name)
        names = [n for n, _, _ in ranges]
        self.assertIn("_LEARNED_LUT", names)

    def test_edit_inside_array_detected(self):
        name = hook.touched_lut_array(self._tmp.name, "1, 2, 3, 4,")
        self.assertEqual(name, "_LEARNED_LUT")

    def test_edit_outside_array_not_detected(self):
        name = hook.touched_lut_array(
            self._tmp.name, "def apply_x_learned(img_bgr, clahe_clip=1.25):")
        self.assertIsNone(name)

    def test_is_learned_brand_file_matches(self):
        self.assertTrue(hook.is_learned_brand_file("brands/sony_a7rvi_learned.py"))

    def test_is_learned_brand_file_rejects_non_learned(self):
        self.assertFalse(hook.is_learned_brand_file("brands/sony_a7rvi.py"))
        self.assertFalse(hook.is_learned_brand_file("tools/fit_final_lut.py"))


class TestProtectGeneratedFilesEndToEnd(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self._file = os.path.join(self._dir, "brands", "x_learned.py")
        os.makedirs(os.path.dirname(self._file))
        with open(self._file, "w") as f:
            f.write(_SAMPLE_LEARNED_FILE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._dir, ignore_errors=True)

    def _run_hook(self, tool_name, tool_input):
        payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
        proc = subprocess.run(
            [sys.executable, hook.__file__], input=payload,
            capture_output=True, text=True, timeout=15,
        )
        out = json.loads(proc.stdout)
        return out["hookSpecificOutput"]["permissionDecision"]

    def test_lut_edit_asks(self):
        decision = self._run_hook("Edit", {
            "file_path": self._file,
            "old_string": "1, 2, 3, 4,",
            "new_string": "9, 9, 9, 9,",
        })
        self.assertEqual(decision, "ask")

    def test_unrelated_edit_allowed(self):
        decision = self._run_hook("Edit", {
            "file_path": self._file,
            "old_string": '"""docstring"""',
            "new_string": '"""updated docstring"""',
        })
        self.assertEqual(decision, "allow")

    def test_write_to_learned_file_asks(self):
        decision = self._run_hook("Write", {
            "file_path": self._file, "content": _SAMPLE_LEARNED_FILE,
        })
        self.assertEqual(decision, "ask")

    def test_non_learned_file_allowed(self):
        decision = self._run_hook("Edit", {
            "file_path": "brands/sony_a7rvi.py",
            "old_string": "x", "new_string": "y",
        })
        self.assertEqual(decision, "allow")

    def test_non_matching_tool_allowed(self):
        decision = self._run_hook("Read", {"file_path": self._file})
        self.assertEqual(decision, "allow")


if __name__ == "__main__":
    unittest.main()
