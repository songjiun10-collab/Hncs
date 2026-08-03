import unittest

from gui import app


class TestAppSkeleton(unittest.TestCase):
    def test_tabs_is_a_list(self):
        self.assertIsInstance(app.TABS, list)

    def test_build_app_and_main_are_callable(self):
        self.assertTrue(callable(app.build_app))
        self.assertTrue(callable(app.main))

    def test_tabs_final_shape(self):
        self.assertEqual(
            [label for label, _ in app.TABS],
            ["브랜드 Look", "hybrid_engine 변환", "RAW→Log", "렌즈 보정"])
        for _, build_tab in app.TABS:
            self.assertTrue(callable(build_tab))
