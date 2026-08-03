import unittest

from core.log_pipeline import LOG_SPACES
from gui.tabs.raw_pipeline_tab import (
    AUTO_EXPOSE_MODES, LOG_SPACE_CHOICES, build_raw_pipeline_command,
)
from tools.raw_pipeline import _AUTO_EXPOSE_MODES


class TestLogSpaceChoices(unittest.TestCase):
    def test_matches_core_log_pipeline(self):
        self.assertEqual(LOG_SPACE_CHOICES, sorted(LOG_SPACES))


class TestAutoExposeModesDrift(unittest.TestCase):
    def test_matches_tools_raw_pipeline_modes(self):
        self.assertEqual(set(AUTO_EXPOSE_MODES), {"없음"} | set(_AUTO_EXPOSE_MODES.keys()))


class TestBuildRawPipelineCommand(unittest.TestCase):
    def test_minimal_command(self):
        cmd = build_raw_pipeline_command("in.CR3", "out.tiff", "S-Log3", python_exe="python3")
        self.assertEqual(
            cmd, ["python3", "-m", "tools.raw_pipeline", "in.CR3", "out.tiff",
                  "--log-space", "S-Log3"])

    def test_exposure_flag_included_when_nonzero(self):
        cmd = build_raw_pipeline_command("in.CR3", "out.tiff", "S-Log3", exposure=1.5,
                                          python_exe="python3")
        self.assertIn("--exposure", cmd)
        self.assertIn("1.5", cmd)

    def test_auto_expose_mode_included_when_set(self):
        cmd = build_raw_pipeline_command("in.CR3", "out.tiff", "S-Log3",
                                          auto_expose_mode="highlight_safe", python_exe="python3")
        self.assertEqual(cmd[-2:], ["--auto-expose-mode", "highlight_safe"])

    def test_auto_expose_none_label_omits_flag(self):
        cmd = build_raw_pipeline_command("in.CR3", "out.tiff", "S-Log3",
                                          auto_expose_mode="없음", python_exe="python3")
        self.assertNotIn("--auto-expose-mode", cmd)


if __name__ == "__main__":
    unittest.main()
