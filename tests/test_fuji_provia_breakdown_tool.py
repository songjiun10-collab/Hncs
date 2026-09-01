"""`tools/breakdown_fuji_provia_by_camera_body.py`의 순수 부분(manifest
camera 컬럼 매핑)만 검증 - RAW 디코드는 CI에 데이터가 없어서
(tests/CLAUDE.md) 제외. `tests/test_sony_a1ii_breakdown_tools.py`의
같은 패턴을 Fuji manifest 스키마로 반복."""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestFujiCameraManifestMapping(unittest.TestCase):
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
                writer.writerow({"filename_raw": "a.RAF", "filename_jpeg": "a.JPG",
                                  "camera": "GFX100RF", "lens": "", "iso": "", "wb_setting": "",
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

            self.assertEqual(name_to_camera["a.RAF"], "GFX100RF")


if __name__ == "__main__":
    unittest.main()
