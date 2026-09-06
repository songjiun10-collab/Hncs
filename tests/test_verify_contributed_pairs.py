import os
import shutil
import subprocess
import tempfile
import unittest

import cv2
import numpy as np

from tools.verify_contributed_pairs import verify_row, _model_matches, _parse_exif_datetime


def _write_tagged_image(path, make="Hasselblad", model="X2D II 100C",
                         datetime_original="2026:07:01 12:00:00", software=None):
    """exiftool로 EXIF를 심은 작은 JPEG 생성. exiftool은 확장자-내용이
    안 맞는 파일(.3FR 이름의 JPEG)에는 *쓰기*를 거부하므로 .jpg 상태에서
    태깅한 뒤 최종 이름으로 rename한다 - *읽기*는 내용 기준이라 검증
    대상 코드(verify_row)는 rename된 파일도 정상적으로 읽는다."""
    img = np.random.default_rng(0).integers(0, 256, (16, 16, 3), dtype=np.uint8)
    tmp_jpg = path + "._tmp.jpg"
    cv2.imwrite(tmp_jpg, img)
    tags = [f"-Make={make}", f"-Model={model}", f"-DateTimeOriginal={datetime_original}"]
    if software:
        tags.append(f"-Software={software}")
    subprocess.run(["exiftool", "-overwrite_original"] + tags + [tmp_jpg],
                    capture_output=True, timeout=30, check=True)
    os.replace(tmp_jpg, path)


@unittest.skipUnless(shutil.which("exiftool"), "exiftool 없음")
class TestVerifyRow(unittest.TestCase):
    """EXIF를 심으려면 실제 exiftool이 필요하다 - 없으면 error가 아니라 skip.
    CI는 `libimage-exiftool-perl`을 깔아서 항상 돌린다
    (`.github/workflows/tests.yml`)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.set_dir = self.tmp.name
        os.makedirs(os.path.join(self.set_dir, "raw"))
        os.makedirs(os.path.join(self.set_dir, "jpeg"))

    def _row(self, **overrides):
        row = {
            "filename_raw": "shot1.3FR",
            "filename_jpeg": "shot1.jpg",
            "camera": "X2D II 100C",
            "lens": "XCD 2,5/55V",
            "iso": "100",
            "wb_setting": "auto",
            "scene_type": "daylight",
            "download_url": "https://example.com/set",
        }
        row.update(overrides)
        return row

    def _make_pair(self, raw_kwargs=None, jpeg_kwargs=None):
        _write_tagged_image(os.path.join(self.set_dir, "raw", "shot1.3FR"),
                             **(raw_kwargs or {}))
        _write_tagged_image(os.path.join(self.set_dir, "jpeg", "shot1.jpg"),
                             **(jpeg_kwargs or {}))

    def test_valid_pair_passes(self):
        self._make_pair()
        self.assertEqual(verify_row(self.set_dir, self._row()), [])

    def test_missing_file_reported(self):
        _write_tagged_image(os.path.join(self.set_dir, "jpeg", "shot1.jpg"))
        problems = verify_row(self.set_dir, self._row())
        self.assertTrue(any("raw 파일 없음" in p for p in problems))

    def test_model_mismatch_reported(self):
        self._make_pair(jpeg_kwargs={"model": "X1D II 50C"})
        problems = verify_row(self.set_dir, self._row())
        self.assertTrue(any("불일치" in p for p in problems))

    def test_time_skew_beyond_tolerance_reported(self):
        self._make_pair(jpeg_kwargs={"datetime_original": "2026:07:01 12:05:00"})
        problems = verify_row(self.set_dir, self._row())
        self.assertTrue(any("같은 셔터가 아닐" in p for p in problems))

    def test_edited_jpeg_reported(self):
        self._make_pair(jpeg_kwargs={"software": "Adobe Lightroom Classic 13.0"})
        problems = verify_row(self.set_dir, self._row())
        self.assertTrue(any("편집 도구" in p for p in problems))

    def test_expected_make_defaults_to_hasselblad(self):
        self._make_pair(raw_kwargs={"make": "Leica"}, jpeg_kwargs={"make": "Leica"})
        problems = verify_row(self.set_dir, self._row())
        self.assertTrue(any("Hasselblad가 아님" in p for p in problems))

    def test_expected_make_leica_passes_leica_pair(self):
        self._make_pair(raw_kwargs={"make": "Leica"}, jpeg_kwargs={"make": "Leica"})
        problems = verify_row(self.set_dir, self._row(), expected_make="Leica")
        self.assertEqual(problems, [])

    def test_expected_make_leica_rejects_hasselblad_pair(self):
        self._make_pair()  # 기본값이 Hasselblad
        problems = verify_row(self.set_dir, self._row(), expected_make="Leica")
        self.assertTrue(any("Leica가 아님" in p for p in problems))


class TestHelpers(unittest.TestCase):
    def test_model_matches_ignores_spacing_and_case(self):
        self.assertTrue(_model_matches("X2D II 100C", "x2dii-100c"))
        self.assertFalse(_model_matches("X1D II 50C", "X2D II 100C"))
        self.assertFalse(_model_matches(None, "X2D II 100C"))

    def test_parse_exif_datetime_both_formats(self):
        self.assertIsNotNone(_parse_exif_datetime("2026:07:01 12:00:00"))
        self.assertIsNotNone(_parse_exif_datetime("2026-07-01T12:00:00"))
        self.assertIsNone(_parse_exif_datetime(None))
        self.assertIsNone(_parse_exif_datetime("garbage"))


if __name__ == "__main__":
    unittest.main()
