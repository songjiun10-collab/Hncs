# "재미용" 브랜드 예측기 (predict-from-new-photo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 임의의 새 사진 한 장을 넣으면 `core/brand_classifier.py`의 10개 브랜드 centroid와의 거리로 순위를 매겨 보여주는 "재미용" CLI 기능(+선택적 자기완결적 HTML 리포트)을 추가한다.

**Architecture:** 새 사진에서 tone/color/gamut 시그니처를 계산하는 `core/photo_signature.py`(신규), 그 벡터를 852장 훈련 풀 기준 centroid까지 거리 순위 매기는 `core/brand_classifier.py`의 신규 함수 `rank_brands_by_distance()`, 이 둘을 엮는 `tools/classify_brand.py`의 새 `predict` 서브커맨드. 전부 Python 단일 소스 - 클라이언트사이드 JS 재구현 없음.

**Tech Stack:** 기존 의존성(`opencv-python`, `numpy`)만 사용, 새 의존성 없음.

## Global Constraints

- 새 의존성 추가 금지 - `cv2`/`numpy`만 사용(이미 `requirements.txt`에 있음).
- `predict`는 **Set A(tone_color_gamut)만 지원** - texture는 브랜드별 계산 공식이 유실돼 새 사진에 재현 불가(기존 연구용 도구 문서화 이슈와 동일).
- **가짜 확률/퍼센트를 절대 표시하지 않는다** - 순위와 거리(숫자)만. 콘솔 출력과 HTML 리포트 양쪽에 "실측 정확도 19.6%(다수결 baseline 14.6%) - 순위는 참고용" 경고를 항상 포함.
- `hue_mean`은 기존 population 시그니처 데이터와 같은 단위(OpenCV 원본 H 채널, 0~179, 실제 색상각의 절반)로 계산해야 한다 - `datasets/*/color_signature.json`의 실측값이 전부 이 범위(관측된 최댓값 179) 안에 있음을 확인했음(설계 스펙 작성 시점엔 놓쳤던 디테일 - 원형평균은 실제 0~360도 단위로 계산한 뒤 다시 절반으로 접어 저장 단위에 맞춰야 함).
- 이미 승인/테스트 완료된 `nearest_centroid_loo()`/`confusion_matrix()`/`classification_report()`/`extract_features()`/`standardize()`의 기존 시그니처와 동작은 바꾸지 않는다 - `rank_brands_by_distance()`는 별도 신규 함수로 추가.
- `tools/classify_brand.py`의 기존 동작(`python3 -m tools.classify_brand [--features ...] [--csv ...]`, 서브커맨드 없이 실행하면 기존 LOO 리포트)은 그대로 유지해야 한다(하위호환) - `predict`는 추가되는 서브커맨드일 뿐.
- HTML 리포트는 외부 CDN/폰트 의존 없이 완전히 자기완결적이어야 한다(사진은 base64 data URI로 내장).
- 테스트는 `unittest.TestCase` 스타일(프로젝트 관례, pytest 미사용).
- README.md/README.ko.md, docs/project_structure.md/.en.md 전부 갱신(이중언어 동시 유지 관례).

---

### Task 1: `core/photo_signature.py` - 새 사진에서 시그니처 계산

**Files:**
- Create: `core/photo_signature.py`
- Test: `tests/test_photo_signature.py`

**Interfaces:**
- Produces: `compute_signature(img_bgr: np.ndarray) -> dict` - BGR uint8 이미지에서 `{"b2", "w995", "median", "dark_pct", "sat_mean", "hue_mean", "a_p1", "a_p99", "b_p1", "b_p99", "a_std", "b_std", "chroma_mean", "chroma_p99"}` 14개 필드(전부 `float`)를 계산. 반환값은 `core.brand_classifier.extract_features([이 dict], feature_set="tone_color_gamut")`에 그대로 넣을 수 있는 필드셋.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_photo_signature.py` 새로 작성:

```python
import unittest

import cv2
import numpy as np

from core.brand_classifier import extract_features
from core.photo_signature import compute_signature


class TestComputeSignature(unittest.TestCase):
    def test_uniform_gray_image(self):
        img = np.full((20, 20, 3), 128, dtype=np.uint8)
        sig = compute_signature(img)

        self.assertEqual(sig["b2"], 128.0)
        self.assertEqual(sig["w995"], 128.0)
        self.assertEqual(sig["median"], 128.0)
        self.assertEqual(sig["dark_pct"], 0.0)
        self.assertEqual(sig["sat_mean"], 0.0)
        self.assertEqual(sig["hue_mean"], 0.0)
        self.assertEqual(sig["a_p1"], 128.0)
        self.assertEqual(sig["a_p99"], 128.0)
        self.assertEqual(sig["b_p1"], 128.0)
        self.assertEqual(sig["b_p99"], 128.0)
        self.assertEqual(sig["a_std"], 0.0)
        self.assertEqual(sig["b_std"], 0.0)
        self.assertEqual(sig["chroma_mean"], 0.0)
        self.assertEqual(sig["chroma_p99"], 0.0)

    def test_pure_red_patch(self):
        img = np.zeros((20, 20, 3), dtype=np.uint8)
        img[..., 2] = 255  # BGR - 순수 빨강

        sig = compute_signature(img)

        self.assertEqual(sig["b2"], 76.0)
        self.assertEqual(sig["w995"], 76.0)
        self.assertEqual(sig["median"], 76.0)
        self.assertEqual(sig["dark_pct"], 0.0)
        self.assertEqual(sig["sat_mean"], 255.0)
        self.assertEqual(sig["hue_mean"], 0.0)
        self.assertEqual(sig["a_p1"], 208.0)
        self.assertEqual(sig["a_p99"], 208.0)
        self.assertEqual(sig["b_p1"], 195.0)
        self.assertEqual(sig["b_p99"], 195.0)
        self.assertAlmostEqual(sig["chroma_mean"], 104.350371, places=4)
        self.assertAlmostEqual(sig["chroma_p99"], 104.350371, places=4)

    def test_circular_hue_mean_handles_wraparound(self):
        # OpenCV H=2와 H=177은 저장 단위(0~179)로는 멀어 보이지만 실제
        # 색상각으로는 4도/354도 - 0도(빨강) 바로 양옆에 붙어있는 거의
        # 같은 색이다. HSV->BGR 왕복 변환으로 정확한 H값을 보장해서
        # 이미지를 구성한다.
        top_hsv = np.zeros((10, 20, 3), dtype=np.uint8)
        top_hsv[..., 0] = 2
        top_hsv[..., 1] = 255
        top_hsv[..., 2] = 255
        bottom_hsv = np.zeros((10, 20, 3), dtype=np.uint8)
        bottom_hsv[..., 0] = 177
        bottom_hsv[..., 1] = 255
        bottom_hsv[..., 2] = 255
        top_bgr = cv2.cvtColor(top_hsv, cv2.COLOR_HSV2BGR)
        bottom_bgr = cv2.cvtColor(bottom_hsv, cv2.COLOR_HSV2BGR)
        img = np.vstack([top_bgr, bottom_bgr])

        sig = compute_signature(img)

        # 올바른 원형평균은 179.5(저장 단위, wraparound 경계) 근처여야
        # 하고, 틀린 산술평균(89.5, 저장 단위로 정반대 - 청록/녹색 쪽)과는
        # 뚜렷이 달라야 한다.
        self.assertAlmostEqual(sig["hue_mean"], 179.5, places=1)
        self.assertGreater(abs(sig["hue_mean"] - 89.5), 50)

    def test_output_feeds_directly_into_extract_features(self):
        img = np.full((10, 10, 3), 128, dtype=np.uint8)
        sig = compute_signature(img)

        X, feature_names = extract_features([sig], feature_set="tone_color_gamut")

        self.assertEqual(X.shape, (1, 15))
        self.assertEqual(len(feature_names), 15)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_photo_signature -v`
Expected: `ModuleNotFoundError: No module named 'core.photo_signature'`

- [ ] **Step 3: 최소 구현 작성**

`core/photo_signature.py` 새로 작성:

```python
"""임의의 사진 한 장에서 datasets/*/{tone,color,gamut}_signature.json과
같은 필드로 시그니처를 계산한다 - "재미용" 브랜드 예측기
(tools/classify_brand.py predict)의 입력 전처리 단계.

texture 필드는 계산하지 않는다 - 브랜드별 sharpening/micro_contrast
계산 공식이 원본 스크립트 유실로 서로 달라져 있다는 게 이미 문서화된
문제라(docs/project_structure.md 참고), 새 사진에 대해 "그 브랜드가
실제로 쓴 공식"을 재현할 방법이 없다.

각 필드의 정의는 tone_signature.json/color_signature.json/
gamut_signature.json의 methodology 필드에 문서화된 걸 그대로
재구현한 것이다 - 원본 계산 스크립트 자체를 복원한 게 아니라 근사
재구현이므로, 기존 population 데이터와 100% 동일한 공식이라는
보장은 없다(설계 근거:
docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md).

hue_mean은 기존 데이터와 같은 단위(OpenCV 원본 H 채널, 0~179 - 실제
색상각의 절반)로 반환한다 - datasets/*/color_signature.json의 실측값이
전부 이 범위(관측된 최댓값 179) 안에 있음을 확인하고 맞췄다. 원형평균
자체는 실제 색상각 단위(0~360도, H*2)로 계산해서 wraparound을 올바르게
처리한 뒤 다시 절반으로 접어 저장 단위에 맞춘다."""
import cv2
import numpy as np


def compute_signature(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)

    b2 = float(np.percentile(gray, 2))
    w995 = float(np.percentile(gray, 99.5))
    median = float(np.median(gray))
    dark_pct = float((gray < 40).sum() / gray.size * 100)

    h_raw = hsv[:, :, 0].astype(np.float64)  # OpenCV H, 0~179
    s = hsv[:, :, 1].astype(np.float64)
    mask = s > 20
    sat_mean = float(s[mask].mean()) if mask.any() else 0.0
    if mask.any():
        true_deg = h_raw[mask] * 2.0  # 0~179 -> 실제 0~358도로 펼침
        rad = np.deg2rad(true_deg)
        mean_true_deg = np.degrees(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360.0
        hue_mean = float(mean_true_deg / 2.0)  # 다시 0~179 단위로 접어서 기존 데이터와 단위 일치
    else:
        hue_mean = 0.0

    a = lab[:, :, 1].astype(np.float64)
    b = lab[:, :, 2].astype(np.float64)
    chroma = np.sqrt((a - 128.0) ** 2 + (b - 128.0) ** 2)

    return {
        "b2": b2, "w995": w995, "median": median, "dark_pct": dark_pct,
        "sat_mean": sat_mean, "hue_mean": hue_mean,
        "a_p1": float(np.percentile(a, 1)), "a_p99": float(np.percentile(a, 99)),
        "b_p1": float(np.percentile(b, 1)), "b_p99": float(np.percentile(b, 99)),
        "a_std": float(a.std()), "b_std": float(b.std()),
        "chroma_mean": float(chroma.mean()), "chroma_p99": float(np.percentile(chroma, 99)),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_photo_signature -v`
Expected: `OK` (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add core/photo_signature.py tests/test_photo_signature.py
git commit -m "Add compute_signature(): reconstruct tone/color/gamut fields for an arbitrary photo"
```

---

### Task 2: `core/brand_classifier.py`에 `rank_brands_by_distance()` 추가

**Files:**
- Modify: `core/brand_classifier.py`
- Modify: `tests/test_brand_classifier.py`

**Interfaces:**
- Consumes: 기존 `standardize(train_X, vector)`.
- Produces: `rank_brands_by_distance(query_vector: np.ndarray, train_X: np.ndarray, train_y: np.ndarray) -> list[tuple[str, float]]` - `(브랜드, 거리)` 쌍을 거리 오름차순으로 정렬한 리스트.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_brand_classifier.py`에 추가:

```python
from core.brand_classifier import (  # 상단 import 갱신
    load_signatures, extract_features, standardize, nearest_centroid_loo,
    confusion_matrix, classification_report, rank_brands_by_distance,
)


class TestRankBrandsByDistance(unittest.TestCase):
    def test_ranks_nearest_brand_first_and_sorted(self):
        rng = np.random.default_rng(0)
        cluster_a = rng.normal(loc=[0.0, 0.0], scale=0.5, size=(20, 2))
        cluster_b = rng.normal(loc=[50.0, 50.0], scale=0.5, size=(20, 2))
        cluster_c = rng.normal(loc=[-50.0, 50.0], scale=0.5, size=(20, 2))
        train_X = np.vstack([cluster_a, cluster_b, cluster_c])
        train_y = np.array(["A"] * 20 + ["B"] * 20 + ["C"] * 20)

        query = np.array([49.5, 50.2])  # 클러스터 B 중심 근처

        ranking = rank_brands_by_distance(query, train_X, train_y)

        self.assertEqual(len(ranking), 3)
        self.assertEqual(ranking[0][0], "B")
        distances = [dist for _, dist in ranking]
        self.assertEqual(distances, sorted(distances))
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `AttributeError` - `rank_brands_by_distance`가 아직 없음

- [ ] **Step 3: 구현 작성**

`core/brand_classifier.py`에 `nearest_centroid_loo()` 다음, `confusion_matrix()` 이전에 추가:

```python
def rank_brands_by_distance(query_vector, train_X, train_y):
    """query_vector(D,)가 train_X/train_y(전체 훈련 풀, held-out 없음)
    기준으로 각 브랜드 centroid와 표준화 공간에서 얼마나 가까운지
    오름차순으로 정렬해서 반환. nearest_centroid_loo()와 달리 폴드마다
    제외할 대상이 없다 - query_vector는 애초에 train_X에 속하지 않는
    새로운 사진이라 리키지 문제 자체가 없다."""
    train_y = np.asarray(train_y)
    z = standardize(train_X, query_vector)
    ranking = []
    for brand in np.unique(train_y):
        centroid_raw = train_X[train_y == brand].mean(axis=0)
        centroid_z = standardize(train_X, centroid_raw)
        dist = float(np.linalg.norm(z - centroid_z))
        ranking.append((str(brand), dist))
    ranking.sort(key=lambda pair: pair[1])
    return ranking
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_brand_classifier -v`
Expected: `OK` (16 tests)

- [ ] **Step 5: 커밋**

```bash
git add core/brand_classifier.py tests/test_brand_classifier.py
git commit -m "Add rank_brands_by_distance(): distance-ranked centroid comparison for a new query photo"
```

---

### Task 3: `tools/classify_brand.py`에 `predict` 서브커맨드 추가

**Files:**
- Modify: `tools/classify_brand.py`

**Interfaces:**
- Consumes: `core.photo_signature.compute_signature`, `core.brand_classifier.{BRANDS, load_signatures, extract_features, rank_brands_by_distance}` (그리고 기존 `nearest_centroid_loo`/`confusion_matrix`/`classification_report`).

- [ ] **Step 1: 기존 로딩 로직을 공유 헬퍼로 리팩터링**

`tools/classify_brand.py`의 현재 `run()` 함수(전체 파일 앞부분은 그대로 두고 이 함수만 교체):

```python
def load_all_features(feature_set):
    """CLASSIFIED_BRANDS(ricoh_gr 제외 10개 브랜드) 전체를 로드해서
    (X, y) 반환 - report 모드와 predict 모드가 함께 재사용한다."""
    all_X = []
    all_y = []
    for brand in CLASSIFIED_BRANDS:
        records = load_signatures(brand)
        X, _ = extract_features(records, feature_set=feature_set)
        all_X.append(X)
        all_y.extend([brand] * len(records))
    X = np.concatenate(all_X, axis=0)
    y = np.array(all_y)
    return X, y


def run(feature_set):
    X, y = load_all_features(feature_set)
    predictions = nearest_centroid_loo(X, y)
    matrix = confusion_matrix(y, predictions, brands=CLASSIFIED_BRANDS)
    report = classification_report(y, predictions, brands=CLASSIFIED_BRANDS)
    return matrix, report
```

(이 리팩터는 `for brand in BRANDS: if brand in EXCLUDED_BRANDS: continue`를
`for brand in CLASSIFIED_BRANDS:`로 단순화하는 것도 겸한다 - 동작은
동일, 순회 대상만 미리 걸러진 리스트로 바뀜.)

- [ ] **Step 2: 리팩터링이 기존 동작을 안 바꿨는지 확인**

Run: `python3 -m tools.classify_brand`
Expected: 콘솔에 `overall accuracy: 0.196`, `macro accuracy (balanced): 0.232`가 그대로 출력됨(리팩터 전과 동일한 숫자 - 순수 리팩터라 결과가 바뀌면 안 됨).

Run: `python3 -m tools.classify_brand --features all`
Expected: `overall accuracy: 0.498`, `macro accuracy (balanced): 0.490` 그대로 출력.

- [ ] **Step 3: import 추가 및 predict 관련 함수 작성**

`tools/classify_brand.py` 상단 import 블록을 다음으로 교체:

```python
"""브랜드 시그니처 판별기 CLI - 10개 브랜드(ricoh_gr은 hue_median/hue_mean
통계 불일치로 제외, EXCLUDED_BRANDS 참고)의 이미 계산된 population
시그니처(datasets/*/*_signature.json)만으로 leave-one-out 교차검증 기반
nearest-centroid 분류를 돌려서 confusion matrix와 지표를 출력한다
(서브커맨드 없이 실행, 기본 동작).

`predict` 서브커맨드는 별도 목적 - "재미용"으로 임의의 새 사진 한 장을
10개 브랜드 centroid와 비교해서 거리 순위를 매긴다. texture 없이
Set A(tone_color_gamut)만 지원(core/photo_signature.py 모듈 docstring
참고 - 브랜드별 texture 계산 공식이 유실돼 새 사진에 재현 불가). 이
판별기의 실측 정확도(19.6%, 다수결 baseline 14.6%)가 낮기 때문에
가짜 확률을 표시하지 않고 거리 순위만 보여준다(설계 근거:
docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md)."""
import argparse
import base64
import csv
import os
import sys

import cv2
import numpy as np

from core.brand_classifier import (
    BRANDS, load_signatures, extract_features, nearest_centroid_loo,
    confusion_matrix, classification_report, rank_brands_by_distance,
)
from core.photo_signature import compute_signature

ACCURACY_CAVEAT = (
    "참고: 이 판별기의 실측 정확도는 19.6%(다수결 baseline 14.6%) - "
    "순위는 참고용이지 확정적 판정이 아님"
)
```

파일 끝(`if __name__ == "__main__":` 앞)에 `write_csv()` 다음으로 추가:

```python
def run_predict(photo_path):
    img = cv2.imread(photo_path)
    if img is None:
        sys.exit(f"이미지를 읽을 수 없음: {photo_path}")

    signature = compute_signature(img)
    query_vector, _ = extract_features([signature], feature_set="tone_color_gamut")
    query_vector = query_vector[0]

    train_X, train_y = load_all_features("tone_color_gamut")
    ranking = rank_brands_by_distance(query_vector, train_X, train_y)
    return ranking


def print_predict_report(ranking):
    print(ACCURACY_CAVEAT)
    print(f"\n1위: {ranking[0][0]} (거리 {ranking[0][1]:.3f})\n")
    print(f"{'순위':<4}{'브랜드':<12}{'거리':>10}")
    for rank, (brand, dist) in enumerate(ranking, start=1):
        print(f"{rank:<4}{brand:<12}{dist:>10.3f}")


def write_predict_html(photo_path, ranking, html_path):
    """사진(base64 내장) + 순위표 + 정확도 경고 배너가 담긴 자기완결적
    정적 HTML 파일을 만든다. 외부 CDN/폰트 의존 없음(시스템 폰트만 사용).
    미니멀/무채색 톤(다크 배경, 회색조 팔레트, 색 액센트 없음) - 코너
    브래킷 뷰파인더 프레임과 모노스페이스 라벨은 사용자가 공유한 다른
    데모 페이지의 에디토리얼 톤에서 아이디어만 가져온 것으로, 그 페이지의
    인터랙티브 JS 엔진은 가져오지 않는다(이 리포트는 정적 결과물)."""
    with open(photo_path, "rb") as f:
        photo_b64 = base64.b64encode(f.read()).decode("ascii")
    ext = os.path.splitext(photo_path)[1].lstrip(".").lower() or "jpeg"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext

    top_brand, top_dist = ranking[0]
    rows = "\n".join(
        f'<div class="bitem{" active" if i == 1 else ""}">'
        f'<span class="idx">{i:02d}</span>'
        f'<span class="bn">{brand}</span>'
        f'<span class="bd">{dist:.3f}</span>'
        f'</div>'
        for i, (brand, dist) in enumerate(ranking, start=1)
    )

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>브랜드 시그니처 예측 (재미용)</title>
<style>
:root{{
  --bg:#0a0a0a; --bg2:#101010; --bg3:#181817;
  --fg:#f2f2f0; --fg2:#c9c9c4; --mut:#8b8b86; --dim:#4c4c48;
  --line:#232321; --line2:#373733;
  --mono:ui-monospace,SFMono-Regular,'IBM Plex Mono',monospace;
  --sans:-apple-system,BlinkMacSystemFont,'Malgun Gothic',sans-serif;
  --maxw:920px;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:var(--sans);background:var(--bg);color:var(--fg);line-height:1.6;padding:0 0 60px}}
.wrap{{max-width:var(--maxw);margin:0 auto;padding:0 28px}}
.top{{border-bottom:1px solid var(--line);padding:18px 0;margin-bottom:36px}}
.top-in{{max-width:var(--maxw);margin:0 auto;padding:0 28px;display:flex;align-items:center;gap:10px}}
.led{{width:7px;height:7px;border-radius:50%;background:var(--fg);flex:none}}
.wm{{font-family:var(--mono);font-size:.72rem;letter-spacing:.14em;color:var(--mut);text-transform:uppercase}}
h1{{font-size:clamp(1.5rem,4vw,2.1rem);font-weight:800;letter-spacing:-.01em;margin-bottom:8px}}
.kicker{{font-family:var(--mono);font-size:.64rem;letter-spacing:.18em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}}
.warn{{background:var(--bg2);border:1px solid var(--fg2);color:var(--fg2);
  font-family:var(--mono);font-size:.74rem;letter-spacing:.02em;padding:12px 16px;
  margin-bottom:32px;line-height:1.7}}
.grid{{display:grid;grid-template-columns:280px 1fr;gap:32px}}
.frame{{position:relative;border:1px dashed var(--line2);padding:10px}}
.corner{{position:absolute;width:13px;height:13px;border:1px solid var(--fg);opacity:.8}}
.c-tl{{top:6px;left:6px;border-right:none;border-bottom:none}}
.c-tr{{top:6px;right:6px;border-left:none;border-bottom:none}}
.c-bl{{bottom:6px;left:6px;border-right:none;border-top:none}}
.c-br{{bottom:6px;right:6px;border-left:none;border-top:none}}
.frame img{{display:block;width:100%;height:auto}}
.frame-cap{{font-family:var(--mono);font-size:.6rem;letter-spacing:.12em;color:var(--dim);
  text-transform:uppercase;margin-top:10px}}
.result{{margin-bottom:18px}}
.result .lbl{{font-family:var(--mono);font-size:.62rem;letter-spacing:.18em;color:var(--mut);
  text-transform:uppercase;margin-bottom:6px}}
.result .val{{font-size:1.7rem;font-weight:800}}
.result .dist{{font-family:var(--mono);font-size:.78rem;color:var(--mut)}}
.blist{{border-top:1px solid var(--fg)}}
.bitem{{display:grid;grid-template-columns:26px 1fr auto;align-items:center;gap:10px;
  padding:9px 4px;border-bottom:1px solid var(--line);font-size:.86rem}}
.bitem .idx{{font-family:var(--mono);font-size:.62rem;color:var(--dim)}}
.bitem .bd{{font-family:var(--mono);font-size:.72rem;color:var(--mut)}}
.bitem.active{{background:var(--fg);color:var(--bg)}}
.bitem.active .idx,.bitem.active .bd{{color:var(--bg)}}
footer{{margin-top:40px;font-family:var(--mono);font-size:.62rem;color:var(--dim);
  letter-spacing:.04em;line-height:1.8}}
@media(max-width:640px){{.grid{{grid-template-columns:1fr}}}}
</style></head>
<body>
<div class="top"><div class="top-in"><span class="led"></span><span class="wm">HNCS &middot; PREDICT (재미용)</span></div></div>
<div class="wrap">
  <div class="kicker">Brand Signature Ranking &middot; Not a Verified Match</div>
  <h1>{top_brand}에 가장 가까움</h1>
  <div class="warn">{ACCURACY_CAVEAT}. 가짜 확률이 아니라 거리 순위만 표시함.</div>
  <div class="grid">
    <div>
      <div class="frame">
        <i class="corner c-tl"></i><i class="corner c-tr"></i><i class="corner c-bl"></i><i class="corner c-br"></i>
        <img src="data:image/{mime};base64,{photo_b64}" alt="입력 사진">
      </div>
      <div class="frame-cap">Query Photo</div>
    </div>
    <div>
      <div class="result">
        <div class="lbl">1위</div>
        <div class="val">{top_brand}</div>
        <div class="dist">거리 {top_dist:.3f}</div>
      </div>
      <div class="blist">{rows}</div>
    </div>
  </div>
  <footer>tools/classify_brand.py predict &middot; Set A(tone+color+gamut)만 사용, texture 미지원<br>
  10개 브랜드 852장 population 시그니처 기준 leave-one-out nearest-centroid</footer>
</div>
</body></html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
```

- [ ] **Step 4: `main()`을 서브커맨드 지원하도록 교체**

`tools/classify_brand.py`의 기존 `main()` 함수를 다음으로 교체(기존 `--features`/`--csv` 동작은 그대로 유지, `predict` 서브커맨드만 추가):

```python
def main():
    parser = argparse.ArgumentParser(description="브랜드 시그니처 판별기 - leave-one-out 결정력 검증 / 새 사진 브랜드 순위(재미용)")
    parser.add_argument("--features", choices=["tone_color_gamut", "all"], default="tone_color_gamut",
                         help="tone_color_gamut(기본, Set A) 또는 all(Set B, texture 포함) - report 모드에만 적용")
    parser.add_argument("--csv", default=None, help="confusion matrix를 CSV로도 저장 - report 모드에만 적용")

    subparsers = parser.add_subparsers(dest="command")
    predict_parser = subparsers.add_parser(
        "predict", help="새 사진 하나를 10개 브랜드 centroid와 비교해서 거리 순위 매김(재미용, Set A만 지원)"
    )
    predict_parser.add_argument("photo", help="입력 사진 파일 경로")
    predict_parser.add_argument("--html", default=None, help="자기완결적 HTML 리포트 저장 경로")

    args = parser.parse_args()

    if args.command == "predict":
        ranking = run_predict(args.photo)
        print_predict_report(ranking)
        if args.html:
            write_predict_html(args.photo, ranking, args.html)
            print(f"\n저장됨: {args.html}")
        return

    print(
        f"note: ricoh_gr excluded - color_signature.json uses hue_median instead of "
        f"hue_mean, not comparable to the other {len(CLASSIFIED_BRANDS)} brands' hue feature"
    )
    matrix, report = run(args.features)
    print_report(matrix, report, args.features)
    if args.csv:
        write_csv(matrix, args.csv)
        print(f"\n저장됨: {args.csv}")
```

- [ ] **Step 5: 수동 스모크테스트 (실제 이미지)**

Run: `python3 -m tools.classify_brand predict docs/images/before_after_hncs.jpg`
Expected: 예외 없이 정확도 경고 문구, 1위 브랜드, 10개 브랜드 순위표(거리 오름차순)가 출력됨.

Run: `python3 -m tools.classify_brand predict docs/images/before_after_hncs.jpg --html /tmp/claude-0/-home-user-Hncs/1d07a51d-3df6-5c74-ae37-0cc778eeeb5b/scratchpad/predict_demo.html`
Expected: 콘솔 출력 + `predict_demo.html` 생성 확인. 파일을 열어서(`grep`으로) 다음이 전부 들어있는지 확인: `<img src="data:image/jpeg;base64,...`(내장 사진), `class="warn"`(정확도 경고 배너), `class="corner c-tl"`(코너 브래킷 프레임 - 총 4개), `class="bitem active"`(1위 브랜드 하이라이트), `class="bitem"`가 정확히 10개(순위 10행). 외부 `<link>`/`http`/`https` 참조가 전혀 없는지도 확인(자기완결적 요구사항 - `grep -c "http" predict_demo.html`가 0이어야 함, base64 데이터 URI 자체는 `data:image/`로 시작하니 걸리지 않음).

Run (기존 report 모드가 여전히 정상 동작하는지 최종 재확인): `python3 -m tools.classify_brand --csv /tmp/claude-0/-home-user-Hncs/1d07a51d-3df6-5c74-ae37-0cc778eeeb5b/scratchpad/report_check.csv`
Expected: 기존과 동일하게 정상 동작, CSV 생성.

- [ ] **Step 6: 커밋**

```bash
git add tools/classify_brand.py
git commit -m "Add 'predict' subcommand: rank a new photo against the 10 brand centroids by distance"
```

---

### Task 4: 문서화 + 전체 테스트 스위트 확인 + 푸시

**Files:**
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `docs/project_structure.md`
- Modify: `docs/project_structure.en.md`

- [ ] **Step 1: README.ko.md에 하위 절 추가**

"## 브랜드 시그니처 판별력 검증 (연구용)" 섹션의 마지막 문단(`leica(45)/pentax(40)/phaseone(16)...` 문단) 바로 다음, `## 목표 / 철학` 직전에 삽입:

```markdown
**그리고 재미로**: 위 검증 도구 위에 얹은 `predict` 서브커맨드로, 아무
사진이나 넣으면 그 사진이 10개 브랜드 중 어디에 가장 가까운지 거리
순위를 보여준다. texture 없이 Set A(tone+color+gamut)만 쓴다 - 브랜드별
texture 계산 공식이 유실돼 새 사진에 재현할 방법이 없어서다(위 캐비앗
그대로). 실측 정확도가 19.6%밖에 안 되기 때문에 가짜 확률(예: "87%
Sony")은 절대 표시하지 않고 거리 순위만 보여주며, 콘솔/HTML 결과물
양쪽에 이 정확도 숫자를 항상 같이 출력한다.

```
python3 -m tools.classify_brand predict photo.jpg
python3 -m tools.classify_brand predict photo.jpg --html result.html  # 사진을 base64로 내장한 자기완결적 정적 HTML
```
```

- [ ] **Step 2: README.md에 동일 섹션의 영어판 추가**

"## Brand-signature discriminability check (research)" 섹션 마지막 문단(`leica (45)/pentax (40)/phaseone (16)...`) 바로 다음, `## Goals / Philosophy` 직전에 삽입:

```markdown
**And for fun**: a `predict` subcommand built on top of the same validated tool - feed it any photo and it ranks which of the 10 brands' centroids it lands closest to, by distance. Texture is left out (Set A only, tone+color+gamut) - the same caveat as above, since texture's per-brand formulas can't be reconstructed for a new photo. Since measured accuracy is only 19.6%, it never shows a fabricated confidence number (no "87% Sony") - just the distance ranking, with that accuracy figure always printed alongside both the console and HTML output.

```
python3 -m tools.classify_brand predict photo.jpg
python3 -m tools.classify_brand predict photo.jpg --html result.html  # self-contained static HTML with the photo embedded as base64
```
```

- [ ] **Step 3: `docs/project_structure.md`/`.en.md`에 파일 행 추가**

`docs/project_structure.md`의 `core/brand_classifier.py` 행 다음에 추가:

```markdown
| `core/photo_signature.py` | "재미용" 예측기의 입력 전처리 - 임의의 새 사진에서 tone/color/gamut 시그니처 필드를 계산(`compute_signature`). texture는 브랜드별 계산 공식 유실로 제외. 원본 계산 스크립트를 복원한 게 아니라 methodology 필드 기반 근사 재구현(설계 근거: `docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md`) |
```

`docs/project_structure.md`의 `tools/classify_brand.py` 행을 다음으로 교체:

```markdown
| `tools/classify_brand.py` | 브랜드 시그니처 판별기 CLI - `python3 -m tools.classify_brand [--features tone_color_gamut\|all] [--csv out.csv]`(기본, LOO 리포트) / `python3 -m tools.classify_brand predict photo.jpg [--html out.html]`(재미용, 새 사진 브랜드 순위) |
```

`docs/project_structure.en.md`의 `core/brand_classifier.py` 행 다음에 추가:

```markdown
| `core/photo_signature.py` | Input preprocessing for the "for fun" predictor - computes tone/color/gamut signature fields for an arbitrary new photo (`compute_signature`). Texture is excluded (per-brand formulas were lost). An approximate reimplementation from the methodology fields, not a restoration of the original scripts (design rationale: `docs/superpowers/specs/2026-07-25-brand-predict-fun-design.md`) |
```

`docs/project_structure.en.md`의 `tools/classify_brand.py` 행을 다음으로 교체:

```markdown
| `tools/classify_brand.py` | Brand-signature classifier CLI - `python3 -m tools.classify_brand [--features tone_color_gamut\|all] [--csv out.csv]` (default, LOO report) / `python3 -m tools.classify_brand predict photo.jpg [--html out.html]` (for fun - rank a new photo against the brands) |
```

- [ ] **Step 4: 전체 테스트 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, 이전(337개) 대비 4개(Task 1의 `test_photo_signature.py`) + 1개(Task 2의 `rank_brands_by_distance` 테스트) = 342개.

- [ ] **Step 5: 커밋 + 푸시**

```bash
git add README.md README.ko.md docs/project_structure.md docs/project_structure.en.md
git commit -m "Document the 'predict' subcommand - for-fun brand ranking for an arbitrary photo"
git push -u origin claude/unknown-character-0x48vp
```
