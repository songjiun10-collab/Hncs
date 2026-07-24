import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

from core.brand_classifier import (
    load_signatures, extract_features, standardize, nearest_centroid_loo,
)


def _write_signature_json(path, n_images, per_image):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"methodology": "test", "n_images": n_images, "population": {}, "per_image": per_image}, f)


def _write_full_fake_brand(brand_dir, tone_records, color_records, gamut_records, texture_records, n_images=None):
    os.makedirs(brand_dir, exist_ok=True)
    n = n_images if n_images is not None else len(tone_records)
    _write_signature_json(os.path.join(brand_dir, "tone_signature.json"), n, tone_records)
    _write_signature_json(os.path.join(brand_dir, "color_signature.json"), n, color_records)
    _write_signature_json(os.path.join(brand_dir, "gamut_signature.json"), n, gamut_records)
    _write_signature_json(os.path.join(brand_dir, "texture_signature.json"), n, texture_records)


_TONE_A = {"filename": "a.jpg", "b2": 1.0, "w995": 2.0, "median": 3.0, "dark_pct": 0.1}
_TONE_B = {"filename": "b.jpg", "b2": 4.0, "w995": 5.0, "median": 6.0, "dark_pct": 0.2}
_COLOR_A = {"filename": "a.jpg", "sat_mean": 10.0, "hue_mean": 20.0}
_COLOR_B = {"filename": "b.jpg", "sat_mean": 30.0, "hue_mean": 40.0}
_GAMUT_A = {"filename": "a.jpg", "a_p1": 1.0, "a_p99": 2.0, "b_p1": 3.0, "b_p99": 4.0,
            "a_std": 1.0, "b_std": 1.0, "chroma_mean": 5.0, "chroma_p99": 6.0}
_GAMUT_B = {"filename": "b.jpg", "a_p1": 1.0, "a_p99": 2.0, "b_p1": 3.0, "b_p99": 4.0,
            "a_std": 1.0, "b_std": 1.0, "chroma_mean": 5.0, "chroma_p99": 6.0}
_TEXTURE_A = {"filename": "a.jpg", "sharpening": 1.0, "micro_contrast": 2.0, "noise": 0.01,
              "n_edges": 10, "overshoot": 1.0, "undershoot": 1.0}
_TEXTURE_B = {"filename": "b.jpg", "sharpening": 1.0, "micro_contrast": 2.0, "noise": 0.01,
              "n_edges": 10, "overshoot": 1.0, "undershoot": 1.0}


class TestLoadSignatures(unittest.TestCase):
    def test_joins_four_files_on_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand_dir = os.path.join(tmp, "fakebrand")
            _write_full_fake_brand(brand_dir, [_TONE_A, _TONE_B], [_COLOR_A, _COLOR_B],
                                    [_GAMUT_A, _GAMUT_B], [_TEXTURE_A, _TEXTURE_B])

            records = load_signatures("fakebrand", datasets_dir=tmp)

            self.assertEqual(len(records), 2)
            by_name = {r["filename"]: r for r in records}
            self.assertEqual(by_name["a.jpg"]["b2"], 1.0)
            self.assertEqual(by_name["a.jpg"]["sat_mean"], 10.0)
            self.assertEqual(by_name["a.jpg"]["a_p1"], 1.0)
            self.assertEqual(by_name["a.jpg"]["sharpening"], 1.0)

    def test_warns_on_filename_mismatch_and_uses_intersection(self):
        with tempfile.TemporaryDirectory() as tmp:
            brand_dir = os.path.join(tmp, "fakebrand")
            # color_signature에는 b.jpg가 없음 - 교집합은 a.jpg 하나뿐
            _write_full_fake_brand(brand_dir, [_TONE_A, _TONE_B], [_COLOR_A],
                                    [_GAMUT_A, _GAMUT_B], [_TEXTURE_A, _TEXTURE_B], n_images=2)

            buf = io.StringIO()
            with redirect_stdout(buf):
                records = load_signatures("fakebrand", datasets_dir=tmp)

            self.assertEqual(len(records), 1)
            self.assertIn("불일치", buf.getvalue())


class TestExtractFeatures(unittest.TestCase):
    def _sample_record(self, **overrides):
        rec = {
            "filename": "a.jpg", "npix": 12345678, "is_portrait": True,
            "quality": 90, "subsampling": "4:2:0",
            "b2": 1.0, "w995": 2.0, "median": 3.0, "dark_pct": 0.1,
            "sat_mean": 50.0, "hue_mean": 30.0,
            "a_p1": 1.0, "a_p99": 2.0, "b_p1": 3.0, "b_p99": 4.0,
            "a_std": 1.0, "b_std": 1.0, "chroma_mean": 5.0, "chroma_p99": 6.0,
            "sharpening": 1.0, "micro_contrast": 2.0, "noise": 0.01,
            "n_edges": 10, "overshoot": 1.0, "undershoot": 1.0,
        }
        rec.update(overrides)
        return rec

    def test_set_a_shape_and_names(self):
        X, names = extract_features([self._sample_record()], feature_set="tone_color_gamut")
        self.assertEqual(X.shape, (1, 15))
        self.assertEqual(len(names), 15)

    def test_set_b_shape_and_names(self):
        X, names = extract_features([self._sample_record()], feature_set="all")
        self.assertEqual(X.shape, (1, 21))
        self.assertEqual(len(names), 21)

    def test_excluded_fields_never_appear(self):
        for feature_set in ["tone_color_gamut", "all"]:
            _, names = extract_features([self._sample_record()], feature_set=feature_set)
            for excluded in ["npix", "is_portrait", "quality", "subsampling", "filename", "hue_mean"]:
                self.assertNotIn(excluded, names)
            self.assertIn("hue_cos", names)
            self.assertIn("hue_sin", names)

    def test_unknown_feature_set_raises(self):
        with self.assertRaises(ValueError):
            extract_features([self._sample_record()], feature_set="bogus")

    def test_circular_hue_wraps_correctly(self):
        records = [
            self._sample_record(filename="a.jpg", hue_mean=359.0),
            self._sample_record(filename="b.jpg", hue_mean=1.0),
            self._sample_record(filename="c.jpg", hue_mean=180.0),
        ]
        X, names = extract_features(records, feature_set="tone_color_gamut")
        cos_i, sin_i = names.index("hue_cos"), names.index("hue_sin")
        dist_359_to_1 = np.linalg.norm(X[0][[cos_i, sin_i]] - X[1][[cos_i, sin_i]])
        dist_359_to_180 = np.linalg.norm(X[0][[cos_i, sin_i]] - X[2][[cos_i, sin_i]])
        self.assertLess(dist_359_to_1, dist_359_to_180)

    def test_empty_records_returns_correct_2d_shape(self):
        X, names = extract_features([], feature_set="tone_color_gamut")
        self.assertEqual(X.shape, (0, 15))
        self.assertEqual(len(names), 15)

        X, names = extract_features([], feature_set="all")
        self.assertEqual(X.shape, (0, 21))
        self.assertEqual(len(names), 21)


class TestStandardize(unittest.TestCase):
    def test_zero_variance_column_does_not_divide_by_zero(self):
        train_X = np.array([[1.0, 5.0], [1.0, 7.0], [1.0, 9.0]])
        vector = np.array([1.0, 6.0])
        z = standardize(train_X, vector)
        self.assertTrue(np.isfinite(z).all())
        self.assertEqual(z[0], 0.0)


class TestNearestCentroidLoo(unittest.TestCase):
    def test_excludes_held_out_sample_from_own_brand_centroid(self):
        # 브랜드 A: [0.0, 1000.0]("1000.0"은 A의 이상치이자 held-out 대상)
        # 브랜드 B: [200.0, 202.0]
        # 자기 자신을 제외하면 A의 centroid는 0.0뿐이라, held-out(1000.0)은
        # B의 centroid(~201)에 훨씬 더 가까워서 "B"로 (오)분류되는 게 정답.
        # 만약 구현이 held-out 샘플을 자기 브랜드 centroid에 leak시키면
        # (mean([0,1000])=500), 그쪽이 더 가까워져서 "A"로 잘못 예측됨 -
        # 이 assert가 그 리키지 버그를 정확히 잡아낸다.
        X = np.array([[0.0], [1000.0], [200.0], [202.0]])
        y = np.array(["A", "A", "B", "B"])
        predictions = nearest_centroid_loo(X, y)
        self.assertEqual(predictions[1], "B")

    def test_excludes_held_out_sample_from_standardization_stats(self):
        # 위 테스트는 centroid 리키지만 잡아내고 표준화 통계(mean/std)
        # 리키지는 통과시켜버린다(mean/std 계산이 실수로 폴드 루프 밖으로
        # hoist되어 train_X 대신 전체 X로 계산돼도 이 데이터로는 걸리지
        # 않음). 이 테스트는 표준화 통계 리키지만 따로 잡아내도록 설계됨 -
        # 두 변형 모두에서 centroid는 항상 train_X로만 계산되고(누출 없음),
        # mean/std만 다르게 계산됐을 때 예측이 달라지는 데이터셋을 씀.
        #
        # 2피처 데이터. held-out(인덱스 0, 브랜드 A) = [-13, -9]는
        # feature0에서 극단적 이상치다 - 학습 폴드(나머지 3개)의
        # feature0 값은 [11, 11, 12]로 좁게 몰려있다.
        #
        # 올바르게 held-out을 제외한 학습 폴드만으로 mean/std를 구하면
        # feature0의 std가 아주 작아서(~0.47) feature0의 z-score 거리가
        # 두 센트로이드(A=[11,11], B=[11.5,-0.5]) 모두에 대해 ~51로
        # 거대하고 서로 거의 같아진다 -> 승부는 feature1이 가르는데,
        # held-out은 feature1에서 B centroid(z=-0.55)보다 A centroid
        # (z=1.09)에 훨씬 가까워서 정답 "A"로 올바르게 분류된다
        # (dist_A=50.99 < dist_B=51.99).
        #
        # 만약 mean/std가 held-out 자신을 포함한 전체 X에서 새어나온다면
        # feature0의 std가 0.47 -> 10.5로 부풀려지면서 feature0 z-score의
        # 영향력이 feature1과 비슷한 스케일로 줄어들고, 그 결과 균형이
        # 뒤집혀 "B"로 잘못 예측된다(dist_A=3.36 > dist_B=2.55). 이
        # assert가 그 표준화 통계 리키지 버그를 정확히 잡아낸다.
        X = np.array([[-13.0, -9.0], [11.0, 5.0], [11.0, 11.0], [12.0, -6.0]])
        y = np.array(["A", "B", "A", "B"])
        predictions = nearest_centroid_loo(X, y)
        self.assertEqual(predictions[0], "A")

    def test_well_separated_clusters_get_high_accuracy(self):
        rng = np.random.default_rng(0)
        cluster_a = rng.normal(loc=[0.0, 0.0], scale=0.5, size=(20, 2))
        cluster_b = rng.normal(loc=[50.0, 50.0], scale=0.5, size=(20, 2))
        cluster_c = rng.normal(loc=[-50.0, 50.0], scale=0.5, size=(20, 2))
        X = np.vstack([cluster_a, cluster_b, cluster_c])
        y = np.array(["A"] * 20 + ["B"] * 20 + ["C"] * 20)

        predictions = nearest_centroid_loo(X, y)

        accuracy = float((predictions == y).mean())
        self.assertGreater(accuracy, 0.95)


if __name__ == "__main__":
    unittest.main()
