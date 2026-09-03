"""Import smoke tests for the ad-hoc tools/analyze_x2dii_*.py scripts -
these are one-off research scripts (no shipped-code imports them, see
tools/CLAUDE.md), so full behavioral tests aren't warranted, but a
broken import should still fail CI rather than only be discovered when
someone tries to rerun the analysis."""
import importlib
import unittest


class TestAnalyzeX2diiScriptsImport(unittest.TestCase):
    def test_loss_breakdown_imports(self):
        importlib.import_module("tools.analyze_x2dii_loss_breakdown")

    def test_burst_fair_comparison_imports(self):
        importlib.import_module("tools.analyze_x2dii_burst_fair_comparison")

    def test_kmichels_own_matrix_gap_imports(self):
        importlib.import_module("tools.analyze_x2dii_kmichels_own_matrix_gap")

    def test_full_interpolation_end_to_end_imports(self):
        importlib.import_module("tools.analyze_x2dii_full_interpolation_end_to_end")


if __name__ == "__main__":
    unittest.main()
