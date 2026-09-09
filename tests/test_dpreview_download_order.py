import csv
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULES = (
    "tools.dpreview.download_ricoh_griv_gallery",
    "tools.dpreview.download_xcd_lens_gallery",
    "tools.dpreview.download_x1d_x2d100c_restore",
)


class TestDpreviewDownloadOrder(unittest.TestCase):
    def _csv(self, path, module_name):
        fields = ["camera", "raw_url", "jpg_url", "raw_name", "jpg_name"]
        if module_name != MODULES[0]:
            fields.append("lens")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            row = {
                "camera": "Ricoh GR IV",
                "raw_url": "https://example.invalid/sample.dng",
                "jpg_url": "https://example.invalid/sample.jpg",
                "raw_name": "sample.dng",
                "jpg_name": "sample.jpg",
            }
            if "lens" in fields:
                row["lens"] = "test-lens"
            writer.writerow(row)

    def test_raw_must_finish_before_jpeg_and_manifest(self):
        for module_name in MODULES:
            with self.subTest(module=module_name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                module = importlib.import_module(module_name)
                csv_path = root / "links.csv"
                self._csv(csv_path, module_name)
                set_dir = root / "dataset"
                events = []

                def raw(url, filename, dest, timeout=30):
                    events.append("raw")
                    Path(dest).write_bytes(b"raw")
                    return True

                def jpg(url, dest):
                    events.append("jpg")
                    Path(dest).write_bytes(b"jpg")

                with patch.object(module, "CSV_PATH", str(csv_path)), \
                     patch.object(module, "SET_DIR", str(set_dir)), \
                     patch.object(module, "_download_raw_via_browser", raw), \
                     patch.object(module, "_download_jpg", jpg), \
                     patch.object(module, "_exif", return_value={}):
                    module.main()

                self.assertEqual(events, ["raw", "jpg"])
                manifest = set_dir / "manifest.csv"
                self.assertTrue(manifest.exists())
                with manifest.open(encoding="utf-8") as handle:
                    self.assertEqual(sum(1 for _ in csv.DictReader(handle)), 1)

    def test_raw_failure_leaves_no_jpeg_or_manifest_row(self):
        module = importlib.import_module(MODULES[0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            csv_path = root / "links.csv"
            self._csv(csv_path, MODULES[0])
            set_dir = root / "dataset"
            with patch.object(module, "CSV_PATH", str(csv_path)), \
                 patch.object(module, "SET_DIR", str(set_dir)), \
                 patch.object(module, "_download_raw_via_browser", return_value=False), \
                 patch.object(module, "_download_jpg") as jpg, \
                 patch.object(module, "_exif", return_value={}):
                module.main()
            jpg.assert_not_called()
            manifest = set_dir / "manifest.csv"
            with manifest.open(encoding="utf-8") as handle:
                self.assertEqual(sum(1 for _ in csv.DictReader(handle)), 0)
            self.assertFalse((set_dir / "jpeg" / "sample.jpg").exists())


if __name__ == "__main__":
    unittest.main()
