import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from tools.analyze import BRAND_CONFIGS, _check_genuine_bytes
from tools.download import list_gallery_images


def _gallery_html(filenames):
    return "".join(
        f'<a href="/cameras/x/image/{i}?section=gallery"><img src="{name}" class="x"></a>'
        for i, name in enumerate(filenames)
    )


class TestBrandConfigFilters(unittest.TestCase):
    """BRAND_CONFIGS의 skip_keywords/skip_patterns가 각 브랜드 docstring/주석에
    적힌 실제 오염 사례(ISO 차트, 조리개 브라케팅, HDR on/off 비교샷 등)를
    걸러내는지 회귀 검증한다. 설정값을 고치다가 정규식/키워드가 깨지면
    population 표본이 다시 오염될 수 있어서(README 실측 기록에 이미 두 번
    벌어진 문제) 실제 BRAND_CONFIGS를 그대로 가져와 검증한다."""

    def _filtered(self, brand, filenames):
        cfg = BRAND_CONFIGS[brand]
        html = _gallery_html(filenames)
        with patch("tools.download.ir_fetch", return_value=html):
            return list_gallery_images("http://example.com/gallery",
                                        cfg["skip_keywords"], cfg["skip_patterns"])

    def test_phaseone_skips_iso_noise_test_chart(self):
        kept = self._filtered("phaseone", ["normal-shot.jpg", "chart-iso-1600.jpg"])
        self.assertEqual(kept, ["/cameras/x/image/0?section=gallery"])

    def test_pentax_skips_iso_noise_test_chart(self):
        kept = self._filtered("pentax", ["landscape.jpg", "test-iso-3200.jpg"])
        self.assertEqual(kept, ["/cameras/x/image/0?section=gallery"])

    def test_ricoh_gr_skips_aperture_bracketing_test_shots(self):
        kept = self._filtered("ricoh_gr", ["street.jpg", "chart-f2.8.jpg", "chart-f8.0.jpg"])
        self.assertEqual(kept, ["/cameras/x/image/0?section=gallery"])

    def test_ricoh_gr_skips_hdr_effect_comparison_shots(self):
        kept = self._filtered("ricoh_gr", ["scene.jpg", "scene-effect.jpg", "scene-no-effect.jpg"])
        self.assertEqual(kept, ["/cameras/x/image/0?section=gallery"])

    def test_leica_does_not_skip_genuine_photos(self):
        kept = self._filtered("leica", ["street-portrait.jpg", "cityscape.jpg"])
        self.assertEqual(len(kept), 2)

    def test_all_brand_configs_have_required_keys(self):
        required = {"galleries", "max_per_camera", "expected_keywords",
                    "reject_keywords", "skip_keywords", "skip_patterns",
                    "cache_dir", "result_csv"}
        for brand, cfg in BRAND_CONFIGS.items():
            with self.subTest(brand=brand):
                self.assertTrue(required.issubset(cfg.keys()))
                self.assertTrue(len(cfg["galleries"]) > 0)


class TestCheckGenuineBytes(unittest.TestCase):
    """GitHub 이슈 #4에서 지적된 문제(genuine_render_check이 run_hasselblad()엔
    안 걸려있었던 것)의 수정 - EXIF Software 태그로 Photoshop/Lightroom 편집을
    잡아내는지 회귀 검증. 리사이즈 전 원본 바이트에서 검사해야 하므로 실제
    exiftool로 Software 태그를 써넣은 JPEG 파일로 테스트한다."""

    def _jpeg_bytes_with_software(self, software):
        img = np.random.default_rng(0).integers(0, 256, (16, 16, 3), dtype=np.uint8)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            path = f.name
        try:
            cv2.imwrite(path, img)
            if software is not None:
                subprocess.run(["exiftool", "-overwrite_original", f"-Software={software}", path],
                                capture_output=True, timeout=30, check=True)
            with open(path, "rb") as f:
                return f.read()
        finally:
            os.remove(path)

    def test_no_software_tag_is_genuine(self):
        data = self._jpeg_bytes_with_software(None)
        self.assertTrue(_check_genuine_bytes(data))

    def test_photoshop_software_tag_is_rejected(self):
        data = self._jpeg_bytes_with_software("Adobe Photoshop 25.0")
        self.assertFalse(_check_genuine_bytes(data))

    def test_lightroom_software_tag_is_rejected(self):
        data = self._jpeg_bytes_with_software("Adobe Lightroom Classic 13.0")
        self.assertFalse(_check_genuine_bytes(data))

    def test_camera_firmware_version_string_is_genuine(self):
        # explorecams.com 검증에서 확인된 패턴 - 순수 버전 문자열은 편집 도구가
        # 아니라 카메라/Phocus 자체 렌더러 표시일 가능성이 높음
        data = self._jpeg_bytes_with_software("3.1.0")
        self.assertTrue(_check_genuine_bytes(data))


if __name__ == "__main__":
    unittest.main()
