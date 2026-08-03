import unittest

from gui import app


class TestAppSkeleton(unittest.TestCase):
    def test_tabs_is_a_list(self):
        self.assertIsInstance(app.TABS, list)

    def test_build_app_and_main_are_callable(self):
        self.assertTrue(callable(app.build_app))
        self.assertTrue(callable(app.main))
