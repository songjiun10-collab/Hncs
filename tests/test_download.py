import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from tools.download import (_collect_files, _gdrive_extract_id,
                             download_fuji_pairs,
                             find_fuji_drive_links, ir_img_url,
                             list_gallery_images, resolve_full_image)


class TestIrImgUrl(unittest.TestCase):
    def test_prefers_lazy_src_over_src(self):
        attrs = ' src="placeholder.jpg" data-lazy-src="real.jpg" class="foo"'
        self.assertEqual(ir_img_url(attrs), "real.jpg")

    def test_falls_back_to_src_when_no_lazy_src(self):
        attrs = ' class="foo" src="real.jpg"'
        self.assertEqual(ir_img_url(attrs), "real.jpg")

    def test_returns_empty_string_when_neither_present(self):
        attrs = ' class="foo" alt="bar"'
        self.assertEqual(ir_img_url(attrs), "")


class TestListGalleryImages(unittest.TestCase):
    """ir_fetch()는 실제 네트워크 호출이라 mock으로 대체하고, 파싱+필터링
    로직(list_gallery_images의 실제 목적)만 검증한다."""

    def _gallery_html(self, entries):
        # entries: [(detail_path, img_attrs_html)]
        return "".join(
            f'<a href="{path}"><img{attrs}></a>' for path, attrs in entries
        )

    def test_extracts_detail_paths_and_dedupes(self):
        html = self._gallery_html([
            ("/cameras/foo/image/1?section=gallery", ' src="a.jpg" class="x"'),
            ("/cameras/foo/image/1?section=gallery", ' src="a.jpg" class="x"'),  # 중복
            ("/cameras/foo/image/2?section=gallery", ' src="b.jpg" class="x"'),
        ])
        with patch("tools.download.ir_fetch", return_value=html):
            result = list_gallery_images("http://example.com/gallery")
        self.assertEqual(result, ["/cameras/foo/image/1?section=gallery",
                                   "/cameras/foo/image/2?section=gallery"])

    def test_filters_by_skip_keyword_substring(self):
        html = self._gallery_html([
            ("/cameras/foo/image/1?section=gallery", ' src="normal.jpg" class="x"'),
            ("/cameras/foo/image/2?section=gallery", ' src="edited-mod.jpg" class="x"'),
        ])
        with patch("tools.download.ir_fetch", return_value=html):
            result = list_gallery_images("http://example.com/gallery", skip_keywords=("-mod",))
        self.assertEqual(result, ["/cameras/foo/image/1?section=gallery"])

    def test_filters_by_skip_pattern_regex(self):
        html = self._gallery_html([
            ("/cameras/foo/image/1?section=gallery", ' src="shot.jpg" class="x"'),
            ("/cameras/foo/image/2?section=gallery", ' src="shot-f2.8.jpg" class="x"'),
        ])
        import re
        with patch("tools.download.ir_fetch", return_value=html):
            result = list_gallery_images("http://example.com/gallery",
                                          skip_patterns=(re.compile(r"-f\d"),))
        self.assertEqual(result, ["/cameras/foo/image/1?section=gallery"])

    def test_skip_keyword_matching_is_case_insensitive_via_lowercasing(self):
        html = self._gallery_html([
            ("/cameras/foo/image/1?section=gallery", ' src="Shot-ISO-800.jpg" class="x"'),
        ])
        with patch("tools.download.ir_fetch", return_value=html):
            result = list_gallery_images("http://example.com/gallery", skip_keywords=("-iso-",))
        self.assertEqual(result, [])


class TestResolveFullImage(unittest.TestCase):
    def test_extracts_original_and_returns_none_when_no_match(self):
        html = ('<a href="https://media.example.com/full.jpg" target="_blank">'
                '<img src="thumb.jpg" class="attachment-full size-full"></a>')
        with patch("tools.download.ir_fetch", return_value=html):
            result = resolve_full_image("/cameras/foo/image/1")
        self.assertIsNotNone(result)
        original_url, scaled_url = result
        self.assertEqual(original_url, "https://media.example.com/full.jpg")

    def test_returns_none_when_pattern_absent(self):
        with patch("tools.download.ir_fetch", return_value="<html>no match here</html>"):
            result = resolve_full_image("/cameras/foo/image/1")
        self.assertIsNone(result)


class TestFindFujiDriveLinks(unittest.TestCase):
    def test_extracts_links_within_section(self):
        html = (
            "<p>intro</p>"
            "<p>SOOC JPG and RAW Samples to Download</p>"
            '<li><a href="https://drive.google.com/folder1"><strong>RAW</strong></a></li>'
            '<li><a href="https://drive.google.com/folder2"><strong>JPEG</strong></a></li>'
            "<hr>"
            '<li><a href="https://drive.google.com/folder3"><strong>Unrelated</strong></a></li>'
        )
        links = find_fuji_drive_links(html)
        self.assertEqual(links, [
            ("https://drive.google.com/folder1", "RAW"),
            ("https://drive.google.com/folder2", "JPEG"),
        ])

    def test_returns_empty_list_when_section_missing(self):
        self.assertEqual(find_fuji_drive_links("<html>nothing relevant</html>"), [])


class TestGdriveExtractId(unittest.TestCase):
    def test_folder_url(self):
        kind, drive_id = _gdrive_extract_id("https://drive.google.com/drive/folders/abc123")
        self.assertEqual((kind, drive_id), ("folder", "abc123"))

    def test_file_url(self):
        kind, drive_id = _gdrive_extract_id("https://drive.google.com/file/d/xyz789/view")
        self.assertEqual((kind, drive_id), ("file", "xyz789"))

    def test_open_id_url_is_unknown_kind(self):
        kind, drive_id = _gdrive_extract_id("https://drive.google.com/open?id=qqq111")
        self.assertEqual((kind, drive_id), ("unknown", "qqq111"))

    def test_unrecognized_url_raises(self):
        with self.assertRaises(ValueError):
            _gdrive_extract_id("https://example.com/not-a-drive-link")


class TestCollectFiles(unittest.TestCase):
    def test_filters_by_extension_case_insensitively_and_recurses(self):
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "sub")
            os.makedirs(sub)
            open(os.path.join(tmp, "a.jpg"), "w").close()
            open(os.path.join(tmp, "b.JPG"), "w").close()
            open(os.path.join(tmp, "c.txt"), "w").close()
            open(os.path.join(sub, "d.jpeg"), "w").close()

            files = _collect_files(tmp, {".jpg", ".jpeg"})
            basenames = sorted(os.path.basename(f) for f in files)
            self.assertEqual(basenames, ["a.jpg", "b.JPG", "d.jpeg"])


class TestDownloadFujiPairsMatching(unittest.TestCase):
    """download_fuji_pairs()가 정정(2026-08) 전엔 EXIF DateTimeOriginal
    문자열이 정확히 같은 raw 전부를 그 jpeg 하나에 중복 배정했다(진짜
    1:1이 아니었음, build_local_manifest의 페어 매칭 버그와 별개로 이
    함수 자체에 있던 버그) - build_local_manifest._match_pairs()로
    교체한 뒤 같은 타임스탬프 버스트에서도 1:1이 유지되는지 확인."""

    def test_same_timestamp_burst_produces_1to1_not_duplicated(self):
        raw_files = ["/cache/raw/A.RAF", "/cache/raw/B.RAF"]
        jpeg_files = ["/cache/jpeg/A.JPG", "/cache/jpeg/B.JPG"]

        # 둘 다 정확히 같은 초에 찍힌 것처럼(버스트) - 파일명은 우연히
        # 대응되지만 매칭 로직은 파일명을 안 보고 타임스탬프만 본다.
        exif_map = {
            "/cache/raw/A.RAF": ("2026:08:01 12:00:00", None),
            "/cache/raw/B.RAF": ("2026:08:01 12:00:00", None),
            "/cache/jpeg/A.JPG": ("2026:08:01 12:00:00", "Provia"),
            "/cache/jpeg/B.JPG": ("2026:08:01 12:00:00", "Velvia"),
        }

        with tempfile.TemporaryDirectory() as tmp:
            links_csv = os.path.join(tmp, "links.csv")
            manifest_path = os.path.join(tmp, "manifest.csv")
            with open(links_csv, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["camera", "gallery_url",
                                                   "raw_drive_url", "jpeg_drive_url"])
                w.writeheader()
                w.writerow(dict(camera="Fujifilm X-T3", gallery_url="", raw_drive_url="",
                                 jpeg_drive_url=""))

            with patch("tools.download.FUJI_LINKS_CSV", links_csv), \
                 patch("tools.download.FUJI_MANIFEST_PATH", manifest_path), \
                 patch("tools.download._gdrive_fetch", return_value=None), \
                 patch("tools.download._collect_files",
                       side_effect=lambda d, exts: raw_files if ".raf" in exts else jpeg_files), \
                 patch("tools.download.is_image_usable", return_value=True), \
                 patch("tools.download._exif_datetime_and_filmmode",
                       side_effect=lambda p: exif_map[p]):
                download_fuji_pairs()

            with open(manifest_path, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 2, "버스트 2쌍이 그대로 2행이어야 함(중복 배정 금지)")
        raw_paths = [row["raw_path"] for row in rows]
        jpeg_paths = [row["jpeg_path"] for row in rows]
        self.assertEqual(len(raw_paths), len(set(raw_paths)), "같은 raw가 두 번 쓰이면 안 됨")
        self.assertEqual(len(jpeg_paths), len(set(jpeg_paths)), "같은 jpeg가 두 번 쓰이면 안 됨(옛 버그)")


if __name__ == "__main__":
    unittest.main()
