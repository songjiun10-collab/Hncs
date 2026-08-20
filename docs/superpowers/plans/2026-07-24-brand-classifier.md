# 브랜드 시그니처 판별기 (연구용 검증) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 11개 브랜드의 이미 계산된 population 시그니처(`datasets/<brand>/*_signature.json`)만으로 leave-one-out nearest-centroid 분류기를 만들어, 그 시그니처 데이터가 브랜드를 실제로 구별할 만큼 결정력이 있는지 정직하게 검증한다.

**Architecture:** `core/brand_classifier.py`(순수 numpy 함수: 로딩/조인 → 피처 추출 → 표준화 → LOO 분류 → confusion matrix/리포트)와 이를 감싸는 `tools/classify_brand.py` CLI 두 층으로 나눈다. 새 사진 입력은 스코프 밖 - 오직 933장 기존 데이터로만 동작.

**Tech Stack:** Python 표준 라이브러리 + numpy만 사용(새 의존성 없음). 테스트는 `unittest`(프로젝트 관례, pytest 미사용).

## Global Constraints

- 새 의존성 추가 금지 - `core/brand_classifier.py`는 numpy만 사용.
- 테스트는 `unittest.TestCase` 스타일로 작성(`tests/` 기존 파일들과 동일한 관례) - pytest 픽스처(`tmp_path`, `capsys` 등) 사용 금지, `tempfile.TemporaryDirectory()`/`contextlib.redirect_stdout` + `io.StringIO`로 대체.
- 피처에서 명시적으로 제외: `npix`, `is_portrait`, `quality`, `subsampling`, `filename`, 그리고 raw `hue_mean`(원형 변환된 `hue_cos`/`hue_sin`으로 대체되고 원본 키는 피처 이름에 안 남음).
- Feature Set A(`feature_set="tone_color_gamut"`, 기본값) = tone(4) + `sat_mean`(1) + gamut(8) + hue_cos/hue_sin(2) = 15차원. Feature Set B(`feature_set="all"`) = Set A + texture(6) = 21차원.
- Leave-one-out은 매 폴드마다 held-out 샘플을 표준화 통계와 자기 브랜드 centroid 양쪽에서 완전히 제외해야 한다(리키지 금지 - Task 3의 회귀 테스트로 고정).
- 이번 플랜은 새 사진을 입력받아 브랜드를 예측하는 기능을 만들지 않는다(스펙의 "범위 밖" 그대로).
- 각 태스크 종료 시 `python3 -m unittest discover -s tests`가 그린이어야 한다.
- 문서는 README.md/README.ko.md 둘 다, `docs/project_structure.md`/`.en.md` 둘 다 갱신(이 프로젝트의 이중언어 동시 유지 관례).

---

### Task 1: 시그니처 로딩 및 조인 (`load_signatures`)

**Files:**
- Create: `core/brand_classifier.py`
- Test: `tests/test_brand_classifier.py`

**Interfaces:**
- Produces: `load_signatures(brand: str, datasets_dir: str = DATASETS_DIR) -> list[dict]` - 4개 시그니처 JSON을 `filename`으로 inner join한 레코드 리스트. 각 레코드는 `{"filename": ..., "b2": ..., "w995": ..., "median": ..., "dark_pct": ..., "sat_mean": ..., "hue_mean": ..., "skin_hue": ...(optional), "a_p1": ..., "a_p99": ..., "b_p1": ..., "b_p99": ..., "a_std": ..., "b_std": ..., "chroma_mean": ..., "chroma_p99": ..., "sharpening": ..., "micro_contrast": ..., "noise": ..., "n_edges": ..., "overshoot": ..., "undershoot": ..., "npix": ..., "is_portrait": ..., "quality": ..., "subsampling": ...}` (원본 4개 파일의 필드가 전부 섞여 들어옴).
- Produces: `BRANDS: list[str]` = `["hasselblad", "canon", "leica", "nikon", "olympus", "panasonic", "pentax", "phaseone", "ricoh_gr", "sigma", "sony"]`
- Produces: `TONE_FIELDS`, `COLOR_FIELDS`, `GAMUT_FIELDS`, `TEXTURE_FIELDS` 상수(Task 2가 사용).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_brand_classifier.py` 새로 작성:

```python
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

from core.brand_classifier import load_signatures


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `ModuleNotFoundError: No module named 'core.brand_classifier'` (또는 `ImportError`)

- [ ] **Step 3: 최소 구현 작성**

`core/brand_classifier.py` 새로 작성:

```python
"""11개 population-fit 브랜드의 이미 계산된 시그니처(datasets/<brand>/
*_signature.json)만으로 브랜드 판별력을 검증하는 연구용 도구.
새 사진을 입력받아 예측하는 기능은 없음 - 순수하게 "이 시그니처 데이터가
브랜드를 실제로 구별할 만큼 결정력이 있는가"를 leave-one-out
교차검증으로 확인하는 게 목적. 설계 근거는
docs/superpowers/specs/2026-07-24-brand-classifier-design.md 참고."""
import json
import os

import numpy as np

DATASETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets")

BRANDS = [
    "hasselblad", "canon", "leica", "nikon", "olympus", "panasonic",
    "pentax", "phaseone", "ricoh_gr", "sigma", "sony",
]

TONE_FIELDS = ["b2", "w995", "median", "dark_pct"]
COLOR_FIELDS = ["sat_mean", "hue_mean"]
GAMUT_FIELDS = ["a_p1", "a_p99", "b_p1", "b_p99", "a_std", "b_std", "chroma_mean", "chroma_p99"]
TEXTURE_FIELDS = ["sharpening", "micro_contrast", "noise", "n_edges", "overshoot", "undershoot"]

_SIGNATURE_FILES = [
    "tone_signature.json", "color_signature.json", "gamut_signature.json", "texture_signature.json",
]


def load_signatures(brand, datasets_dir=DATASETS_DIR):
    """brand의 4개 시그니처 JSON(per_image 배열)을 filename으로 inner
    join해서 레코드 리스트를 반환. 4개 파일의 파일셋이 n_images 선언값과
    다르면(즉 조인 후 교집합이 더 작으면) 경고를 출력한다."""
    brand_dir = os.path.join(datasets_dir, brand)
    per_file = {}
    n_images_declared = None
    for fname in _SIGNATURE_FILES:
        path = os.path.join(brand_dir, fname)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if n_images_declared is None:
            n_images_declared = data.get("n_images")
        per_file[fname] = {rec["filename"]: rec for rec in data["per_image"]}

    common_filenames = set(per_file[_SIGNATURE_FILES[0]])
    for fname in _SIGNATURE_FILES[1:]:
        common_filenames &= set(per_file[fname])

    if n_images_declared is not None and len(common_filenames) != n_images_declared:
        print(
            f"경고: {brand} - 시그니처 파일 4개 조인 결과 {len(common_filenames)}장, "
            f"n_images 선언값 {n_images_declared}장과 불일치"
        )

    records = []
    for filename in sorted(common_filenames):
        merged = {"filename": filename}
        for fname in _SIGNATURE_FILES:
            merged.update(per_file[fname][filename])
        records.append(merged)
    return records
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `OK` (2 tests)

- [ ] **Step 5: 커밋**

```bash
git add core/brand_classifier.py tests/test_brand_classifier.py
git commit -m "Add load_signatures(): join the 4 per-brand signature JSONs on filename"
```

---

### Task 2: 피처 추출 (`extract_features`)

**Files:**
- Modify: `core/brand_classifier.py`
- Modify: `tests/test_brand_classifier.py`

**Interfaces:**
- Consumes: Task 1의 `TONE_FIELDS`/`COLOR_FIELDS`/`GAMUT_FIELDS`/`TEXTURE_FIELDS`, `load_signatures()`가 반환하는 레코드 형태.
- Produces: `extract_features(records: list[dict], feature_set: str = "tone_color_gamut") -> tuple[np.ndarray, list[str]]` - `feature_set`은 `"tone_color_gamut"`(Set A, 15차원) 또는 `"all"`(Set B, 21차원). 반환값 `X`는 `(len(records), D)` float64 배열, `feature_names`는 길이 `D`인 문자열 리스트(순서: tone 4개 → `sat_mean` → gamut 8개 → [texture 6개, `all`일 때만] → `hue_cos` → `hue_sin`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_brand_classifier.py`에 추가:

```python
from core.brand_classifier import load_signatures, extract_features  # 상단 import 갱신


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `AttributeError` 또는 `ImportError` - `extract_features`가 아직 없음

- [ ] **Step 3: 구현 작성**

`core/brand_classifier.py`에 `load_signatures()` 다음에 추가:

```python
def extract_features(records, feature_set="tone_color_gamut"):
    """records(load_signatures 반환값)에서 (N, D) 피처 행렬과 피처
    이름 리스트를 만든다. hue_mean은 원형 변수라 (cos, sin) 2차원으로
    변환한다(359도와 1도가 raw z-score로는 최대로 멀게 취급되는 문제를
    피하기 위함). npix/is_portrait/quality/subsampling은 색감과 무관한
    메타데이터라 의도적으로 제외."""
    if feature_set == "tone_color_gamut":
        scalar_fields = TONE_FIELDS + ["sat_mean"] + GAMUT_FIELDS
    elif feature_set == "all":
        scalar_fields = TONE_FIELDS + ["sat_mean"] + GAMUT_FIELDS + TEXTURE_FIELDS
    else:
        raise ValueError(f"알 수 없는 feature_set: {feature_set} (tone_color_gamut 또는 all)")

    feature_names = list(scalar_fields) + ["hue_cos", "hue_sin"]
    rows = []
    for rec in records:
        values = [float(rec[field]) for field in scalar_fields]
        hue_rad = np.deg2rad(rec["hue_mean"])
        values.append(float(np.cos(hue_rad)))
        values.append(float(np.sin(hue_rad)))
        rows.append(values)
    X = np.array(rows, dtype=np.float64)
    return X, feature_names
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `OK` (7 tests)

- [ ] **Step 5: 커밋**

```bash
git add core/brand_classifier.py tests/test_brand_classifier.py
git commit -m "Add extract_features(): Set A/B feature vectors with circular hue encoding"
```

---

### Task 3: 표준화 + LOO nearest-centroid 분류 (`standardize`, `nearest_centroid_loo`)

**Files:**
- Modify: `core/brand_classifier.py`
- Modify: `tests/test_brand_classifier.py`

**Interfaces:**
- Produces: `standardize(train_X: np.ndarray, vector: np.ndarray) -> np.ndarray` - `train_X`의 열별 평균/표준편차로 `vector`를 z-score 표준화. 표준편차가 0인 열은 결과를 0으로 고정(분산 없는 피처는 판별에 기여 안 함, 0-division 방지).
- Produces: `nearest_centroid_loo(X: np.ndarray, y: np.ndarray) -> np.ndarray` - `X` shape `(N, D)`, `y` shape `(N,)`(브랜드 문자열 배열, `BRANDS`에 한정되지 않는 임의 라벨 지원). 매 폴드마다 held-out 샘플 `i`를 표준화 통계와 자기 브랜드 centroid 양쪽에서 제외하고, 표준화 공간에서 유클리드 거리가 최소인 브랜드로 예측한 라벨 배열 `(N,)`을 반환.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_brand_classifier.py`에 추가:

```python
from core.brand_classifier import (  # 상단 import 갱신
    load_signatures, extract_features, standardize, nearest_centroid_loo,
)


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `AttributeError` - `standardize`/`nearest_centroid_loo`가 아직 없음

- [ ] **Step 3: 구현 작성**

`core/brand_classifier.py`에 `extract_features()` 다음에 추가:

```python
def standardize(train_X, vector):
    """train_X의 열별 평균/표준편차로 vector를 z-score 표준화. 표준편차가
    0인 열(분산 없는 피처)은 나눗셈 대신 0을 반환 - 판별에 기여할 정보가
    없는 피처로 취급."""
    mean = train_X.mean(axis=0)
    std = train_X.std(axis=0)
    std_safe = np.where(std == 0, 1.0, std)
    z = (vector - mean) / std_safe
    return np.where(std == 0, 0.0, z)


def nearest_centroid_loo(X, y):
    """leave-one-out 표준화 거리 nearest-centroid 분류. 매 폴드마다
    held-out 샘플 i를 표준화 기준 통계와 자기 브랜드 centroid 양쪽에서
    완전히 제외한다(리키지 방지 - test_excludes_held_out_sample_from_own_
    brand_centroid 참고)."""
    y = np.asarray(y)
    n = X.shape[0]
    predictions = np.empty(n, dtype=y.dtype)
    all_indices = np.arange(n)

    for i in range(n):
        keep = all_indices != i
        train_X = X[keep]
        train_y = y[keep]
        z = standardize(train_X, X[i])

        best_brand = None
        best_dist = None
        for brand in np.unique(train_y):
            centroid_raw = train_X[train_y == brand].mean(axis=0)
            centroid_z = standardize(train_X, centroid_raw)
            dist = float(np.linalg.norm(z - centroid_z))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_brand = brand
        predictions[i] = best_brand

    return predictions
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `OK` (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add core/brand_classifier.py tests/test_brand_classifier.py
git commit -m "Add standardize() + nearest_centroid_loo() with a leakage regression test"
```

---

### Task 4: Confusion matrix + 리포트 (`confusion_matrix`, `classification_report`)

**Files:**
- Modify: `core/brand_classifier.py`
- Modify: `tests/test_brand_classifier.py`

**Interfaces:**
- Consumes: Task 3의 `nearest_centroid_loo()`가 반환하는 예측 라벨 배열.
- Produces: `confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, brands: list[str] = BRANDS) -> np.ndarray` - shape `(len(brands), len(brands))` int 배열, 행=실제, 열=예측.
- Produces: `classification_report(y_true: np.ndarray, y_pred: np.ndarray, brands: list[str] = BRANDS) -> dict` - 키: `"per_brand"`(브랜드별 `{"precision", "recall", "f1", "n"}` 딕셔너리), `"accuracy"`(전체 정확도), `"macro_accuracy"`(브랜드별 recall의 비가중 평균 = balanced accuracy), `"majority_baseline"`, `"uniform_baseline"`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_brand_classifier.py`에 추가:

```python
from core.brand_classifier import (  # 상단 import 갱신
    load_signatures, extract_features, standardize, nearest_centroid_loo,
    confusion_matrix, classification_report,
)


class TestConfusionMatrix(unittest.TestCase):
    def test_counts_correctly(self):
        y_true = np.array(["A", "A", "B", "B", "B"])
        y_pred = np.array(["A", "B", "B", "B", "A"])
        matrix = confusion_matrix(y_true, y_pred, brands=["A", "B"])
        np.testing.assert_array_equal(matrix, np.array([[1, 1], [1, 2]]))


class TestClassificationReport(unittest.TestCase):
    def test_metrics_and_baselines(self):
        # 브랜드 A: 3개(예측 A,A,B) / 브랜드 B: 1개(예측 B)
        y_true = np.array(["A", "A", "A", "B"])
        y_pred = np.array(["A", "A", "B", "B"])
        report = classification_report(y_true, y_pred, brands=["A", "B"])

        self.assertAlmostEqual(report["accuracy"], 3 / 4)
        self.assertAlmostEqual(report["per_brand"]["A"]["recall"], 2 / 3)
        self.assertAlmostEqual(report["per_brand"]["A"]["precision"], 1.0)
        self.assertEqual(report["per_brand"]["A"]["n"], 3)
        self.assertAlmostEqual(report["per_brand"]["B"]["recall"], 1.0)
        self.assertAlmostEqual(report["macro_accuracy"], (2 / 3 + 1.0) / 2)
        self.assertAlmostEqual(report["majority_baseline"], 3 / 4)
        self.assertAlmostEqual(report["uniform_baseline"], 0.5)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `AttributeError` - `confusion_matrix`/`classification_report`가 아직 없음

- [ ] **Step 3: 구현 작성**

`core/brand_classifier.py`에 `nearest_centroid_loo()` 다음에 추가:

```python
def confusion_matrix(y_true, y_pred, brands=BRANDS):
    """brands 순서로 정렬된 (len(brands), len(brands)) confusion matrix.
    matrix[i, j] = 실제 브랜드가 brands[i]인데 brands[j]로 예측된 개수."""
    index = {b: i for i, b in enumerate(brands)}
    matrix = np.zeros((len(brands), len(brands)), dtype=int)
    for true_label, pred_label in zip(y_true, y_pred):
        matrix[index[true_label], index[pred_label]] += 1
    return matrix


def classification_report(y_true, y_pred, brands=BRANDS):
    """브랜드별 precision/recall/f1/표본수와 두 baseline(다수결,
    균등확률), 그리고 전체 정확도(accuracy)와 브랜드별 recall의 비가중
    평균(macro_accuracy = balanced accuracy, 표본 불균형에 영향받지
    않음)을 담은 딕셔너리를 반환."""
    matrix = confusion_matrix(y_true, y_pred, brands=brands)

    per_brand = {}
    for i, brand in enumerate(brands):
        n = int(matrix[i].sum())
        tp = int(matrix[i, i])
        predicted_as_brand = int(matrix[:, i].sum())
        recall = tp / n if n > 0 else 0.0
        precision = tp / predicted_as_brand if predicted_as_brand > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
        per_brand[brand] = {"precision": precision, "recall": recall, "f1": f1, "n": n}

    total = int(matrix.sum())
    accuracy = float(np.trace(matrix)) / total if total > 0 else 0.0
    macro_accuracy = float(np.mean([per_brand[b]["recall"] for b in brands]))
    counts = matrix.sum(axis=1)
    majority_baseline = float(counts.max()) / total if total > 0 else 0.0
    uniform_baseline = 1.0 / len(brands)

    return {
        "per_brand": per_brand,
        "accuracy": accuracy,
        "macro_accuracy": macro_accuracy,
        "majority_baseline": majority_baseline,
        "uniform_baseline": uniform_baseline,
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `OK` (12 tests)

- [ ] **Step 5: 커밋**

```bash
git add core/brand_classifier.py tests/test_brand_classifier.py
git commit -m "Add confusion_matrix() + classification_report() with majority/uniform baselines"
```

---

### Task 5: CLI (`tools/classify_brand.py`)

**Files:**
- Create: `tools/classify_brand.py`

**Interfaces:**
- Consumes: `core.brand_classifier.BRANDS`, `load_signatures`, `extract_features`, `nearest_centroid_loo`, `confusion_matrix`, `classification_report` (Tasks 1-4).

- [ ] **Step 1: CLI 작성**

`tools/classify_brand.py` 새로 작성:

```python
"""브랜드 시그니처 판별기 CLI - 11개 브랜드의 이미 계산된 population
시그니처(datasets/*/*_signature.json)만으로 leave-one-out 교차검증 기반
nearest-centroid 분류를 돌려서 confusion matrix와 지표를 출력한다.
연구용 검증 도구 - 새 사진을 넣어 예측하는 기능은 없음
(docs/superpowers/specs/2026-07-24-brand-classifier-design.md 참고)."""
import argparse
import csv

import numpy as np

from core.brand_classifier import (
    BRANDS, load_signatures, extract_features, nearest_centroid_loo,
    confusion_matrix, classification_report,
)


def run(feature_set):
    all_X = []
    all_y = []
    for brand in BRANDS:
        records = load_signatures(brand)
        X, _ = extract_features(records, feature_set=feature_set)
        all_X.append(X)
        all_y.extend([brand] * len(records))
    X = np.concatenate(all_X, axis=0)
    y = np.array(all_y)

    predictions = nearest_centroid_loo(X, y)
    matrix = confusion_matrix(y, predictions, brands=BRANDS)
    report = classification_report(y, predictions, brands=BRANDS)
    return matrix, report


def print_report(matrix, report, feature_set):
    print(f"=== feature_set={feature_set} ===")
    header = "true\\pred".ljust(12) + "".join(b[:8].rjust(9) for b in BRANDS)
    print(header)
    for i, brand in enumerate(BRANDS):
        row = brand.ljust(12) + "".join(str(matrix[i, j]).rjust(9) for j in range(len(BRANDS)))
        print(row)
    print()
    print(f"{'brand':<12}{'n':>6}{'precision':>12}{'recall':>10}{'f1':>8}")
    for brand in BRANDS:
        stats = report["per_brand"][brand]
        print(f"{brand:<12}{stats['n']:>6}{stats['precision']:>12.3f}{stats['recall']:>10.3f}{stats['f1']:>8.3f}")
    print()
    print(f"overall accuracy: {report['accuracy']:.3f}")
    print(f"macro accuracy (balanced): {report['macro_accuracy']:.3f}")
    print(f"majority-class baseline: {report['majority_baseline']:.3f}")
    print(f"uniform baseline (1/{len(BRANDS)}): {report['uniform_baseline']:.3f}")


def write_csv(matrix, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["true\\pred"] + BRANDS)
        for i, brand in enumerate(BRANDS):
            writer.writerow([brand] + list(matrix[i]))


def main():
    parser = argparse.ArgumentParser(description="브랜드 시그니처 판별기 - leave-one-out 결정력 검증")
    parser.add_argument("--features", choices=["tone_color_gamut", "all"], default="tone_color_gamut",
                         help="tone_color_gamut(기본, Set A) 또는 all(Set B, texture 포함)")
    parser.add_argument("--csv", default=None, help="confusion matrix를 CSV로도 저장")
    args = parser.parse_args()

    matrix, report = run(args.features)
    print_report(matrix, report, args.features)
    if args.csv:
        write_csv(matrix, args.csv)
        print(f"\n저장됨: {args.csv}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 수동 스모크테스트 (실제 933장 데이터)**

Run: `python3 -m tools.classify_brand`
Expected: 예외 없이 11×11 confusion matrix 표, 브랜드별 precision/recall/f1, `overall accuracy`/`macro accuracy`/두 baseline이 출력됨.

Run: `python3 -m tools.classify_brand --features all`
Expected: 21차원(Set B) 기준으로 동일한 형식의 출력, Set A와 다른 수치.

Run: `python3 -m tools.classify_brand --csv /tmp/claude-0/-home-user-Hncs/1d07a51d-3df6-5c74-ae37-0cc778eeeb5b/scratchpad/matrix_a.csv`
Expected: 콘솔 출력 + `matrix_a.csv` 파일 생성, 12행(헤더+11브랜드) × 12열(헤더+11브랜드) CSV.

Step 2에서 출력된 정확한 수치(overall accuracy, macro accuracy, 두 baseline, Set A/B 각각)를 받아적어 둔다 - Task 6에서 README에 그대로 옮겨 적는다.

- [ ] **Step 3: 커밋**

```bash
git add tools/classify_brand.py
git commit -m "Add tools/classify_brand.py CLI for the brand-signature LOO classifier"
```

---

### Task 6: 문서화 + 전체 테스트 스위트 확인

**Files:**
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `docs/project_structure.md`
- Modify: `docs/project_structure.en.md`

**Interfaces:**
- Consumes: Task 5의 `python3 -m tools.classify_brand` / `--features all` 실행 결과(정확한 accuracy/macro_accuracy/baseline 수치, Set A와 B 각각).

- [ ] **Step 1: README.ko.md에 새 섹션 추가**

`## Lightroom Classic / Adobe Camera Raw` 절(Photoshop/Lightroom LUT 내보내기 섹션의 일부) 바로 다음, `## 목표 / 철학` 직전에 삽입:

```markdown
## 브랜드 시그니처 판별력 검증 (연구용)

`tools/classify_brand.py`는 이 프로젝트의 다른 도구들과 방향이 반대다 -
새 기능을 만드는 게 아니라, 이미 계산해둔 11개 브랜드의 population
시그니처(`datasets/<brand>/*_signature.json`, 총 933장)가 브랜드를 실제로
구별할 만큼 결정력이 있는지를 leave-one-out nearest-centroid 분류로
검증한다. 표준화 거리 기반이고, held-out 사진은 매 폴드마다 자기 브랜드
centroid 계산에서도 완전히 제외된다(리키지 없음). `npix`/`is_portrait`/
`quality`/`subsampling`(이미지 크기·JPEG 인코더 설정)은 색감과 무관해서
의도적으로 제외 - 안 그러면 판별기가 "색 렌더링 차이"가 아니라 "어느
브랜드가 어떤 해상도/JPEG 설정으로 갤러리에 올렸는지"라는 무관한
지름길을 학습해버린다. 새 사진을 넣어 브랜드를 예측하는 기능은 없음(설계
근거는 `docs/superpowers/specs/2026-07-24-brand-classifier-design.md`).

```
python3 -m tools.classify_brand                # Set A: tone+color+gamut (15차원)
python3 -m tools.classify_brand --features all  # Set B: + texture (21차원)
```

[[TASK 5 STEP 2에서 받아적은 실제 출력값으로 아래를 채운다:]]
- Set A(texture 제외) - overall accuracy: `<실측값>`, macro accuracy: `<실측값>`
  (다수결 baseline `<실측값>`, 균등확률 baseline ≈9.1%)
- Set B(texture 포함) - overall accuracy: `<실측값>`, macro accuracy: `<실측값>`

texture의 sharpening/micro_contrast는 브랜드마다 계산 공식이 달라서
(`docs/project_structure.md` 기존 문서화 - Canon/Sony vs Nikon/Leica/
Pentax/Ricoh GR 스케일 다름) Set B가 Set A보다 정확도가 높게 나오더라도
그게 "진짜 색감 차이" 때문인지 "계산 공식 차이" 때문인지는 이 결과만으로
분리할 수 없다는 점을 유의. `leica`(45장)/`pentax`(40장)/`phaseone`(16장)은
표본이 얇아 그 브랜드들의 recall은 특히 노이즈가 클 수 있다.
```

`[[...]]` 안의 지시문대로 Task 5에서 실제로 받아적은 숫자로 바꿔 넣는다 - 플레이스홀더를 그대로 커밋하면 안 됨.

- [ ] **Step 2: README.md에 동일 섹션의 영어판 추가**

`## Photoshop / DaVinci Resolve preset export (.cube LUT)` 섹션 다음, `## Goals / Philosophy` 직전에 삽입 (Step 1과 동일한 실측 수치 사용):

```markdown
## Brand-signature discriminability check (research)

`tools/classify_brand.py` runs in the opposite direction from this project's other tools - instead of building a new feature, it validates whether the already-computed population signatures for the 11 brands (`datasets/<brand>/*_signature.json`, 933 photos total) actually carry enough signal to tell brands apart, via leave-one-out nearest-centroid classification. Distances are standardized (z-score), and the held-out photo is fully excluded from its own brand's centroid on every fold (no leakage). `npix`/`is_portrait`/`quality`/`subsampling` (image size, JPEG encoder settings) are deliberately excluded - keeping them would let the classifier learn "which brand uploads which resolution/JPEG setting" instead of an actual color-rendering difference. There's no predict-from-a-new-photo mode - design rationale in `docs/superpowers/specs/2026-07-24-brand-classifier-design.md`.

```
python3 -m tools.classify_brand                # Set A: tone+color+gamut (15-dim)
python3 -m tools.classify_brand --features all  # Set B: + texture (21-dim)
```

[[fill in with the actual numbers recorded in Task 5 step 2:]]
- Set A (no texture) - overall accuracy: `<measured>`, macro accuracy: `<measured>`
  (majority baseline `<measured>`, uniform baseline ≈9.1%)
- Set B (with texture) - overall accuracy: `<measured>`, macro accuracy: `<measured>`

Texture's sharpening/micro_contrast use different formulas per brand (documented in `docs/project_structure.md` - Canon/Sony vs. Nikon/Leica/Pentax/Ricoh GR are on different scales), so if Set B scores higher than Set A, this result alone can't separate "genuine color difference" from "which formula was used." `leica` (45)/`pentax` (40)/`phaseone` (16) have thin samples, so those brands' recall figures are especially noisy.
```

- [ ] **Step 3: `docs/project_structure.md`/`.en.md`에 파일 행 추가**

`docs/project_structure.md`의 `core/lut_export.py` 행 다음에 추가:

```markdown
| `core/brand_classifier.py` | "연구용" 브랜드 시그니처 판별력 검증 - 11개 브랜드의 `datasets/*/*_signature.json`을 filename으로 조인해서 leave-one-out nearest-centroid 분류(`load_signatures`/`extract_features`/`standardize`/`nearest_centroid_loo`/`confusion_matrix`/`classification_report`). numpy만 사용, 새 사진 예측 기능은 없음 |
```

`docs/project_structure.md`의 `tools/export_lut.py` 행 다음에 추가:

```markdown
| `tools/classify_brand.py` | 브랜드 시그니처 판별기 CLI - `python3 -m tools.classify_brand [--features tone_color_gamut\|all] [--csv out.csv]` |
```

`docs/project_structure.en.md`의 `core/lut_export.py` 행 다음에 추가:

```markdown
| `core/brand_classifier.py` | "Research-only" brand-signature discriminability check - joins the 11 brands' `datasets/*/*_signature.json` on filename and runs leave-one-out nearest-centroid classification (`load_signatures`/`extract_features`/`standardize`/`nearest_centroid_loo`/`confusion_matrix`/`classification_report`). numpy-only, no predict-from-a-new-photo mode |
```

`docs/project_structure.en.md`의 `tools/export_lut.py` 행 다음에 추가:

```markdown
| `tools/classify_brand.py` | Brand-signature classifier CLI - `python3 -m tools.classify_brand [--features tone_color_gamut\|all] [--csv out.csv]` |
```

- [ ] **Step 4: 전체 테스트 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, 이전 대비 12개 테스트 증가(Task 1~4에서 추가한 것들)

- [ ] **Step 5: 커밋 + 푸시**

```bash
git add README.md README.ko.md docs/project_structure.md docs/project_structure.en.md
git commit -m "Document the brand-signature LOO classifier's measured discriminability results"
git push -u origin claude/unknown-character-0x48vp
```
