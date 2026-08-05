import csv
import os
import tempfile
import unittest

from tools.evaluate_sony_body_split import load_rows, loo_errors


class TestLoadRows(unittest.TestCase):
    def test_strips_sony_prefix_and_parses_floats(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["camera", "filename", "url", "b2", "w995", "med", "sat", "dark_pct"])
                writer.writerow(["Sony A7 III", "img1.jpg", "http://x", "10.7", "185.3", "70.0", "91.8", "20.0"])
            rows = load_rows(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["body"], "A7 III")
            self.assertEqual(rows[0]["name"], "img1.jpg")
            self.assertAlmostEqual(rows[0]["b2"], 10.7)
            self.assertAlmostEqual(rows[0]["w995"], 185.3)
        finally:
            os.remove(path)

    def test_reads_all_rows(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["camera", "filename", "url", "b2", "w995", "med", "sat", "dark_pct"])
                writer.writerow(["Sony A7", "a.jpg", "u", "1", "2", "3", "4", "5"])
                writer.writerow(["Sony A7R", "b.jpg", "u", "6", "7", "8", "9", "10"])
            rows = load_rows(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual([r["body"] for r in rows], ["A7", "A7R"])
        finally:
            os.remove(path)


class TestLooErrors(unittest.TestCase):
    def setUp(self):
        # 2 bodies, 3 images each, exact hand-computed expected errors
        self.rows = [
            {"body": "X", "name": "x0", "b2": 10.0},
            {"body": "X", "name": "x1", "b2": 12.0},
            {"body": "X", "name": "x2", "b2": 14.0},
            {"body": "Y", "name": "y0", "b2": 20.0},
            {"body": "Y", "name": "y1", "b2": 22.0},
            {"body": "Y", "name": "y2", "b2": 24.0},
        ]

    def test_returns_one_row_per_input_image(self):
        errors = loo_errors(self.rows, "b2")
        self.assertEqual(len(errors), 6)

    def test_holdout_x0_pooled_and_body_errors(self):
        # held-out x0=10.0: others = [12,14,20,22,24] -> pooled mean 18.4 -> |10-18.4|=8.4
        # same-body(X) others = [12,14] -> body mean 13.0 -> |10-13.0|=3.0
        errors = loo_errors(self.rows, "b2")
        x0 = next(e for e in errors if e["name"] == "x0")
        self.assertAlmostEqual(x0["pooled_error"], 8.4)
        self.assertAlmostEqual(x0["body_error"], 3.0)
        self.assertEqual(x0["body"], "X")

    def test_holdout_y0_pooled_and_body_errors(self):
        # held-out y0=20.0: others = [10,12,14,22,24] -> pooled mean 16.4 -> |20-16.4|=3.6
        # same-body(Y) others = [22,24] -> body mean 23.0 -> |20-23.0|=3.0
        errors = loo_errors(self.rows, "b2")
        y0 = next(e for e in errors if e["name"] == "y0")
        self.assertAlmostEqual(y0["pooled_error"], 3.6)
        self.assertAlmostEqual(y0["body_error"], 3.0)


if __name__ == "__main__":
    unittest.main()
