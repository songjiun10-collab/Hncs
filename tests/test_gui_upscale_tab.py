import unittest

from core.upscale import UPSCALE_ENGINES, UPSCALE_SCALES
from gui.tabs.upscale_tab import ENGINE_CHOICES, SCALE_CHOICES, build_upscale_command


class TestChoicesMatchCoreUpscale(unittest.TestCase):
    def test_scale_choices_match(self):
        self.assertEqual(SCALE_CHOICES, [str(s) for s in UPSCALE_SCALES])

    def test_engine_choices_match(self):
        self.assertEqual(set(ENGINE_CHOICES), set(UPSCALE_ENGINES))


class TestBuildUpscaleCommand(unittest.TestCase):
    def test_minimal_command(self):
        cmd = build_upscale_command("in.jpg", "out.png", "4", "onnx", python_exe="python3")
        self.assertEqual(
            cmd, ["python3", "-m", "tools.upscale", "in.jpg", "out.png",
                  "--scale", "4", "--engine", "onnx"])

    def test_pytorch_engine_passed_through(self):
        cmd = build_upscale_command("in.jpg", "out.png", "2", "pytorch", python_exe="python3")
        self.assertIn("--engine", cmd)
        self.assertEqual(cmd[cmd.index("--engine") + 1], "pytorch")


if __name__ == "__main__":
    unittest.main()
