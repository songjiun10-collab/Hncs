import unittest

from gui.tabs.hybrid_convert import (
    AUTO_LABEL, build_hybrid_convert_command, is_raw_input, list_raw_profiles,
)


class TestIsRawInput(unittest.TestCase):
    def test_raw_extension_true(self):
        self.assertTrue(is_raw_input("photo.3FR"))
        self.assertTrue(is_raw_input("photo.nef"))

    def test_jpeg_extension_false(self):
        self.assertFalse(is_raw_input("photo.jpg"))


class TestBuildHybridConvertCommand(unittest.TestCase):
    def test_jpeg_requires_target_flag(self):
        cmd = build_hybrid_convert_command("in.jpg", "out.jpg", "hasselblad",
                                            python_exe="python3")
        self.assertEqual(
            cmd, ["python3", "-m", "hybrid_engine.convert", "in.jpg", "out.jpg",
                  "--target", "hasselblad"])

    def test_jpeg_with_source_override(self):
        cmd = build_hybrid_convert_command("in.jpg", "out.jpg", "hasselblad",
                                            source_override="canon", python_exe="python3")
        self.assertEqual(
            cmd, ["python3", "-m", "hybrid_engine.convert", "in.jpg", "out.jpg",
                  "--target", "hasselblad", "--source", "canon"])

    def test_jpeg_auto_source_omits_flag(self):
        cmd = build_hybrid_convert_command("in.jpg", "out.jpg", "hasselblad",
                                            source_override=AUTO_LABEL, python_exe="python3")
        self.assertNotIn("--source", cmd)

    def test_raw_with_profile_override(self):
        cmd = build_hybrid_convert_command("in.3FR", "out.jpg", "hasselblad",
                                            python_exe="python3")
        self.assertEqual(
            cmd, ["python3", "-m", "hybrid_engine.main", "in.3FR", "out.jpg",
                  "--profile", "hasselblad"])

    def test_raw_auto_profile_omits_flag(self):
        cmd = build_hybrid_convert_command("in.3FR", "out.jpg", AUTO_LABEL,
                                            python_exe="python3")
        self.assertNotIn("--profile", cmd)


class TestListRawProfiles(unittest.TestCase):
    def test_includes_hasselblad(self):
        self.assertIn("hasselblad", list_raw_profiles())


if __name__ == "__main__":
    unittest.main()
