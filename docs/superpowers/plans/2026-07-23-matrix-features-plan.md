# root-polynomial + WLS 매트릭스 피팅 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `hybrid_engine/core/raw_baseline.py`의 `fit_color_matrix()`를 root-polynomial feature와 가중 최소자승(WLS)으로 확장하고, `calibrate_profile.py`에 이 축들을 실제 15쌍 데이터로 그리드서치+교차검증하는 모드를 추가해서 ΔE00을 더 낮출 수 있는지 실측한다.

**Architecture:** 기존 `fit_color_matrix(sources, targets)`(순수 선형 3x3 OLS)에 `feature_fn`/`weights`/`ridge` 키워드 인자를 추가(기본값은 기존 동작과 동일 - 하위호환). `apply_color_matrix()`도 같은 `feature_fn`을 받도록 확장. 새 `calibrate_profile.py --mode matrix_features`가 `feature_set x weight_scheme x ridge` 그리드를 4-fold CV로 스크리닝한 뒤 1등만 13-fold(leave-one-out) CV로 확정 검증한다. 이 실험은 Phase 0(raw_baseline 매트릭스)만 다루고, 기존 `run_raw_baseline_mode`와 같은 범위(전체 파이프라인 재학습 없음)다.

**Tech Stack:** Python 3.11, numpy(선형대수), 기존 `hybrid_engine` 모듈 구조. 신규 의존성 없음.

## Global Constraints

- `fit_color_matrix()`/`apply_color_matrix()`의 기존 2-인자 호출 시그니처는 반드시 기존과 동일하게 동작해야 한다(기존 호출부 `pipeline/engine.py`, `calibrate_profile.py`의 다른 함수들이 코드 변경 없이 그대로 동작).
- 이 프로젝트는 `numpy`만 쓰고 다른 무거운 ML 의존성(scipy, scikit-learn 등)을 추가하지 않는다는 원칙이 있다(`hybrid_engine/EVALUATION.md` 후속 실측 18 - RBF 시도 때 scipy를 새 의존성으로 추가해야 해서 채택 안 함).
- 교차검증에서 데이터 누출 금지: `weights`(특히 `density_weights`)는 반드시 그 fold의 **학습 데이터에서만** 다시 계산해야 한다.
- 배포 기준(≥5% CV 개선)과 실패 시에도 결과를 삭제하지 않고 문서화하는 원칙은 이 프로젝트 전체의 관례이며 이 플랜에도 그대로 적용된다.
- 스펙 문서: `docs/superpowers/specs/2026-07-23-matrix-features-design.md`

---

## Task 1: `root_polynomial_features()` + `fit_color_matrix()`/`apply_color_matrix()` 확장

**Files:**
- Modify: `hybrid_engine/core/raw_baseline.py`
- Test: `tests/test_raw_baseline.py`

**Interfaces:**
- Produces:
  - `root_polynomial_features(rgb: np.ndarray) -> np.ndarray` — `rgb`는 `(..., 3)`, 반환은 `(..., 6)` = `[r, g, b, sqrt(r*g), sqrt(r*b), sqrt(g*b)]`(음수는 sqrt 전에 0으로 clip)
  - `fit_color_matrix(sources, targets, feature_fn=None, weights=None, ridge=0.0) -> np.ndarray` — `feature_fn=None`이면 기존 선형 3항. `weights`는 `sources`와 길이가 같은 리스트, 각 원소는 해당 source와 같은 `(H, W)` shape(픽셀별 가중치). `ridge`는 L2 정규화 강도.
  - `apply_color_matrix(rgb_linear, matrix, feature_fn=None) -> np.ndarray`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_raw_baseline.py` 맨 위 import를 아래처럼 바꾸고:

```python
from hybrid_engine.core.raw_baseline import (
    fit_color_matrix, apply_color_matrix, root_polynomial_features,
)
```

`TestApplyColorMatrix` 클래스 뒤(`if __name__ == "__main__":` 앞)에 아래 클래스들을 추가:

```python
class TestRootPolynomialFeatures(unittest.TestCase):
    def test_output_shape(self):
        rng = np.random.default_rng(10)
        img = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        feats = root_polynomial_features(img)
        self.assertEqual(feats.shape, (6, 6, 6))

    def test_known_pixel_values(self):
        img = np.array([[[0.4, 0.9, 0.25]]])
        feats = root_polynomial_features(img)
        expected = np.array([[[0.4, 0.9, 0.25,
                                np.sqrt(0.4 * 0.9),
                                np.sqrt(0.4 * 0.25),
                                np.sqrt(0.9 * 0.25)]]])
        np.testing.assert_allclose(feats, expected, atol=1e-10)

    def test_exposure_invariance_of_fitted_matrix_prediction(self):
        # 노출(전역 밝기 스케일)이 k배 바뀌어도 같은 매트릭스로 예측한 결과이
        # 그대로 k배가 되어야 한다 - root-polynomial의 핵심 성질(노출 불변).
        rng = np.random.default_rng(11)
        img = rng.uniform(0.05, 0.6, size=(10, 10, 3))
        matrix = rng.uniform(-0.2, 1.2, size=(6, 3))
        pred = root_polynomial_features(img).reshape(-1, 6) @ matrix

        k = 2.5
        scaled_pred = root_polynomial_features(img * k).reshape(-1, 6) @ matrix
        np.testing.assert_allclose(scaled_pred, pred * k, rtol=1e-8)


class TestFitColorMatrixWithFeatureFn(unittest.TestCase):
    def test_root_polynomial_recovers_known_matrix(self):
        rng = np.random.default_rng(12)
        img = rng.uniform(0.05, 0.9, size=(30, 30, 3))
        known_matrix = rng.uniform(-0.3, 1.3, size=(6, 3))
        target = (root_polynomial_features(img).reshape(-1, 6) @ known_matrix).reshape(img.shape)

        fitted = fit_color_matrix([img], [target], feature_fn=root_polynomial_features)
        np.testing.assert_allclose(fitted, known_matrix, atol=1e-6)


class TestFitColorMatrixWeighted(unittest.TestCase):
    def test_weighted_matches_manual_weighted_lstsq(self):
        rng = np.random.default_rng(14)
        img = rng.uniform(0.05, 0.9, size=(5, 5, 3))
        target = rng.uniform(0.05, 0.9, size=(5, 5, 3))
        w = rng.uniform(0.1, 2.0, size=(5, 5))

        fitted = fit_color_matrix([img], [target], weights=[w])

        X = img.reshape(-1, 3)
        Y = target.reshape(-1, 3)
        sw = np.sqrt(w.reshape(-1))[:, None]
        expected, _, _, _ = np.linalg.lstsq(X * sw, Y * sw, rcond=None)
        np.testing.assert_allclose(fitted, expected, atol=1e-8)

    def test_uniform_weights_match_unweighted(self):
        rng = np.random.default_rng(15)
        img = rng.uniform(0.05, 0.9, size=(10, 10, 3))
        target = rng.uniform(0.05, 0.9, size=(10, 10, 3))
        w = np.ones((10, 10))
        weighted = fit_color_matrix([img], [target], weights=[w])
        unweighted = fit_color_matrix([img], [target])
        np.testing.assert_allclose(weighted, unweighted, atol=1e-8)


class TestFitColorMatrixRidge(unittest.TestCase):
    def test_higher_ridge_shrinks_matrix_norm(self):
        rng = np.random.default_rng(16)
        img = rng.uniform(0.05, 0.9, size=(15, 15, 3))
        target = rng.uniform(0.05, 0.9, size=(15, 15, 3))
        m0 = fit_color_matrix([img], [target], ridge=0.0)
        m1 = fit_color_matrix([img], [target], ridge=1.0)
        self.assertLess(np.linalg.norm(m1), np.linalg.norm(m0))


class TestApplyColorMatrixWithFeatureFn(unittest.TestCase):
    def test_root_polynomial_apply_matches_manual(self):
        rng = np.random.default_rng(17)
        img = rng.uniform(0.05, 0.9, size=(4, 4, 3))
        matrix = rng.uniform(-0.5, 1.5, size=(6, 3))
        out = apply_color_matrix(img, matrix, feature_fn=root_polynomial_features)
        expected = np.clip(
            root_polynomial_features(img).reshape(-1, 6) @ matrix, 0.0, None
        ).reshape(img.shape)
        np.testing.assert_allclose(out, expected, atol=1e-10)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_raw_baseline.py -v`
Expected: `root_polynomial_features`가 없어서 `ImportError`로 FAIL

- [ ] **Step 3: 구현**

`hybrid_engine/core/raw_baseline.py`를 통째로 아래 내용으로 교체:

```python
"""
[GitHub 이슈 #4 대응, Phase 0] raw 베이스라인(rawpy/libraw 기본 디코드)
자체를 색차트 없이 실측 raw+jpeg 페어로 특성화한다.

이슈 #4 지적: "raw 베이스라인이 색차트 최소자승 매트릭스로 특성화된 적이
없다" - hybrid_engine의 ΔE≈15 병목이 톤/채도/hue 등 hybrid_engine
자체의 처리 문제인지, 아니면 애초에 rawpy의 기본 디코드(카메라 고유
CFA 분광감도를 sRGB 프라이머리로 근사하는 기본 색공간 변환)가 실제
카메라(Phocus)와 다른 색공간에서 출발하기 때문인지 이 둘을 분리해서
보지 못했다는 뜻. 실제 ColorChecker 촬영이 이 프로젝트엔 없어서, 대신
13쌍의 실사진 픽셀 대응 자체를 거대한 "차트"로 써서 전역 3x3 선형
컬러 매트릭스 하나를 최소자승으로 맞춘다 - hybrid_engine의 다른 처리를
전혀 거치지 않은 순수 rawpy 디코드 결과에 대해서.

**2026-07 실측(EVALUATION.md 후속 실측 5)**: 이 매트릭스 하나가
교차검증 기준 32.6% 개선을 냈다(다른 LUT 실험들과 달리 유일한 양성
결과) - 자유도 9개뿐이라 표본 13장에서도 과적합이 덜 되는 게 이유로
보인다. 그 결과로 이 모듈은 단순 진단 도구를 넘어 pipeline/engine.py의
정식 **Phase 0** 단계가 됐다(`raw_baseline_matrix` profile 파라미터,
calibrate_profile.py --mode raw_baseline_pipeline으로 캘리브레이션) -
tone_core(Phase 1)/color_core(Phase 2)는 삭제하지 않고 이 매트릭스
위에서 재학습한다(사용자 지시).

**2026-07 확장(docs/superpowers/specs/2026-07-23-matrix-features-design.md,
후속 실측 20)**: 자유도를 통제된 방식으로만 늘리는 두 축을 추가.
(1) root-polynomial feature(Finlayson et al. 2015) - 선형 3항 대신
[r,g,b,sqrt(rg),sqrt(rb),sqrt(gb)] 6항을 써서 노출 불변성을 유지하면서
자유도를 9->18로 늘림. (2) 가중 최소자승(WLS) - 밀도 기반(과대표집된
색 영역 다운웨이트)과 채도 기반(무채색 픽셀 다운웨이트) 두 가중치
스킴. 둘 다 기본값(feature_fn=None, weights=None, ridge=0.0)에서는
기존 동작과 완전히 동일하다.
"""
import numpy as np


def root_polynomial_features(rgb):
    """rgb: (..., 3) linear RGB. 반환: (..., 6) =
    [r, g, b, sqrt(r*g), sqrt(r*b), sqrt(g*b)].

    Finlayson et al. 2015 "Color Correction Using Root-Polynomial
    Regression" 방식 - 제곱항(r^2 등)이 아니라 제곱근 교차항을 쓰는
    이유는 전역 노출(밝기) 스케일 불변성 때문이다: 이미지 전체가 k배
    밝아지면 선형항도 제곱근 교차항도 똑같이 k배로 스케일되어(제곱근
    안의 곱이 k^2배가 되고 제곱근을 취하면 k배), 이 feature로 피팅한
    매트릭스는 노출이 다른 사진에도 그대로 유효하다. 일반 2차 다항식의
    순수 제곱항(r^2)은 k^2배로 스케일되어 이 불변성이 깨진다.

    음수(라인어 RGB 클리핑 이전의 미세한 음수)는 제곱근 전에 0으로
    clip해서 NaN을 막는다 - 최종 feature 값 자체는 clip 안 된 원본
    r/g/b를 그대로 쓴다(선형항은 clip 불필요)."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    r_c = np.clip(r, 0.0, None)
    g_c = np.clip(g, 0.0, None)
    b_c = np.clip(b, 0.0, None)
    return np.stack([
        r, g, b,
        np.sqrt(r_c * g_c),
        np.sqrt(r_c * b_c),
        np.sqrt(g_c * b_c),
    ], axis=-1)


def fit_color_matrix(sources, targets, feature_fn=None, weights=None, ridge=0.0):
    """sources/targets: linear RGB 배열 리스트(각 (H, W, 3), 페어별로
    shape 동일). 전부 이어붙여서 Y ≈ features(X) @ M 최소자승으로
    (K, 3) 행렬을 구한다(K=3이면 feature_fn=None일 때의 기존 동작).
    bias(상수항)는 넣지 않음 - linear RGB는 물리적으로 원점을 지나야
    한다(검은색 -> 검은색).

    feature_fn: None(기존 선형 3항)이거나 (H,W,3)->(H,W,K) 변환 함수
    (예: root_polynomial_features).
    weights: None(균등 가중치)이거나 sources와 길이가 같은 리스트 -
    각 원소는 해당 source와 같은 (H, W) shape의 픽셀별 가중치. 가중
    최소자승은 sqrt(weight)를 X/Y 양쪽에 곱하는 표준 트릭으로 구현.
    ridge: L2 정규화 강도(기본 0 = 정규화 없음, 기존 동작과 동일).
    feature_fn으로 자유도가 늘어날 때 과적합을 억제하는 용도."""
    if feature_fn is None:
        feats = [s.reshape(-1, 3) for s in sources]
    else:
        feats = []
        for s in sources:
            f = feature_fn(s)
            feats.append(f.reshape(-1, f.shape[-1]))
    X = np.concatenate(feats, axis=0)
    Y = np.concatenate([t.reshape(-1, 3) for t in targets], axis=0)

    if weights is not None:
        w = np.concatenate([wi.reshape(-1) for wi in weights], axis=0)
        sqrt_w = np.sqrt(w)[:, None]
        X = X * sqrt_w
        Y = Y * sqrt_w

    if ridge == 0.0:
        matrix, _, _, _ = np.linalg.lstsq(X, Y, rcond=None)
    else:
        k = X.shape[1]
        matrix = np.linalg.solve(X.T @ X + ridge * np.eye(k), X.T @ Y)
    return matrix


def apply_color_matrix(rgb_linear, matrix, feature_fn=None):
    """rgb_linear: (H, W, 3). matrix: (K, 3), fit_color_matrix()가 만든
    것(K=3이면 feature_fn=None, K=6이면 feature_fn=root_polynomial_features
    등). feature_fn은 fit_color_matrix()에 쓴 것과 반드시 같아야 한다.
    반환: 보정된 (H, W, 3), 음수는 0으로 clip(물리적으로 불가능한 음의
    광량은 없음)."""
    features = rgb_linear if feature_fn is None else feature_fn(rgb_linear)
    out = features @ matrix
    return np.clip(out, 0.0, None)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_raw_baseline.py -v`
Expected: 전부 PASS (기존 `TestFitColorMatrix`/`TestApplyColorMatrix` 6개 + 신규 8개)

- [ ] **Step 5: 기존 호출부 회귀 확인**

Run: `python3 -m pytest tests/test_hybrid_engine.py -v -k "RawBaseline"`
Expected: PASS (`pipeline/engine.py`/`calibrate_profile.py`의 기존 `fit_color_matrix(sources, targets)`/`apply_color_matrix(rgb, matrix)` 2-인자 호출부가 새 기본값으로도 그대로 동작하는지 확인)

- [ ] **Step 6: 커밋**

```bash
git add hybrid_engine/core/raw_baseline.py tests/test_raw_baseline.py
git commit -m "Add root-polynomial feature + WLS/ridge support to fit_color_matrix"
```

---

## Task 2: `chroma_weights()` + `density_weights()`

**Files:**
- Modify: `hybrid_engine/core/raw_baseline.py`
- Test: `tests/test_raw_baseline.py`

**Interfaces:**
- Consumes: 없음(numpy만 사용)
- Produces:
  - `chroma_weights(sources: list[np.ndarray], p: float = 1.0) -> list[np.ndarray]` — 각 원소는 해당 source와 같은 `(H, W)` shape
  - `density_weights(sources: list[np.ndarray], n_bins: int = 16) -> list[np.ndarray]` — 각 원소는 해당 source와 같은 `(H, W)` shape

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_raw_baseline.py` import 줄에 추가:

```python
from hybrid_engine.core.raw_baseline import (
    fit_color_matrix, apply_color_matrix, root_polynomial_features,
    chroma_weights, density_weights,
)
```

파일 끝(`if __name__ == "__main__":` 앞)에 추가:

```python
class TestChromaWeights(unittest.TestCase):
    def test_gray_pixel_gets_zero_weight(self):
        img = np.full((3, 3, 3), 0.5)
        w = chroma_weights([img], p=1.0)[0]
        np.testing.assert_allclose(w, np.zeros((3, 3)), atol=1e-10)

    def test_saturated_pixel_gets_higher_weight_than_gray_pixel(self):
        img = np.zeros((1, 2, 3))
        img[0, 0] = [0.5, 0.5, 0.5]
        img[0, 1] = [0.9, 0.1, 0.5]
        w = chroma_weights([img], p=1.0)[0]
        self.assertGreater(w[0, 1], w[0, 0])

    def test_p_zero_gives_uniform_weight(self):
        rng = np.random.default_rng(18)
        img = rng.uniform(0.0, 1.0, size=(4, 4, 3))
        w = chroma_weights([img], p=0.0)[0]
        np.testing.assert_allclose(w, np.ones((4, 4)))


class TestDensityWeights(unittest.TestCase):
    def test_output_shapes_match_sources(self):
        rng = np.random.default_rng(20)
        imgs = [rng.uniform(0.0, 1.0, size=(6, 6, 3)) for _ in range(3)]
        weights = density_weights(imgs, n_bins=4)
        self.assertEqual(len(weights), 3)
        for w, img in zip(weights, imgs):
            self.assertEqual(w.shape, img.shape[:2])

    def test_overrepresented_color_gets_lower_weight_than_rare_color(self):
        common = np.full((20, 20, 3), 0.3)
        rare = np.full((1, 1, 3), 0.9)
        weights = density_weights([common, rare], n_bins=8)
        common_w = weights[0][0, 0]
        rare_w = weights[1][0, 0]
        self.assertGreater(rare_w, common_w)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_raw_baseline.py -v -k "ChromaWeights or DensityWeights"`
Expected: `ImportError`로 FAIL

- [ ] **Step 3: 구현**

`hybrid_engine/core/raw_baseline.py`의 `apply_color_matrix()` 함수 뒤에 추가:

```python
def chroma_weights(sources, p=1.0):
    """sources: (H, W, 3) linear RGB 소스 리스트. 반환: 각 소스와 같은
    (H, W) shape의 가중치 리스트 - weight = chroma^p, chroma =
    max(r,g,b) - min(r,g,b)(채널 간 최대-최소). 무채색에 가까운
    픽셀일수록 색 매트릭스 피팅에 정보량이 적다는 직관(회색은 어떤
    매트릭스를 곱해도 그레이축 근처에 남는다)을 반영. p=0이면 균등
    가중치(1)와 동일해서 자연스러운 기준선 역할을 한다."""
    result = []
    for s in sources:
        chroma = np.clip(s.max(axis=-1) - s.min(axis=-1), 0.0, None)
        if p == 0:
            result.append(np.ones_like(chroma))
        else:
            result.append(np.power(chroma, p))
    return result


def density_weights(sources, n_bins=16):
    """sources: (H, W, 3) linear RGB 소스 리스트. pooled 전체(모든
    source를 합친) 기준으로 RGB 공간에 성긴 3D 히스토그램(축마다
    n_bins개)을 만들고, weight = 1/sqrt(count_in_bin)으로 과대표집된
    색 영역(같은 챠트를 여러 장 찍은 버스트, 야경의 균일한 하늘처럼
    비슷한 색이 반복되는 큰 영역)을 다운웨이트한다. 반환: 각 소스와
    같은 (H, W) shape의 가중치 리스트.

    교차검증에서 쓸 때는 반드시 그 fold의 학습 데이터(sources)만으로
    새로 호출해야 한다 - held-out 데이터의 분포가 히스토그램에 섞이면
    데이터 누출이다."""
    all_flat = np.concatenate([s.reshape(-1, 3) for s in sources], axis=0)
    lo = all_flat.min(axis=0)
    hi = all_flat.max(axis=0)
    edges = [np.linspace(lo[c], max(hi[c], lo[c] + 1e-6), n_bins + 1) for c in range(3)]

    def bin_indices(flat):
        return np.stack([
            np.clip(np.searchsorted(edges[c], flat[:, c], side="right") - 1, 0, n_bins - 1)
            for c in range(3)
        ], axis=-1)

    all_idx = bin_indices(all_flat)
    all_flat_bin = (all_idx[:, 0] * n_bins + all_idx[:, 1]) * n_bins + all_idx[:, 2]
    counts_per_bin = np.bincount(all_flat_bin, minlength=n_bins ** 3)

    result = []
    for s in sources:
        flat = s.reshape(-1, 3)
        idx = bin_indices(flat)
        flat_bin = (idx[:, 0] * n_bins + idx[:, 1]) * n_bins + idx[:, 2]
        counts = counts_per_bin[flat_bin]
        w = 1.0 / np.sqrt(np.clip(counts, 1.0, None))
        result.append(w.reshape(s.shape[:2]))
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_raw_baseline.py -v`
Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add hybrid_engine/core/raw_baseline.py tests/test_raw_baseline.py
git commit -m "Add chroma-based and density-based pixel weighting for WLS matrix fitting"
```

---

## Task 3: `calibrate_profile.py --mode matrix_features`

**Files:**
- Modify: `hybrid_engine/calibrate_profile.py`
- Test: `tests/test_hybrid_engine.py`

**Interfaces:**
- Consumes: `fit_color_matrix`, `apply_color_matrix`, `root_polynomial_features`, `chroma_weights`, `density_weights`(Task 1/2에서 만듦), `mean_delta_e`(`hybrid_engine.utils.evaluate`, 기존)
- Produces: `run_matrix_features_mode(dataset, n_folds=4, seed=0) -> (baseline_loss: float, results: list, (best_label: str, loo_loss: float, loo_improvement: float))`. `dataset`은 기존 관례대로 `(linear_small, camera_wb, target_small)` 튜플 리스트(`_load_calib_set()`이 만드는 것과 같은 형태).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_hybrid_engine.py`의 `TestRawBaselinePipelineMode` 클래스 뒤(`if __name__ == "__main__":` 앞)에 추가:

```python
class TestMatrixFeaturesMode(unittest.TestCase):
    """calibrate_profile.run_matrix_features_mode - 합성 페어로 그리드서치
    +교차검증 파이프라인 전체가 끝까지 도는지, 알려진 선형 변환을
    낮은 오차로 복원하는지 검증(raw 디코드/실제 hasselblad.json은
    필요 없음 - 순수 매트릭스 그리드서치라 참고용 profile도 안 읽음)."""

    def test_recovers_known_linear_transform_with_low_loo_loss(self):
        from hybrid_engine.calibrate_profile import run_matrix_features_mode

        rng = np.random.default_rng(27)
        known_matrix = np.array([
            [1.1, 0.02, -0.01],
            [0.01, 0.95, 0.02],
            [-0.02, 0.01, 1.15],
        ])
        dataset = []
        for _ in range(8):
            img = rng.uniform(0.05, 0.9, size=(14, 14, 3))
            target = np.clip(img @ known_matrix, 0.0, 1.0)
            dataset.append((img, None, target))

        baseline_loss, results, (best_label, loo_loss, loo_improvement) = \
            run_matrix_features_mode(dataset, n_folds=4)

        self.assertTrue(np.isfinite(baseline_loss))
        self.assertGreater(len(results), 0)
        self.assertIsInstance(best_label, str)
        self.assertTrue(np.isfinite(loo_loss))
        # 여러 페어가 전부 같은 선형 변환을 공유하니 최선 조합의
        # leave-one-out 오차는 낮아야 한다.
        self.assertLess(loo_loss, 1.0)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_hybrid_engine.py -v -k MatrixFeaturesMode`
Expected: `ImportError`(`run_matrix_features_mode` 없음)로 FAIL

- [ ] **Step 3: 구현**

`hybrid_engine/calibrate_profile.py`의 `run_raw_baseline_mode()` 함수(약 885~936번째 줄) 뒤, `_find_matrix_and_recalibrate()` 앞에 추가:

```python
def run_matrix_features_mode(dataset, n_folds=4, seed=0):
    """raw_baseline 3x3 매트릭스를 root-polynomial feature/가중 최소자승
    (WLS)으로 확장한 버전들을 그리드서치+교차검증으로 비교한다(스펙:
    docs/superpowers/specs/2026-07-23-matrix-features-design.md, 후속
    실측 20). run_raw_baseline_mode와 같은 범위(Phase 0 매트릭스만 -
    전체 파이프라인의 tone_core/color_core 재학습은 안 함) - 그래서
    이 함수의 ΔE 숫자는 hasselblad.json의 8.976(파이프라인 전체)과
    직접 비교 대상이 아니라, run_raw_baseline_mode의 매트릭스-단독
    ΔE와 비교해야 공정하다.

    1단계: feature_set x weight_scheme x ridge 그리드를 n_folds-fold
    CV로 스크리닝(매트릭스 피팅은 closed-form이라 빠름). 가중치는 매
    fold마다 그 fold의 학습 데이터에서만 다시 계산한다(데이터 누출
    방지 - density_weights는 pooled 분포를 쓰므로 특히 중요).
    2단계: 스크리닝 1등 조합만 leave-one-out(fold 수 = len(dataset))
    으로 확정 검증한다."""
    from hybrid_engine.core.raw_baseline import (
        fit_color_matrix, apply_color_matrix, root_polynomial_features,
        chroma_weights, density_weights,
    )
    from hybrid_engine.utils.evaluate import mean_delta_e

    raw_sources = [d[0] for d in dataset]
    targets = [d[2] for d in dataset]
    n = len(dataset)

    feature_sets = [("linear", None), ("root_polynomial", root_polynomial_features)]
    weight_schemes = [
        ("none", None, None),
        ("density", "density", None),
        ("chroma_p0.5", "chroma", 0.5),
        ("chroma_p1", "chroma", 1.0),
        ("chroma_p2", "chroma", 2.0),
    ]
    ridge_candidates = [0.0, 1e-4, 1e-3, 1e-2, 1e-1]

    def compute_weights(kind, param, sources):
        if kind is None:
            return None
        if kind == "density":
            return density_weights(sources)
        return chroma_weights(sources, p=param)

    baseline_matrix = fit_color_matrix(raw_sources, targets)
    baseline_loss = float(np.mean(
        [mean_delta_e(apply_color_matrix(s, baseline_matrix), t)
         for s, t in zip(raw_sources, targets)]))
    print(f"기준선(선형, 가중치 없음, ridge=0) in-sample ΔE: {baseline_loss:.3f}")

    combos = []
    for feat_label, feat_fn in feature_sets:
        for weight_label, weight_kind, weight_param in weight_schemes:
            for ridge in ridge_candidates:
                combos.append((feat_label, feat_fn, weight_label, weight_kind, weight_param, ridge))

    rng = np.random.default_rng(seed)
    order = rng.permutation(n)
    folds = np.array_split(order, min(n_folds, n))

    results = []
    for feat_label, feat_fn, weight_label, weight_kind, weight_param, ridge in combos:
        fold_losses = []
        for fold_idx in folds:
            fold_idx_set = set(fold_idx.tolist())
            train_sources = [raw_sources[i] for i in range(n) if i not in fold_idx_set]
            train_targets = [targets[i] for i in range(n) if i not in fold_idx_set]
            train_weights = compute_weights(weight_kind, weight_param, train_sources)
            fold_matrix = fit_color_matrix(
                train_sources, train_targets, feature_fn=feat_fn,
                weights=train_weights, ridge=ridge)
            for i in fold_idx:
                pred = apply_color_matrix(raw_sources[i], fold_matrix, feature_fn=feat_fn)
                fold_losses.append(mean_delta_e(pred, targets[i]))
        cv_loss = float(np.mean(fold_losses))
        label = f"{feat_label} / {weight_label} / ridge={ridge}"
        improvement = (baseline_loss - cv_loss) / baseline_loss * 100
        results.append((label, feat_label, feat_fn, weight_kind, weight_param, ridge, cv_loss, improvement))
        print(f"  {label}: {n_folds}-fold CV ΔE {cv_loss:.3f} ({improvement:+.1f}%)")

    results.sort(key=lambda r: r[6])
    (best_label, best_feat_label, best_feat_fn, best_weight_kind,
     best_weight_param, best_ridge, best_cv, best_improve) = results[0]
    print(f"\n{n_folds}-fold 스크리닝 1등: {best_label} (CV ΔE {best_cv:.3f}, {best_improve:+.1f}%)")

    loo_losses = []
    for held_out in range(n):
        train_sources = [raw_sources[i] for i in range(n) if i != held_out]
        train_targets = [targets[i] for i in range(n) if i != held_out]
        train_weights = compute_weights(best_weight_kind, best_weight_param, train_sources)
        fold_matrix = fit_color_matrix(
            train_sources, train_targets, feature_fn=best_feat_fn,
            weights=train_weights, ridge=best_ridge)
        pred = apply_color_matrix(raw_sources[held_out], fold_matrix, feature_fn=best_feat_fn)
        loo_losses.append(mean_delta_e(pred, targets[held_out]))
    loo_loss = float(np.mean(loo_losses))
    loo_improvement = (baseline_loss - loo_loss) / baseline_loss * 100
    print(f"{best_label} leave-one-out 교차검증 ΔE: {loo_loss:.3f} ({loo_improvement:+.1f}%)")

    return baseline_loss, results, (best_label, loo_loss, loo_improvement)
```

CLI에 연결하기 위해 `main()`의 `argparse` 부분을 수정한다. 먼저 `choices` 리스트(약 1046~1049번째 줄):

```python
    parser.add_argument("--mode",
                         choices=["parametric", "learned", "hue", "hue_chroma", "lab2d", "lab3d",
                                  "spatial", "raw_baseline", "raw_baseline_pipeline", "gray_world",
                                  "gray_world_zoned", "gray_world_strength", "color_cast_algorithm",
                                  "matrix_features"],
```

`help` 문자열 끝(`color_cast_algorithm: ...` 설명이 끝나는 줄, 약 1063번째 줄)에 이어서:

```python
                              "color_cast_algorithm: Gray World 대신 White Patch/Shades of Gray/Gray Edge를 탐색하고 in-sample+LOO ΔE 비교(후속 실측 17) / "
                              "matrix_features: raw_baseline 매트릭스를 root-polynomial feature/가중 최소자승(WLS)/ridge로 확장해서 그리드서치+교차검증(후속 실측 20)")
```

`main()`의 모드 분기(`if args.mode == "color_cast_algorithm":` 블록, 약 1117~1119번째 줄) 바로 뒤에 추가:

```python
    if args.mode == "color_cast_algorithm":
        run_color_cast_algorithm_mode(dataset)
        return

    if args.mode == "matrix_features":
        run_matrix_features_mode(dataset)
        return
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_hybrid_engine.py -v -k MatrixFeaturesMode`
Expected: PASS

- [ ] **Step 5: 전체 테스트 스위트로 회귀 확인**

Run: `python3 -m unittest discover tests -q`
Expected: OK(기존 284개 + 신규 케이스 전부 통과)

- [ ] **Step 6: 커밋**

```bash
git add hybrid_engine/calibrate_profile.py tests/test_hybrid_engine.py
git commit -m "Add calibrate_profile.py --mode matrix_features grid search + LOO CV"
```

---

## Task 4: 실제 데이터로 실행하고 결과 문서화

**Files:**
- Modify: `hybrid_engine/EVALUATION.md`
- Modify (조건부): `hybrid_engine/assets/profiles/hasselblad.json`

**Interfaces:**
- Consumes: Task 3의 `run_matrix_features_mode`(CLI `--mode matrix_features`로 실행)

이 태스크는 실제 `raw_calib_cache/`(15쌍, 1.5GB RAW+JPEG)로 돌려서 나온 **실제 숫자**를 문서화한다 - 결과를 미리 알 수 없으므로, 아래는 실행 절차와 결과에 따른 분기 규칙이다. 실제 실행 시 반드시 아래 두 시나리오 중 하나를 따른다(추측으로 숫자를 메우지 말 것 - 반드시 명령 출력에서 그대로 옮겨 적을 것).

- [ ] **Step 1: 실행**

```bash
python3 -m hybrid_engine.calibrate_profile --mode matrix_features 2>&1 | tee /tmp/matrix_features_output.txt
```

전체 그리드(50 조합 x 4-fold + 15-fold LOO)와 rawpy 디코드(15쌍) 때문에 몇 분 걸릴 수 있다. 완료되면 `/tmp/matrix_features_output.txt`에 다음이 남아있어야 한다: 기준선 in-sample ΔE, 50개 조합 각각의 4-fold CV ΔE와 개선율, 1등 조합 이름, 1등 조합의 leave-one-out ΔE와 개선율.

- [ ] **Step 2: 5% 배포 기준으로 판정**

출력의 마지막 줄(`{best_label} leave-one-out 교차검증 ΔE: ... ({loo_improvement}%)`)에서 `loo_improvement` 값을 확인하고 아래 세 갈래 중 해당하는 것을 따른다.

**(a) `loo_improvement < 5%` (기각)**: Step 3a로. `hasselblad.json`은 건드리지 않는다.

**(b) `loo_improvement >= 5%`이고 1등 조합의 `feature_set == "linear"`**: 매트릭스 shape이 기존과 동일한 (3,3)이라 엔진 변경 없이 바로 교체 가능. Step 3b로.

**(c) `loo_improvement >= 5%`이고 1등 조합의 `feature_set == "root_polynomial"`**: 매트릭스 shape이 (6,3)이라 `pipeline/engine.py`의 Phase 0(`raw_baseline_matrix` 적용부)이 `apply_color_matrix`에 `feature_fn`을 넘기도록 바뀌어야 하고, JSON profile에도 `raw_baseline_feature_set` 같은 필드가 새로 필요하다 - 이건 이 플랜의 범위 밖(스펙의 "범위 밖" 섹션 참고, Task 1~3은 실험 도구만 만드는 것이 목표). Step 3c로.

- [ ] **Step 3a: 기각 문서화**

`hybrid_engine/EVALUATION.md` 맨 끝(825번째 줄, 마지막 문단 뒤)에 추가:

```markdown

**후속 실측 20(2026-07, docs/superpowers/specs/2026-07-23-matrix-features-design.md):
root-polynomial feature + 가중 최소자승(WLS)/ridge 확장 - 기각.**
`fit_color_matrix()`를 확장해서 (1) root-polynomial feature(Finlayson
2015, [r,g,b,sqrt(rg),sqrt(rb),sqrt(gb)] 6항, 노출 불변) (2) 밀도
기반/채도 기반 WLS (3) ridge 정규화를 지원하게 만들고, `feature_set x
weight_scheme x ridge` 50개 조합을 `calibrate_profile.py --mode
matrix_features`로 4-fold 스크리닝 후 1등만 15-fold leave-one-out으로
확정 검증했다(Phase 0 매트릭스 단독 비교 - 전체 파이프라인 재학습은
안 함).

| 조합 | LOO 교차검증 ΔE00 | 변화 |
|---|---|---|
| 기준선(선형, 가중치 없음, ridge=0) | [실제 출력의 baseline_loss] | - |
| **1등: [실제 출력의 best_label]** | [실제 출력의 loo_loss] | [실제 출력의 loo_improvement]% |

5% 배포 기준을 못 넘겨서 `hasselblad.json`은 바꾸지 않는다. [1등 조합이
어느 축이었는지(root-polynomial/WLS/ridge 중 무엇이었는지)와, 상위권
조합들의 공통 패턴(예: 특정 weight_scheme이 전반적으로 조금이라도
나았는지, 아니면 전부 잡음 수준에 수렴했는지)을 실제 4-fold 스크리닝
표(`/tmp/matrix_features_output.txt`)를 보고 1~2문장으로 적을 것.]
`fit_color_matrix()`의 확장 자체(feature_fn/weights/ridge 인자)는
코드에 남겨둔다 - 향후 issue #4의 새 데이터가 들어왔을 때 재시도할 수
있는 도구로 남기는 것이 이 프로젝트의 문서화 철학과 일치한다.
```

(대괄호 `[...]` 부분은 반드시 `/tmp/matrix_features_output.txt`의 실제 값으로 채울 것 - 이 플랜 작성 시점엔 실행 전이라 알 수 없다.)

Step 4로 이동.

- [ ] **Step 3b: 채택(선형 + WLS/ridge) 문서화 및 배포**

`raw_calib_cache/`로 최종 매트릭스를 전체 15쌍으로 다시 적합(1등 조합의 weight_scheme/ridge, `feature_fn=None`)해서 `hasselblad.json`의 `raw_baseline_matrix`를 갱신해야 한다. 아래 스니펫을 `python3` 인터랙티브 셸이나 임시 스크립트로 실행:

```python
import json, os
from hybrid_engine.calibrate_profile import _load_calib_set
from hybrid_engine.core.raw_baseline import fit_color_matrix, chroma_weights, density_weights

dataset = _load_calib_set()
raw_sources = [d[0] for d in dataset]
targets = [d[2] for d in dataset]

# 아래 두 줄은 실제 1등 조합의 weight_kind/weight_param/ridge로 채울 것
weights = None  # 예: density_weights(raw_sources) 또는 chroma_weights(raw_sources, p=1.0)
ridge = 0.0     # 실제 1등 조합의 ridge 값

matrix = fit_color_matrix(raw_sources, targets, weights=weights, ridge=ridge)

profile_path = "hybrid_engine/assets/profiles/hasselblad.json"
with open(profile_path, encoding="utf-8") as f:
    profile = json.load(f)
profile["raw_baseline_matrix"] = matrix.tolist()
profile["_comment"] = (
    "v1.4 - 후속 실측 20(root-polynomial+WLS/ridge 그리드서치)에서 "
    "[실제 1등 조합 이름]이 raw_baseline 매트릭스 단독 기준 leave-one-out "
    "ΔE00 [실제 개선율]% 개선을 보여 채택. Phase 0 매트릭스만 교체했고 "
    "Phase 1(tone_core)/Phase 2(color_core)는 v1.3 값 그대로 - 재학습은 "
    "별도 후속 작업(raw_baseline_pipeline 모드로 매트릭스+톤/채도 동시 "
    "재학습)에서 다룰 것. 자세한 실측은 EVALUATION.md 후속 실측 20 참고."
)
with open(profile_path, "w", encoding="utf-8") as f:
    json.dump(profile, f, ensure_ascii=False, indent=2)
    f.write("\n")
```

그 다음 `EVALUATION.md`에 Step 3a와 같은 표 형식으로 "채택"이라고 명시해서 추가(문구를 "5% 배포 기준을 넘겨서 `hasselblad.json`을 v1.4로 갱신했다"로 바꿀 것).

Step 4로 이동.

- [ ] **Step 3c: 유망하지만 보류(root-polynomial) 문서화**

`EVALUATION.md`에 Step 3a와 같은 표 형식으로 추가하되, 결론 문단을 다음으로 대체:

```markdown
5% 배포 기준은 넘겼지만 1등 조합이 root-polynomial feature(6-항, (6,3)
매트릭스)라 기존 (3,3) 매트릭스를 그대로 곱하는 `pipeline/engine.py`의
Phase 0 적용부와 JSON profile 스키마를 바꿔야 배포할 수 있다 - 이번
작업 범위 밖(docs/superpowers/specs/2026-07-23-matrix-features-design.md
"범위 밖" 참고)이라 `hasselblad.json`은 이번엔 바꾸지 않는다. `pipeline/
engine.py`가 `raw_baseline_feature_set` profile 키를 읽어서 `apply_color_
matrix`에 맞는 `feature_fn`을 골라 넘기도록 확장하는 게 다음 후속
작업으로 필요하다.
```

Step 4로 이동.

- [ ] **Step 4: 테스트 재실행**

Run: `python3 -m unittest discover tests -q`
Expected: OK (Step 3b에서 `hasselblad.json`을 바꿨다면 `tests/test_hybrid_engine.py`의 `--evaluate`/기존 profile 관련 테스트가 여전히 통과하는지 특히 확인)

- [ ] **Step 5: 커밋**

Step 3a(기각)를 따랐다면:
```bash
git add hybrid_engine/EVALUATION.md
git commit -m "Document follow-up measurement 20: root-polynomial/WLS matrix grid search rejected"
```

Step 3b(채택)를 따랐다면:
```bash
git add hybrid_engine/EVALUATION.md hybrid_engine/assets/profiles/hasselblad.json
git commit -m "Ship v1.4: root-polynomial/WLS matrix fitting, +N% LOO CV over v1.3"
```
(`N`은 실제 개선율로 바꿀 것)

Step 3c(보류)를 따랐다면:
```bash
git add hybrid_engine/EVALUATION.md
git commit -m "Document follow-up measurement 20: root-polynomial matrix clears CV bar but needs engine changes to deploy"
```

---

## Self-Review 결과

- **스펙 커버리지**: 스펙의 "목표" 4개 항목(fit_color_matrix 확장/새 모드/EVALUATION.md 문서화/5% 배포 기준) 전부 Task 1~4가 커버. "범위 밖"에 명시한 항목(새 데이터 확보, LUT/RBF/gradient boosting 재시도, brands/*.py 변경)은 어느 태스크에도 없음 - 일치.
- **플레이스홀더 스캔**: Task 4의 대괄호(`[실제 출력...]`)는 실행 전 값을 알 수 없는 실측 작업의 불가피한 특성이며, 정확히 어느 명령의 어느 출력값을 쓸지와 분기 조건을 구체적으로 명시해서 "TBD"류 방치가 아님. 나머지 태스크는 전부 완전한 코드.
- **타입/시그니처 일관성**: `fit_color_matrix(sources, targets, feature_fn=None, weights=None, ridge=0.0)`과 `apply_color_matrix(rgb_linear, matrix, feature_fn=None)` 시그니처가 Task 1(정의)과 Task 3(`run_matrix_features_mode`에서 호출)에서 동일하게 사용됨을 확인. `chroma_weights(sources, p=1.0)`/`density_weights(sources, n_bins=16)`도 Task 2(정의)와 Task 3(호출)에서 일치.

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-23-matrix-features-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
