import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from gui.tabs.lens_correction_tab import build_lens_correction_command, read_exif_fields


class TestBuildLensCorrectionCommand(unittest.TestCase):
    def test_minimal_command_no_overrides(self):
        cmd = build_lens_correction_command("in.jpg", "out.jpg", python_exe="python3")
        self.assertEqual(cmd, ["python3", "-m", "tools.lens_correction", "in.jpg", "out.jpg"])

    def test_all_overrides_included(self):
        cmd = build_lens_correction_command(
            "in.jpg", "out.jpg", make="FUJIFILM", model="X-T1", lens="XF10-24mmF4 R OIS",
            focal_length=10, aperture=8, python_exe="python3")
        self.assertEqual(cmd, [
            "python3", "-m", "tools.lens_correction", "in.jpg", "out.jpg",
            "--make", "FUJIFILM", "--model", "X-T1", "--lens", "XF10-24mmF4 R OIS",
            "--focal-length", "10", "--aperture", "8",
        ])


class TestReadExifFields(unittest.TestCase):
    @patch("gui.tabs.lens_correction_tab.subprocess.run")
    def test_parses_available_fields(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([{
                "Make": "FUJIFILM", "Model": "X-T1", "LensModel": "XF10-24mmF4 R OIS",
                "FocalLength": "10.0 mm", "FNumber": 4.0,
            }]))
        fields = read_exif_fields("dummy.RAF")
        self.assertEqual(fields, {
            "make": "FUJIFILM", "model": "X-T1", "lens": "XF10-24mmF4 R OIS",
            "focal_length": "10.0", "aperture": "4.0",
        })

    @patch("gui.tabs.lens_correction_tab.subprocess.run")
    def test_exiftool_failure_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertEqual(read_exif_fields("dummy.RAF"), {})

    @patch("gui.tabs.lens_correction_tab.subprocess.run")
    def test_passes_env(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        read_exif_fields("dummy.RAF")
        self.assertIn("env", mock_run.call_args.kwargs)

    @patch("gui.tabs.lens_correction_tab.subprocess.run")
    def test_exiftool_not_found_returns_empty_and_reports_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError("no exiftool")
        errors = []
        fields = read_exif_fields("dummy.RAF", on_error=errors.append)
        self.assertEqual(fields, {})
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FileNotFoundError)

    @patch("gui.tabs.lens_correction_tab.subprocess.run")
    def test_timeout_returns_empty_and_reports_error(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="exiftool", timeout=60)
        errors = []
        fields = read_exif_fields("dummy.RAF", on_error=errors.append)
        self.assertEqual(fields, {})
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], subprocess.TimeoutExpired)

    @patch("gui.tabs.lens_correction_tab.subprocess.run")
    def test_no_on_error_does_not_raise(self, mock_run):
        mock_run.side_effect = FileNotFoundError("no exiftool")
        self.assertEqual(read_exif_fields("dummy.RAF"), {})


if __name__ == "__main__":
    unittest.main()
