import unittest
from unittest.mock import patch

from tools.analyze import BRAND_CONFIGS
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


if __name__ == "__main__":
    unittest.main()
