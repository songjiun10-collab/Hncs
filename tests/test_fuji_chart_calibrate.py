import unittest

import numpy as np

from tools.fuji_chart_calibrate import aggregate_deltas, extract_strips


class TestExtractStrips(unittest.TestCase):
    def test_splits_by_box_frac(self):
        img = np.zeros((100, 200, 3), dtype=np.uint8)
        img[:, :100] = 50   # 왼쪽 절반
        img[:, 100:] = 200  # 오른쪽 절반
        strips = [
            {"film_mode": "Left", "box_frac": [0.0, 0.0, 0.5, 1.0]},
            {"film_mode": "Right", "box_frac": [0.5, 0.0, 1.0, 1.0]},
        ]
        out = extract_strips(img, strips)
        self.assertEqual(set(out.keys()), {"Left", "Right"})
        self.assertTrue(np.all(out["Left"] == 50))
        self.assertTrue(np.all(out["Right"] == 200))

    def test_box_frac_is_relative_to_image_size(self):
        small = np.full((50, 50, 3), 10, dtype=np.uint8)
        big = np.full((500, 500, 3), 10, dtype=np.uint8)
        strips = [{"film_mode": "Center", "box_frac": [0.25, 0.25, 0.75, 0.75]}]
        out_small = extract_strips(small, strips)["Center"]
        out_big = extract_strips(big, strips)["Center"]
        self.assertEqual(out_small.shape[:2], (25, 25))
        self.assertEqual(out_big.shape[:2], (250, 250))


class TestAggregateDeltas(unittest.TestCase):
    def test_groups_by_film_mode_across_charts(self):
        all_deltas = {
            "chart1": {"Astia": {"d_b2": -2.0, "d_w995": 5.0, "d_sat": -10.0}},
            "chart2": {"Astia": {"d_b2": -4.0, "d_w995": 7.0, "d_sat": -20.0}},
        }
        agg = aggregate_deltas(all_deltas)
        self.assertEqual(agg["Astia"]["n_charts"], 2)
        self.assertAlmostEqual(agg["Astia"]["d_b2"]["mean"], -3.0)
        self.assertAlmostEqual(agg["Astia"]["d_sat"]["mean"], -15.0)

    def test_missing_mode_in_some_charts_only_counts_present_ones(self):
        all_deltas = {
            "chart1": {"Astia": {"d_b2": -2.0, "d_w995": 5.0, "d_sat": -10.0}},
            "chart2": {"Acros": {"d_b2": -1.0, "d_w995": 2.0, "d_sat": -60.0}},
        }
        agg = aggregate_deltas(all_deltas)
        self.assertEqual(agg["Astia"]["n_charts"], 1)
        self.assertEqual(agg["Acros"]["n_charts"], 1)

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(aggregate_deltas({}), {})


if __name__ == "__main__":
    unittest.main()
