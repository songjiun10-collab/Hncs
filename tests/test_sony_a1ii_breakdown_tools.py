"""`tools/breakdown_sony_by_camera_body.py`/`tools/evaluate_sony_a1ii_vs_raw_look.py`
의 순수 부분만 검증 - RAW 디코드는 CI에 데이터가 없어서(tests/CLAUDE.md)
제외. 카메라 매핑 CSV 파싱과 부호검정 통계 함수만 대상."""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.evaluate_sony_a1ii_vs_raw_look import _sign_test_p


class TestSignTestP(unittest.TestCase):
    def test_all_wins_gives_small_p(self):
        self.assertLess(_sign_test_p(10, 0), 0.01)

    def test_even_split_gives_p_near_one(self):
        self.assertGreater(_sign_test_p(5, 5), 0.9)

    def test_no_observations_returns_one(self):
        self.assertEqual(_sign_test_p(0, 0), 1.0)


class TestCameraManifestMapping(unittest.TestCase):
    """`tools/breakdown_sony_by_camera_body.py`의 name->camera 매핑 로직을
    실제 manifest.csv 스키마와 같은 임시 CSV로 검증 - RAW 파일은 안 씀."""

    def test_name_to_camera_reads_camera_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = os.path.join(tmp, "some-set")
            os.makedirs(set_dir)
            manifest_path = os.path.join(set_dir, "manifest.csv")
            with open(manifest_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "filename_raw", "filename_jpeg", "camera", "lens", "iso",
                    "wb_setting", "scene_type", "filename_phocus_tiff",
                    "phocus_settings", "illuminant", "download_url", "notes"])
                writer.writeheader()
                writer.writerow({"filename_raw": "a.ARW", "filename_jpeg": "a.JPG",
                                  "camera": "ILCE-1M2", "lens": "", "iso": "", "wb_setting": "",
                                  "scene_type": "", "filename_phocus_tiff": "",
                                  "phocus_settings": "", "illuminant": "",
                                  "download_url": "", "notes": ""})

            name_to_camera = {}
            for set_name in sorted(os.listdir(tmp)):
                m = os.path.join(tmp, set_name, "manifest.csv")
                if not os.path.exists(m):
                    continue
                for row in csv.DictReader(open(m, encoding="utf-8-sig")):
                    name_to_camera.setdefault(row["filename_raw"], row.get("camera", "?"))

            self.assertEqual(name_to_camera["a.ARW"], "ILCE-1M2")


if __name__ == "__main__":
    unittest.main()
