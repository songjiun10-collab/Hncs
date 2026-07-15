"""
datasets/<brand>/texture_signature.json 전체를 훑어서 명백한 스케일/단위
버그를 잡는 회귀 테스트. Sony의 sharpening이 원래 스케일 없는 Sobel std를
그대로 써서 다른 브랜드보다 15~20배 크게 나왔던 사고(이 세션에서 발견,
/15로 재계산해서 수정)가 재발하는 걸 막기 위한 가드레일 - 새 브랜드를
추가하는 에이전트가 sharpening/micro_contrast 공식을 잘못 재정의해도
이 테스트가 커밋 전에 잡아준다.

경계값은 "정확한 정답"이 아니라 지금까지 실측된 값들(README/각 브랜드
texture_signature.json 참고)에 여유를 넉넉히 둔 것 - Sigma의 noise=2.0처럼
브랜드 고유의 진짜 신호(Foveon 센서가 Bayer보다 노이즈가 많다는 건 사진
커뮤니티에서 잘 알려진 특성)까지 잘못 걸러내지 않으면서, Sony 사고 수준의
자릿수 오류(15~20배)만 잡을 정도로 느슨하게 잡았다.
"""
import glob
import json
import os
import unittest

DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")


def _load_all_texture_signatures():
    result = {}
    for path in sorted(glob.glob(os.path.join(DATASETS_DIR, "*", "texture_signature.json"))):
        brand = os.path.basename(os.path.dirname(path))
        with open(path, encoding="utf-8") as f:
            result[brand] = json.load(f)
    return result


class TestTextureSignatureConsistency(unittest.TestCase):
    def setUp(self):
        self.signatures = _load_all_texture_signatures()
        # 이 프로젝트가 population-fit 브랜드를 계속 늘려온 이력상 최소
        # 이 정도는 있어야 함 - 브랜드가 하나도 안 잡히면 glob 경로가
        # 깨졌다는 신호라 그 자체로 실패해야 함
        self.assertGreaterEqual(len(self.signatures), 10)

    def test_n_images_matches_per_image_length(self):
        for brand, d in self.signatures.items():
            with self.subTest(brand=brand):
                self.assertEqual(d["n_images"], len(d["per_image"]))
                self.assertEqual(d["n_images"], d["population"]["sharpening"]["n"])

    def test_sharpening_within_sane_cross_brand_range(self):
        # Canon 공식(Sobel gradient magnitude std / 15) 재사용이 관례라
        # 전 브랜드가 비슷한 자릿수여야 함 - Sony 사고(약 55, 15~20배 과다)
        # 재발 시 이 상한(15)에 걸림
        for brand, d in self.signatures.items():
            mean = d["population"]["sharpening"]["mean"]
            with self.subTest(brand=brand):
                self.assertGreater(mean, 0, f"{brand} sharpening mean은 양수여야 함")
                self.assertLess(mean, 15, f"{brand} sharpening mean={mean:.2f} - Sony 스케일 버그와 같은 "
                                           f"자릿수 오류 의심 (다른 브랜드는 전부 0.5~4.5대)")

    def test_micro_contrast_within_sane_cross_brand_range(self):
        # DoG sigma pair가 브랜드군마다 달라(1,2 vs 1,4 추정) 자릿수 자체는
        # 8~12대/3.6~4.5대로 갈리지만, 그래도 스케일 버그(수십~수백대)와는
        # 구분되는 느슨한 상한만 건다
        for brand, d in self.signatures.items():
            mean = d["population"]["micro_contrast"]["mean"]
            with self.subTest(brand=brand):
                self.assertGreater(mean, 0, f"{brand} micro_contrast mean은 양수여야 함")
                self.assertLess(mean, 30, f"{brand} micro_contrast mean={mean:.2f} - 스케일 버그 의심")

    def test_noise_within_sane_cross_brand_range(self):
        for brand, d in self.signatures.items():
            mean = d["population"]["noise"]["mean"]
            with self.subTest(brand=brand):
                self.assertGreaterEqual(mean, 0, f"{brand} noise mean은 음수일 수 없음")
                self.assertLess(mean, 10, f"{brand} noise mean={mean:.2f} - 다른 브랜드(전부 10 미만)와 "
                                          f"자릿수가 다름, 스케일 버그 의심")

    def test_methodology_field_is_nonempty_string(self):
        for brand, d in self.signatures.items():
            with self.subTest(brand=brand):
                self.assertIsInstance(d["methodology"], str)
                self.assertGreater(len(d["methodology"]), 50)


if __name__ == "__main__":
    unittest.main()
