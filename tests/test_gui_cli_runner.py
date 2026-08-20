import os
import shutil
import unittest
from unittest.mock import MagicMock

from gui.tabs._cli_runner import CliRunner


class _FakeWidget:
    """실 Tk 없이 CliRunner를 테스트하기 위한 위젯 대역 - after()를 그
    자리에서 바로 호출한다(테스트 목적상 스레드 안전성은 문제되지 않음)."""

    def after(self, delay, func, *args):
        func(*args)


class _CliRunnerTestCase(unittest.TestCase):
    def _make(self):
        run_button = MagicMock()
        choose_button = MagicMock()
        progress = MagicMock()
        runner = CliRunner(_FakeWidget(), run_button, choose_button, progress)
        self.addCleanup(shutil.rmtree, runner.out_dir, ignore_errors=True)
        return runner, run_button, choose_button, progress


class TestCliRunnerInit(_CliRunnerTestCase):
    def test_creates_out_dir(self):
        runner, *_ = self._make()
        self.assertTrue(os.path.isdir(runner.out_dir))


class TestCliRunnerSuccessPath(_CliRunnerTestCase):
    def test_disables_then_reenables_buttons_and_delivers_result(self):
        runner, run_button, choose_button, progress = self._make()
        done = []
        thread = runner.start(lambda: "ok", done.append,
                               lambda exc: self.fail(f"unexpected error: {exc}"))
        thread.join(timeout=5)

        run_button.configure.assert_any_call(state="disabled")
        run_button.configure.assert_any_call(state="normal")
        choose_button.configure.assert_any_call(state="disabled")
        choose_button.configure.assert_any_call(state="normal")
        progress.start.assert_called_once()
        progress.stop.assert_called_once()
        self.assertEqual(done, ["ok"])


class TestCliRunnerErrorPath(_CliRunnerTestCase):
    def test_exception_in_work_routes_to_on_error_and_recovers(self):
        runner, run_button, choose_button, progress = self._make()
        errors = []

        def boom():
            raise ValueError("nope")

        thread = runner.start(boom, lambda result: self.fail("unexpected done"), errors.append)
        thread.join(timeout=5)

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        run_button.configure.assert_any_call(state="normal")
        choose_button.configure.assert_any_call(state="normal")
        progress.stop.assert_called_once()


class TestCliRunnerOutDirLifecycle(_CliRunnerTestCase):
    def test_start_clears_previous_output_before_running(self):
        runner, *_ = self._make()
        stale = os.path.join(runner.out_dir, "stale.txt")
        with open(stale, "w") as f:
            f.write("x")

        thread = runner.start(lambda: None, lambda r: None, lambda e: None)
        thread.join(timeout=5)

        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.isdir(runner.out_dir))


if __name__ == "__main__":
    unittest.main()
