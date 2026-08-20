# HNCS Structural Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research and document HNCS's real 4-stage render pipeline (vs. `apply_hncs()`'s 3-stage simplification), build a separate experimental module that mirrors the real structure, and measure via leave-one-out cross-validation whether the more accurate structure actually improves ΔE — recording the result honestly either way.

**Architecture:** A pure-documentation bilingual research doc (no code) sits alongside a new `hybrid_engine/research/` subpackage that implements a 4-stage pipeline (WB → illuminant-cluster-specific 3×3 matrix → illuminant-cluster-specific chroma LUT → shared film curve) using existing `hybrid_engine` RAW/matrix-fitting infrastructure. A `tools/` evaluation script fits per-cluster matrices and chroma-LUT parameters via leave-one-out cross-validation over the 13 real raw+jpeg pairs, and measures `apply_hncs()`'s own ΔE on the same 13 pairs for a fair comparison. Results go into `hybrid_engine/EVALUATION.md` regardless of outcome.

**Tech Stack:** Python, NumPy, OpenCV (`cv2`), `colour-science`, `rawpy` (via existing `hybrid_engine.utils.io`), `exiftool` (via existing `hybrid_engine.utils.exif`), `unittest`.

## Global Constraints

- `brands/hasselblad.py`'s `apply_hncs()` is the Stable, in-production function and **must never be modified** by any task in this plan, regardless of this experiment's outcome.
- The experiment population is the **13 real raw+jpeg pairs** documented in `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` (14 lines − 1 header). The 2 extra cached raw files in `raw_calib_cache/` (`x2dii-chart-31325`, `x2dii-chart-31330`) belong to a different, unrelated dataset (X2D II ColorChecker chart contribution) and must be excluded.
- Illuminant clustering: 2 clusters by `AsShotNeutral[0] / AsShotNeutral[2]` (R/B ratio), threshold **0.9**. `"cluster_a"` = R/B < 0.9 (10 pairs, range 0.36–0.66). `"cluster_b"` = R/B ≥ 0.9 (3 pairs, range 1.13–1.32).
- `raw_calib_cache/` is git-ignored and already populated locally in this environment with all 15 cached raw+target files (13 real pairs used by this plan + 2 excluded chart files) — do not attempt to re-download it.
- No video-engine integration, no ≥4-illuminant clustering, no reproduction of Phocus's actual proprietary matrix/LUT values — all explicitly out of scope per the spec.
- ΔE means CIEDE2000 via `hybrid_engine.utils.evaluate.mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000")`, this project's established convention.
- Results (win or lose) get recorded honestly in `hybrid_engine/EVALUATION.md`, following this project's existing convention (see the tail of that file for format precedent).
- Spec: `docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md` (already corrected: 13 pairs, R/B-ratio math, cluster_a/cluster_b naming, threshold 0.9, 13-fold LOOCV).

---

### Task 1: `hybrid_engine/research/hncs_structural.py` — experimental 4-stage pipeline module

**Files:**
- Create: `hybrid_engine/research/__init__.py`
- Create: `hybrid_engine/research/hncs_structural.py`
- Test: `tests/test_hncs_structural.py`

**Interfaces:**
- Consumes: `hybrid_engine.utils.io.decode_raw_native(raw_path)` → `(H,W,3)` float64 linear RGB, camera-native (no WB, no matrix). `hybrid_engine.utils.exif.read_as_shot_neutral(path)` → `(3,)` float64 array or `None`, format `[R, G(=1), B]`. `hybrid_engine.core.raw_baseline.apply_color_matrix(rgb_linear, matrix, feature_fn=None)` → clipped `(H,W,3)`. `core.curve.film_curve(x, toe_lift=0.001, shoulder_start=0.78, white_point=1.0)` → elementwise, any array shape.
- Produces: `decode_and_white_balance(raw_path)` → `(H,W,3)` float64. `classify_illuminant_cluster(as_shot_neutral)` → `"cluster_a"` or `"cluster_b"`. `apply_chroma_lut(img_rgb, sat_mult, hue_shift_deg)` → `(H,W,3)` float64 in `[0,1]`. `apply_hncs_structural(raw_path, illuminant_matrices, chroma_lut_params, toe_lift, shoulder_start, white_point)` → `(H,W,3)` float64, where `illuminant_matrices`/`chroma_lut_params` are `{"cluster_a": ..., "cluster_b": ...}` dicts (matrix `(3,3)` ndarray; chroma params `(sat_mult, hue_shift_deg)` tuple). `CLUSTER_THRESHOLD_R_OVER_B = 0.9` module constant. Task 3's evaluation script imports all four functions plus the constant directly from this module.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_hncs_structural.py`:

```python
import unittest
from unittest.mock import patch

import numpy as np

from hybrid_engine.research.hncs_structural import (
    CLUSTER_THRESHOLD_R_OVER_B,
    apply_chroma_lut,
    apply_hncs_structural,
    classify_illuminant_cluster,
    decode_and_white_balance,
)


class TestClassifyIlluminantCluster(unittest.TestCase):
    def test_below_threshold_is_cluster_a(self):
        # R/B = 0.4 / 0.6 = 0.667 < 0.9
        self.assertEqual(
            classify_illuminant_cluster(np.array([0.4, 1.0, 0.6])), "cluster_a")

    def test_at_or_above_threshold_is_cluster_b(self):
        # R/B = 1.2 / 1.0 = 1.2 >= 0.9
        self.assertEqual(
            classify_illuminant_cluster(np.array([1.2, 1.0, 1.0])), "cluster_b")

    def test_exactly_at_threshold_is_cluster_b(self):
        # R/B = 0.9 / 1.0 = 0.9, boundary is inclusive on the cluster_b side
        self.assertEqual(
            classify_illuminant_cluster(np.array([0.9, 1.0, 1.0])), "cluster_b")

    def test_uses_module_threshold_constant(self):
        self.assertEqual(CLUSTER_THRESHOLD_R_OVER_B, 0.9)


class TestDecodeAndWhiteBalance(unittest.TestCase):
    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_divides_native_rgb_by_as_shot_neutral(self, mock_decode, mock_asn):
        mock_decode.return_value = np.array([[[0.4, 1.0, 0.6]]])
        mock_asn.return_value = np.array([0.4, 1.0, 0.6])
        result = decode_and_white_balance("fake.3FR")
        np.testing.assert_allclose(result, np.array([[[1.0, 1.0, 1.0]]]))

    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_raises_when_as_shot_neutral_missing(self, mock_decode, mock_asn):
        mock_decode.return_value = np.zeros((2, 2, 3))
        mock_asn.return_value = None
        with self.assertRaises(ValueError):
            decode_and_white_balance("fake.3FR")


class TestApplyChromaLut(unittest.TestCase):
    def test_identity_when_sat_mult_1_and_hue_shift_0(self):
        rng = np.random.default_rng(0)
        img = rng.uniform(0.05, 0.9, size=(8, 8, 3))
        out = apply_chroma_lut(img, sat_mult=1.0, hue_shift_deg=0.0)
        np.testing.assert_allclose(out, img, atol=1e-3)

    def test_hue_shift_is_360_periodic(self):
        rng = np.random.default_rng(1)
        img = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        out_0 = apply_chroma_lut(img, sat_mult=1.0, hue_shift_deg=0.0)
        out_360 = apply_chroma_lut(img, sat_mult=1.0, hue_shift_deg=360.0)
        np.testing.assert_allclose(out_0, out_360, atol=1e-3)

    def test_sat_mult_zero_desaturates_to_gray(self):
        img = np.array([[[0.9, 0.1, 0.1]]])  # saturated red
        out = apply_chroma_lut(img, sat_mult=0.0, hue_shift_deg=0.0)
        r, g, b = out[0, 0]
        self.assertAlmostEqual(r, g, delta=1e-3)
        self.assertAlmostEqual(g, b, delta=1e-3)

    def test_output_shape_matches_input(self):
        rng = np.random.default_rng(2)
        img = rng.uniform(0.05, 0.9, size=(5, 7, 3))
        out = apply_chroma_lut(img, sat_mult=1.1, hue_shift_deg=3.0)
        self.assertEqual(out.shape, img.shape)


class TestApplyHncsStructural(unittest.TestCase):
    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_identity_matrix_and_chroma_matches_film_curve_directly(
            self, mock_decode, mock_asn):
        rng = np.random.default_rng(3)
        native = rng.uniform(0.02, 0.3, size=(4, 4, 3))
        as_shot_neutral = np.array([0.4, 1.0, 0.6])  # R/B=0.667 -> cluster_a
        mock_decode.return_value = native
        mock_asn.return_value = as_shot_neutral
        wb_rgb = native / as_shot_neutral

        matrices = {"cluster_a": np.eye(3), "cluster_b": np.eye(3)}
        chroma_params = {"cluster_a": (1.0, 0.0), "cluster_b": (1.0, 0.0)}
        result = apply_hncs_structural(
            "fake.3FR", matrices, chroma_params,
            toe_lift=0.001, shoulder_start=0.78, white_point=1.0)

        from core.curve import film_curve
        expected = film_curve(wb_rgb, toe_lift=0.001, shoulder_start=0.78,
                               white_point=1.0)
        np.testing.assert_allclose(result, expected, atol=1e-2)

    @patch("hybrid_engine.research.hncs_structural.read_as_shot_neutral")
    @patch("hybrid_engine.research.hncs_structural.decode_raw_native")
    def test_selects_matrix_for_cluster_b_when_r_over_b_high(
            self, mock_decode, mock_asn):
        native = np.full((3, 3, 3), 0.3)
        as_shot_neutral = np.array([1.2, 1.0, 1.0])  # R/B=1.2 -> cluster_b
        mock_decode.return_value = native
        mock_asn.return_value = as_shot_neutral

        # cluster_a gets a matrix that would blow up the output (2x gain);
        # cluster_b keeps identity. If the wrong matrix is picked, the
        # shoulder/highlight clipping in film_curve makes the two diverge.
        matrices = {"cluster_a": np.eye(3) * 2.0, "cluster_b": np.eye(3)}
        chroma_params = {"cluster_a": (1.0, 0.0), "cluster_b": (1.0, 0.0)}
        result = apply_hncs_structural(
            "fake.3FR", matrices, chroma_params,
            toe_lift=0.001, shoulder_start=0.78, white_point=1.0)

        from core.curve import film_curve
        wb_rgb = native / as_shot_neutral
        expected = film_curve(wb_rgb, toe_lift=0.001, shoulder_start=0.78,
                               white_point=1.0)
        np.testing.assert_allclose(result, expected, atol=1e-2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_hncs_structural -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'hybrid_engine.research'`

- [ ] **Step 3: Write the implementation**

Create `hybrid_engine/research/__init__.py`:

```python
"""연구용 실험 모듈 - 아직 Stable 파이프라인에 올리지 않은 것들을 담는
공간. 여기 있는 어떤 것도 brands/*.py의 Stable apply_* 함수를 대체하지
않는다."""
```

Create `hybrid_engine/research/hncs_structural.py`:

```python
"""HNCS(Hasselblad Natural Colour Solution) 실제 4단계 렌더 구조를
미러링한 연구용 실험 모듈.

brands/hasselblad.py의 apply_hncs()(⭐ Stable, 실사용 중, 3단계 단순화:
exposure_gamma LUT -> CLAHE -> film_curve LUT)와 완전히 별도다.
apply_hncs()는 이 모듈에서 절대 수정하지 않는다.

구조 대비와 출처는 docs/hncs_structural_research.md 참고. 설계 근거는
docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md.

실제 HNCS 파이프라인(조사 결과, 4단계):
1. RAW 센서 데이터
2. 조명별(illuminant-specific) 3x3 컬러 매트릭스
3. 그 매트릭스와 짝지어진 조명별 chroma LUT (hue/채도 보정)
4. Hasselblad Film Curve (공유, 조명과 무관)

이 모듈은 표본(13쌍 raw+jpeg)이 뒷받침하는 만큼만 근사한다: 조명
"최소 4종" 대신 AsShotNeutral R/B 비율 기반 2-클러스터
("cluster_a"/"cluster_b", 임계값 CLUSTER_THRESHOLD_R_OVER_B)로 단순화.
"""
import cv2
import numpy as np

from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import decode_raw_native

CLUSTER_THRESHOLD_R_OVER_B = 0.9


def decode_and_white_balance(raw_path):
    """RAW -> 카메라 네이티브 linear RGB에 AsShotNeutral로 WB만 적용한
    상태(HNCS 2단계 - 조명별 매트릭스 - 가 받는 입력에 해당). WB
    게인만 걸고 아직 어떤 색매트릭스도 안 걸린 상태를 만들어야 하므로
    decode_raw()(libraw 자체 매트릭스까지 같이 적용)가 아니라
    decode_raw_native()(WB/매트릭스 둘 다 미적용)에서 시작해 직접
    AsShotNeutral로 나눈다."""
    native_rgb = decode_raw_native(raw_path)
    as_shot_neutral = read_as_shot_neutral(raw_path)
    if as_shot_neutral is None:
        raise ValueError(f"AsShotNeutral 태그를 읽을 수 없음: {raw_path}")
    return native_rgb / as_shot_neutral


def classify_illuminant_cluster(as_shot_neutral, threshold=CLUSTER_THRESHOLD_R_OVER_B):
    """AsShotNeutral[0]/AsShotNeutral[2](R/B 비율)로 2-클러스터 분류.
    threshold 미만이면 "cluster_a"(실측 10쌍, R/B 0.36~0.66), 이상이면
    "cluster_b"(실측 3쌍, R/B 1.13~1.32). 기본 임계값 0.9는 두 그룹
    사이(0.66~1.13) 아무 값이나 가능해서 중간값으로 고른 것."""
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return "cluster_a" if r_over_b < threshold else "cluster_b"


def apply_chroma_lut(img_rgb, sat_mult, hue_shift_deg):
    """조명 클러스터별 hue/채도 보정(HNCS 3단계). HSV로 변환해 S
    채널에 sat_mult를 곱하고 H 채널에 hue_shift_deg를 더한 뒤 되돌린다.
    표본이 작아 저차원(파라미터 2개)으로 제한 - 그 이상(예: hue별 배열)은
    이 프로젝트가 반복적으로 경고해온 과적합 함정과 같다.

    img_rgb가 [0,1]을 벗어나는 하이라이트를 담고 있을 수 있는데, HSV
    변환 전에 [0,1]로 clip한다 - 뒤이은 film_curve 단계가 셔츠/롤오프를
    처리하는 대상 범위도 [0,1]이라 여기서 먼저 맞춘다(연구용 단순화로
    문서에 명시)."""
    clipped = np.clip(img_rgb, 0.0, 1.0).astype(np.float32)
    hsv = cv2.cvtColor(clipped, cv2.COLOR_RGB2HSV)
    hsv[..., 0] = (hsv[..., 0] + hue_shift_deg) % 360.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat_mult, 0.0, 1.0)
    out = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return np.clip(out, 0.0, 1.0).astype(np.float64)


def apply_hncs_structural(raw_path, illuminant_matrices, chroma_lut_params,
                           toe_lift, shoulder_start, white_point):
    """4단계 파이프라인: WB적용 네이티브 RGB -> 클러스터별 3x3 매트릭스
    -> 클러스터별 chroma LUT -> 공유 필름커브.

    illuminant_matrices/chroma_lut_params는 {"cluster_a": ..., "cluster_b": ...}
    형태의 피팅 결과를 받는다(피팅 자체는 tools/evaluate_hncs_structural.py).
    필름커브만 클러스터로 안 나누고 공유 - 톤(밝기 분포)은 조명보다
    노출/장면에 더 좌우된다고 보는 판단(v11에서 apply_hncs()의
    toe_lift/shoulder_start를 표본이 작아 바꾸지 않은 전례와 같은
    이유)."""
    wb_rgb = decode_and_white_balance(raw_path)
    as_shot_neutral = read_as_shot_neutral(raw_path)
    cluster = classify_illuminant_cluster(as_shot_neutral)
    matrixed = apply_color_matrix(wb_rgb, illuminant_matrices[cluster])
    sat_mult, hue_shift_deg = chroma_lut_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    return film_curve(chroma_applied, toe_lift=toe_lift,
                       shoulder_start=shoulder_start, white_point=white_point)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_hncs_structural -v`
Expected: all tests PASS (10 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python3 -m unittest discover -s tests`
Expected: all existing tests still PASS, plus the 10 new ones (baseline was 430 at the end of the prior plan)

- [ ] **Step 6: Commit**

```bash
git add hybrid_engine/research/__init__.py hybrid_engine/research/hncs_structural.py tests/test_hncs_structural.py
git commit -m "Add hncs_structural.py: experimental 4-stage HNCS pipeline mirror"
```

---

### Task 2: Bilingual research document

**Files:**
- Create: `docs/hncs_structural_research.md`
- Create: `docs/hncs_structural_research.en.md`

**Interfaces:**
- Consumes: nothing (pure documentation).
- Produces: nothing consumed by later tasks' code — Task 4 appends a results section to these same two files after Task 3's evaluation run.

- [ ] **Step 1: Write `docs/hncs_structural_research.md`**

```markdown
# HNCS 구조 리서치: 실제 파이프라인 vs `apply_hncs()`

*[English](hncs_structural_research.en.md)*

[메인 README](../README.md)로 돌아가기.

`brands/hasselblad.py`의 `apply_hncs()`(⭐ Stable, 실사용 중)는 실제
HNCS 파이프라인을 3단계로 단순화한 근사다. 이 문서는 실제 구조를
출처와 함께 정리하고, 그 구조를 반영한 별도의 **연구용** 실험 모듈
(`hybrid_engine/research/hncs_structural.py`)이 실제로 정확도를
개선하는지 측정한 결과를 담는다. `apply_hncs()` 자체는 이 리서치로
수정되지 않는다 - 설계 근거는
[2026-07-28-hncs-structural-research-design.md](superpowers/specs/2026-07-28-hncs-structural-research-design.md).

## 출처

- Hasselblad 공식 사이트: hasselblad.com/learn/hasselblad-natural-colour-solution
  - "필름커브 톤, 지각보상 대비, rich saturation 무조작, 스킨톤
    hue/채도 무조작, X시스템 전체 일관 적용" 5개 설계 원칙을 공개.
    **파이프라인의 정확한 단계 수/구현 방식은 공개하지 않음.**
- blog.tonalphoto.com, "How HNCS Actually Works" - Phocus `.phos`
  사이드카를 바이트 단위로 diff한 독립 기술 분석. 저자 본인이 글
  안에서 "공식 지원/가이드가 아니라 개인적 조사와 테스트"라고 명시.
  **공식 화이트페이퍼는 존재하지 않는다** - 검색으로 확인.
- "최소 4개 조명(Tungsten/Low Tungsten/Flash/Flash-Daylight)"이라는
  구체적 개수는 위 블로그 글이 다시 인용한 Luminous Landscape 포럼의
  커뮤니티 기술 분석 출처 - Hasselblad가 공개한 숫자가 아니다.

세 출처의 확실성 등급이 다르다: 공식 사이트(설계 원칙, 공식) >
tonalphoto.com(`.phos` 바이트 diff, 비공식이지만 직접 실측) >
Luminous Landscape 포럼 인용(비공식, 재인용).

## 구조 대비

| 단계 | `apply_hncs()` (Stable, 실사용) | 실제 HNCS (조사 결과) |
|---|---|---|
| 입력 | RAW를 이미 카메라 JPEG로 디코드한 8비트 BGR | RAW 센서 데이터 (16비트) |
| 1 | 전역 노출 리프트 (`exposure_gamma` LUT, v10 추가) | 조명별(illuminant-specific) 3x3 컬러 매트릭스 - 최소 4종 중 WB 설정에 따라 선택 |
| 2 | CLAHE (지각보상 대비, 사진 모드만 - 비디오는 생략) | 그 매트릭스와 짝지어진 chroma LUT (해당 광원에 맞춘 hue/채도 보정) |
| 3 | `film_curve` LUT (toe/mid/shoulder 톤커브) | Hasselblad Film Curve (하이라이트 롤오프 + 섀도우 전환) |
| 화이트밸런스 변경 시 | 영향 없음 (JPEG 입력이라 WB는 이미 반영된 상태) | 2단계부터 전체 재실행 (매트릭스+LUT가 조명에 종속) |
| hue/채도 조작 | 없음 (원칙 그대로 무조작) | 있음 - 다만 **프리셋 간에는** 없음(아래 참고) |

**단순화의 핵심**: `apply_hncs()`가 근거로 삼은 "스킨톤 hue/채도 무조작"
원칙은 프리셋(Standard/Nature/Portrait/Product/Square Crop) 비교에서는
맞다 - `.phos` 사이드카 직접 비교 결과 Brightness/Contrast/Saturation이
5개 프리셋 전부 0/0/0으로 동일했다. 하지만 그건 "프리셋끼리 색과학을
안 바꾼다"는 뜻이지 "파이프라인 전체에 채도 보정이 없다"는 뜻이
아니었다 - 2단계(조명별 chroma LUT)는 프리셋과 무관하게 항상 존재하는
별도 단계다.

## 실험: 구조를 더 정확히 따라가면 ΔE가 좋아지는가

`hybrid_engine/research/hncs_structural.py`가 위 4단계를 미러링한다
(RAW 기반, WB 적용 -> 클러스터별 3x3 매트릭스 -> 클러스터별 chroma LUT
-> 공유 필름커브). 표본(13쌍의 raw+jpeg 페어,
`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv`)이 "최소 4개 조명"을
뒷받침하지 못해 `AsShotNeutral`의 R/B 비율 기반 2-클러스터
(`cluster_a`/`cluster_b`, 임계값 0.9)로 축소했다 - 10 대 3의 뚜렷한
분리가 있어 시도할 근거는 있지만, 소수 클러스터가 3쌍뿐이라 통계적으로
얇다.

leave-one-out 교차검증(13회, 매회 1쌍을 held-out으로 빼고 나머지로
피팅)으로 이 실험 모듈과 `apply_hncs()`(같은 raw 기반 baseline에
적용, 공정 비교) 양쪽의 ΔE(CIEDE2000)를 같은 13쌍에 대해 재측정했다.

<!-- 결과는 tools/evaluate_hncs_structural.py 실행 후 채워짐 -->

## 한계

- **Phocus의 실제 매트릭스/LUT 값과 다르다** - 우리가 가진 13쌍짜리
  raw+jpeg 페어로 새로 피팅한 근사치. Hasselblad의 비공개 자산을
  재현한 게 아니다.
- **조사 출처가 비공식이다** - 위 "출처" 절 참고. 확실성 등급이 다른
  정보가 섞여 있다.
- **2-클러스터는 실제 구조(4개 이상)의 축소판** - 표본 부족으로 인한
  타협이지 "2개가 맞다"는 주장이 아니다.
- **표본 13쌍, 클러스터당 3~10쌍(소수 클러스터 3쌍)** - 통계적으로
  매우 얇음. 교차검증 결과가 양수든 음수든 표본이 늘어나면 재확인이
  필요하다.
- **`apply_hncs()`를 대체하지 않는다** - 이 실험이 이겨도 이 스펙
  범위에서는 Stable로 승격하지 않는다(별도 논의).
```

- [ ] **Step 2: Write `docs/hncs_structural_research.en.md`**

```markdown
# HNCS Structural Research: the real pipeline vs. `apply_hncs()`

*[한국어](hncs_structural_research.md)*

Back to the [main README](../README.md).

`brands/hasselblad.py`'s `apply_hncs()` (⭐ Stable, in production) is a
3-stage simplification of the real HNCS pipeline. This document lays out
the real structure with sources, and records whether a separate
**research-only** experimental module
(`hybrid_engine/research/hncs_structural.py`) that mirrors that structure
actually improves accuracy. `apply_hncs()` itself is not modified by this
research - design rationale:
[2026-07-28-hncs-structural-research-design.md](superpowers/specs/2026-07-28-hncs-structural-research-design.md).

## Sources

- Hasselblad's official site: hasselblad.com/learn/hasselblad-natural-colour-solution
  - Publishes 5 design principles: film-curve tonality, perceptual
    contrast, no rich-saturation manipulation, no skin-tone hue/saturation
    manipulation, consistent application across the X System.
    **Does not disclose the exact pipeline stage count or implementation.**
- blog.tonalphoto.com, "How HNCS Actually Works" - an independent
  technical analysis based on a byte-level diff of Phocus `.phos`
  sidecars. The author explicitly states in the post that this is
  "personal research and testing, not official support or guidance."
  **No official whitepaper exists** - confirmed by search.
- The specific "at least 4 illuminants (Tungsten/Low Tungsten/Flash/
  Flash-Daylight)" figure is itself cited by that blog post from a
  Luminous Landscape forum community technical analysis - not a number
  Hasselblad has published.

The three sources carry different confidence levels: the official site
(design principles, official) > tonalphoto.com (byte-level `.phos` diff,
unofficial but directly measured) > the Luminous Landscape forum citation
(unofficial, second-hand).

## Structural comparison

| Stage | `apply_hncs()` (Stable, in production) | Real HNCS (research findings) |
|---|---|---|
| Input | RAW already decoded to an 8-bit BGR camera JPEG | Raw sensor data (16-bit) |
| 1 | Global exposure lift (`exposure_gamma` LUT, added in v10) | Illuminant-specific 3x3 color matrix - one of at least 4, selected by white balance |
| 2 | CLAHE (perceptual contrast, photo mode only - skipped for video) | Chroma LUT paired with that matrix (hue/saturation correction tuned to that light source) |
| 3 | `film_curve` LUT (toe/mid/shoulder tone curve) | Hasselblad Film Curve (highlight rolloff + shadow transition) |
| On white-balance change | No effect (JPEG input already has WB baked in) | Stages 2 onward fully re-run (matrix + LUT depend on the illuminant) |
| Hue/saturation manipulation | None (the stated principle, applied as-is) | Present - but **not between presets** (see below) |

**The core of the simplification**: the "no skin-tone hue/saturation
manipulation" principle `apply_hncs()` relies on is true *between
presets* - a direct byte comparison of `.phos` sidecars found
Brightness/Contrast/Saturation identical (0/0/0) across all 5 presets
(Standard/Nature/Portrait/Product/Square Crop). But that means presets
don't change the color science relative to each other, not that the
pipeline has no saturation correction anywhere - stage 2 (the
illuminant-specific chroma LUT) is a separate stage that exists
regardless of preset.

## Experiment: does a more accurate structure actually improve ΔE?

`hybrid_engine/research/hncs_structural.py` mirrors the 4 stages above
(RAW-based, WB applied -> cluster-specific 3x3 matrix -> cluster-specific
chroma LUT -> shared film curve). The sample (13 raw+jpeg pairs,
`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv`) can't support "at
least 4 illuminants," so this was reduced to a 2-cluster split by the
`AsShotNeutral` R/B ratio (`cluster_a`/`cluster_b`, threshold 0.9) - a
clear 10-vs-3 separation gives grounds to try it, but the minority
cluster at only 3 pairs is statistically thin.

Leave-one-out cross-validation (13 runs, each holding out 1 pair and
fitting on the rest) re-measured ΔE (CIEDE2000) for both this
experimental module and `apply_hncs()` (applied to the same raw-derived
baseline, for a fair comparison) on the same 13 pairs.

<!-- Results filled in after running tools/evaluate_hncs_structural.py -->

## Limitations

- **Differs from Phocus's actual matrix/LUT values** - this is a new fit
  from our own 13 raw+jpeg pairs, not a reproduction of Hasselblad's
  proprietary asset.
- **Research sources are unofficial** - see "Sources" above; information
  of differing confidence levels is mixed together.
- **The 2-cluster model is a reduction of the real structure (4+)** - a
  compromise forced by sample size, not a claim that 2 is correct.
- **13 pairs total, 3-10 per cluster (minority cluster: 3)** -
  statistically thin. Whether the cross-validation result is positive or
  negative, it needs re-checking as the sample grows.
- **Does not replace `apply_hncs()`** - even if this experiment wins, it
  is not promoted to Stable within this plan's scope (that's a separate
  discussion).
```

- [ ] **Step 3: Verify both files render (no broken markdown table syntax)**

Run: `python3 -c "import pathlib; [print(p, len(pathlib.Path(p).read_text())) for p in ['docs/hncs_structural_research.md', 'docs/hncs_structural_research.en.md']]"`
Expected: both files print non-zero lengths, no exception

- [ ] **Step 4: Commit**

```bash
git add docs/hncs_structural_research.md docs/hncs_structural_research.en.md
git commit -m "Add bilingual HNCS structural research document"
```

---

### Task 3: `tools/evaluate_hncs_structural.py` — calibration + leave-one-out cross-validation

**Files:**
- Create: `tools/evaluate_hncs_structural.py`
- Test: `tests/test_evaluate_hncs_structural.py`

**Interfaces:**
- Consumes: everything from Task 1 (`decode_and_white_balance`, `classify_illuminant_cluster`, `apply_chroma_lut`, `apply_hncs_structural`). `hybrid_engine.core.raw_baseline.fit_color_matrix(sources, targets, ridge=0.0)` → `(3,3)` matrix. `hybrid_engine.core.raw_baseline.apply_color_matrix`. `core.curve.film_curve`. `hybrid_engine.utils.evaluate.mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000")` and `load_image_linear_for_evaluate(target_path, result_shape, resize_to_match=True)`. `hybrid_engine.utils.io.decode_raw(raw_path)`, `decode_raw_native(raw_path)`, `load_image_linear(path, resize_to=None)`. `brands.hasselblad.apply_hncs(img_bgr, ...)` (uint8 BGR in/out). `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` (13 rows, `jpeg_url` column gives the basename used to find cache files). `raw_calib_cache/{name}.jpg.3FR` or `.fff` (raw) and `raw_calib_cache/{name}.jpg.target.jpg` (target JPEG).
- Produces: `_pair_names()`, `_resize_max_dim(img, max_dim)` (unit-tested, portable helpers). `load_pairs()`, `run_loocv()`, `main()` (full pipeline, verified by actually running the script — not committed unit tests, matching this project's existing precedent for one-off experiment scripts like `tools/analyze_camera_native_matrix.py`, which also has no test file).

**Design notes for the implementer:**

RAW decoding via `rawpy` is slow, and this script's chroma-LUT grid search runs the matrix+chroma+curve pipeline hundreds of times per fold. To keep total runtime reasonable, every raw/target pair is decoded once, downsampled to a max dimension, and cached in memory for the rest of the run — the 3x3 matrix and the 2-parameter chroma LUT are both global (non-spatial) transforms, so this downsampling doesn't distort what's being fit, and it's disclosed as a limitation when recording results in Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluate_hncs_structural.py`:

```python
import unittest

import numpy as np

from tools.evaluate_hncs_structural import _pair_names, _resize_max_dim


class TestPairNames(unittest.TestCase):
    def test_returns_13_real_pairs(self):
        names = _pair_names()
        self.assertEqual(len(names), 13)

    def test_excludes_x2dii_chart_files(self):
        names = _pair_names()
        self.assertFalse(any("x2dii-chart" in n for n in names))

    def test_names_are_jpeg_basenames(self):
        names = _pair_names()
        self.assertTrue(all(n.endswith(".jpg") for n in names))


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(1000, 2000, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertLessEqual(max(out.shape[:2]), 512)
        # aspect ratio preserved (within 1px rounding)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 2000 / 1000, places=1)

    def test_preserves_channel_count(self):
        img = np.random.default_rng(2).uniform(0, 1, size=(600, 300, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertEqual(out.shape[2], 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_evaluate_hncs_structural -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.evaluate_hncs_structural'`

- [ ] **Step 3: Write the implementation**

Create `tools/evaluate_hncs_structural.py`:

```python
"""hybrid_engine/research/hncs_structural.py(HNCS 실제 4단계 구조를
미러링한 실험 모듈)이 apply_hncs()보다 실제로 ΔE가 개선되는지
leave-one-out 교차검증으로 확인한다. 설계 근거:
docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md

  python3 -m tools.evaluate_hncs_structural
"""
import csv
import glob
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from brands.hasselblad import apply_hncs
from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix, fit_color_matrix
from hybrid_engine.research.hncs_structural import (
    apply_chroma_lut, classify_illuminant_cluster, decode_and_white_balance,
)
from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import decode_raw, decode_raw_native, load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
HUE_SHIFT_GRID = [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]

FILM_CURVE_TOE_LIFT = 0.001
FILM_CURVE_SHOULDER_START = 0.78
FILM_CURVE_WHITE_POINT = 1.0

MATRIX_RIDGE = 1.0  # 클러스터당 3~10쌍뿐이라 3x3(자유도 9) 과적합 억제

# 그리드서치+ΔE 루프가 폴드당 수백 번 반복되므로 축소본으로 처리한다 -
# 3x3 매트릭스와 2-파라미터 chroma LUT는 둘 다 공간 정보가 아니라 색
# 분포에만 의존하는 전역 변환이라 축소가 피팅 품질에 실질적 영향이
# 없다(결과 기록에 한계로 명시).
DOWNSAMPLE_MAX_DIM = 512

_PAIR_DATA_CACHE = {}
_BASELINE_CACHE = {}


def _pair_names():
    """CSV의 jpeg_url basename 목록(13개, 확장자 .jpg 포함) - 실제
    사진 페어만 담고 있고 raw_calib_cache/의 x2dii-chart-* 2개(다른
    데이터셋)는 여기 없다."""
    names = []
    with open(CSV_PATH, newline="") as f:
        for row in csv.DictReader(f):
            names.append(os.path.basename(row["jpeg_url"]))
    return names


def _raw_path_for(jpeg_name):
    matches = [m for m in glob.glob(os.path.join(CACHE_DIR, jpeg_name + ".*"))
               if not m.endswith(".target.jpg")]
    if len(matches) != 1:
        raise FileNotFoundError(f"raw for {jpeg_name}: expected 1 match, got {matches}")
    return matches[0]


def _target_path_for(jpeg_name):
    return os.path.join(CACHE_DIR, jpeg_name + ".target.jpg")


def _resize_max_dim(img, max_dim):
    """긴 변이 max_dim을 넘으면 종횡비 유지한 채 축소. 이미 작으면
    그대로 반환(no-op)."""
    h, w = img.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale >= 1.0:
        return img
    new_w, new_h = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = cv2.resize(img.astype(np.float32), (new_w, new_h),
                          interpolation=cv2.INTER_AREA)
    return resized.astype(np.float64)


def load_pairs():
    """13쌍 전부를 dict 리스트로 반환: name/raw_path/target_path/cluster."""
    pairs = []
    for jpeg_name in _pair_names():
        raw_path = _raw_path_for(jpeg_name)
        as_shot_neutral = read_as_shot_neutral(raw_path)
        cluster = classify_illuminant_cluster(as_shot_neutral)
        pairs.append({
            "name": jpeg_name, "raw_path": raw_path,
            "target_path": _target_path_for(jpeg_name), "cluster": cluster,
        })
    return pairs


def _pair_data(pair):
    """(wb_rgb, target_linear) 축소본을 캐시 - RAW 디코드가 느리고
    그리드서치가 같은 페어를 폴드마다 반복 사용하므로 이름으로 캐시."""
    name = pair["name"]
    if name not in _PAIR_DATA_CACHE:
        wb_rgb = _resize_max_dim(decode_and_white_balance(pair["raw_path"]),
                                  DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=wb_rgb.shape[:2])
        _PAIR_DATA_CACHE[name] = (wb_rgb, target)
    return _PAIR_DATA_CACHE[name]


def _hncs_baseline_and_target(pair):
    """apply_hncs() 공정 비교용 - decode_raw()(WB+libraw sRGB 매트릭스,
    "일반 카메라 JPEG" 근사) 기반 축소본 캐시."""
    name = pair["name"]
    if name not in _BASELINE_CACHE:
        baseline = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=baseline.shape[:2])
        _BASELINE_CACHE[name] = (baseline, target)
    return _BASELINE_CACHE[name]


def fit_matrices(train_pairs):
    """클러스터별 3x3 매트릭스 피팅 (ridge=MATRIX_RIDGE)."""
    by_cluster = {}
    for cluster in ("cluster_a", "cluster_b"):
        cluster_pairs = [p for p in train_pairs if p["cluster"] == cluster]
        sources = [_pair_data(p)[0] for p in cluster_pairs]
        targets = [_pair_data(p)[1] for p in cluster_pairs]
        by_cluster[cluster] = fit_color_matrix(sources, targets, ridge=MATRIX_RIDGE)
    return by_cluster


def fit_chroma_lut_params(train_pairs, matrices):
    """클러스터별 (sat_mult, hue_shift_deg) 그리드서치 - 매트릭스 +
    chroma LUT + 공유 필름커브까지 다 적용한 뒤 타깃과의 평균
    ΔE(CIEDE2000)가 최소인 조합을 그 클러스터의 학습 페어 평균으로
    고른다."""
    by_cluster = {}
    for cluster, matrix in matrices.items():
        cluster_pairs = [p for p in train_pairs if p["cluster"] == cluster]
        best_params, best_de = (1.0, 0.0), float("inf")
        for sat_mult, hue_shift_deg in itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID):
            des = []
            for p in cluster_pairs:
                wb_rgb, target = _pair_data(p)
                matrixed = apply_color_matrix(wb_rgb, matrix)
                chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
                result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                                     shoulder_start=FILM_CURVE_SHOULDER_START,
                                     white_point=FILM_CURVE_WHITE_POINT)
                des.append(mean_delta_e(result, target))
            mean_de = float(np.mean(des))
            if mean_de < best_de:
                best_de, best_params = mean_de, (sat_mult, hue_shift_deg)
        by_cluster[cluster] = best_params
    return by_cluster


def structural_delta_e(test_pair, matrices, chroma_lut_params):
    wb_rgb, target = _pair_data(test_pair)
    cluster = test_pair["cluster"]
    matrixed = apply_color_matrix(wb_rgb, matrices[cluster])
    sat_mult, hue_shift_deg = chroma_lut_params[cluster]
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                         shoulder_start=FILM_CURVE_SHOULDER_START,
                         white_point=FILM_CURVE_WHITE_POINT)
    return mean_delta_e(result, target)


def _linear_to_uint8_bgr(rgb_linear):
    clipped = np.clip(rgb_linear, 0.0, 1.0)
    encoded = colour.cctf_encoding(clipped, function="sRGB")
    u8 = (np.clip(encoded, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return u8[:, :, ::-1]


def _uint8_bgr_to_linear(bgr_uint8):
    rgb = bgr_uint8[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")


def apply_hncs_delta_e(test_pair):
    """공정 비교: apply_hncs()도 같은 raw 기반 baseline(decode_raw())에
    적용해서 같은 13쌍 target에 대해 ΔE를 잰다 - 기존 v8~v12 이력의
    RMSE 23.3은 다른 표본/다른 측정 방식이라 그대로 갖다 쓰지 않고 이
    실험 안에서 재측정한다."""
    baseline, target = _hncs_baseline_and_target(test_pair)
    bgr_uint8 = _linear_to_uint8_bgr(baseline)
    result_bgr = apply_hncs(bgr_uint8)
    result_linear = _uint8_bgr_to_linear(result_bgr)
    return mean_delta_e(result_linear, target)


def run_loocv():
    pairs = load_pairs()
    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrices = fit_matrices(train)
        chroma_params = fit_chroma_lut_params(train, matrices)
        de_structural = structural_delta_e(held_out, matrices, chroma_params)
        de_hncs = apply_hncs_delta_e(held_out)
        per_fold.append((held_out["name"], held_out["cluster"], de_structural, de_hncs))
        print(f"  [{held_out['name']}] cluster={held_out['cluster']} "
              f"structural ΔE={de_structural:.3f} apply_hncs ΔE={de_hncs:.3f}",
              flush=True)
    return per_fold


def main():
    per_fold = run_loocv()
    structural_des = [row[2] for row in per_fold]
    hncs_des = [row[3] for row in per_fold]
    mean_structural = float(np.mean(structural_des))
    mean_hncs = float(np.mean(hncs_des))
    improvement_pct = (mean_hncs - mean_structural) / mean_hncs * 100
    print()
    print(f"평균 structural ΔE (CIEDE2000, n={len(structural_des)}): {mean_structural:.3f}")
    print(f"평균 apply_hncs ΔE (CIEDE2000, n={len(hncs_des)}): {mean_hncs:.3f}")
    verdict = "구조적 실험이 이겼다" if improvement_pct > 0 else "apply_hncs()가 더 낫다"
    print(f"개선폭: {improvement_pct:.1f}% ({verdict})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_evaluate_hncs_structural -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python3 -m unittest discover -s tests`
Expected: all existing tests still PASS, plus the 6 new ones

- [ ] **Step 6: Actually run the evaluation against the real 13-pair dataset**

Run: `python3 -m tools.evaluate_hncs_structural`

This will take several minutes (13 RAW decodes + grid search per fold). Capture the **full stdout output verbatim** — every per-fold line plus the final summary (mean structural ΔE, mean `apply_hncs` ΔE, improvement %, verdict). This output is required input for Task 4; do not paraphrase or round it — copy it exactly into your task report.

- [ ] **Step 7: Commit**

```bash
git add tools/evaluate_hncs_structural.py tests/test_evaluate_hncs_structural.py
git commit -m "Add tools/evaluate_hncs_structural.py: LOOCV vs apply_hncs()"
```

---

### Task 4: Record results in `EVALUATION.md` + finish the research document + README link

**Files:**
- Modify: `hybrid_engine/EVALUATION.md`
- Modify: `docs/hncs_structural_research.md`
- Modify: `docs/hncs_structural_research.en.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3's captured stdout output (per-fold ΔE lines + summary) from its task report.
- Produces: nothing consumed by later tasks — this is the final task in the plan.

- [ ] **Step 1: Append a new section to `hybrid_engine/EVALUATION.md`**

Using Task 3's actual captured output, append a section at the end of `hybrid_engine/EVALUATION.md` following this structure (this project's established "record honestly, win or lose" format — see the file's existing tail for the precedent this mirrors):

```markdown

## HNCS 구조 실험: 4단계 구조 미러링이 ΔE를 개선하는가

**배경**: `apply_hncs()`(Stable)는 실제 HNCS 파이프라인을 3단계로
단순화한 근사다. 실제 구조(조명별 매트릭스 -> 조명별 chroma LUT ->
공유 필름커브, `docs/hncs_structural_research.md` 참고)를 미러링한
연구용 실험 모듈(`hybrid_engine/research/hncs_structural.py`)이 실제로
ΔE를 개선하는지 leave-one-out 교차검증(13쌍, `tools/evaluate_hncs_structural.py`)으로
측정했다.

**결과** (같은 13쌍, CIEDE2000, held-out마다 재피팅):

| 방법 | 평균 ΔE (CIEDE2000) |
|---|---|
| `apply_hncs()` (raw 기반 baseline에 적용, 이 실험 안에서 재측정) | <Task 3 출력의 mean_hncs 값> |
| 구조 실험 (`apply_hncs_structural`, 클러스터별 매트릭스+chroma LUT+공유 필름커브) | <Task 3 출력의 mean_structural 값> |

개선폭: <Task 3 출력의 improvement_pct 값>% (<Task 3 출력의 verdict 문자열>)

**판정**: <"구조 실험이 이겼다"면 개선폭과 함께 명시, 졌다면 "졌다" +
개선폭(음수)을 그대로 정직하게 기록 - 이 프로젝트의 "이기든 지든
기록" 관례>

**알려진 한계**:
- **표본 13쌍, 클러스터당 3~10쌍(소수 클러스터 3쌍)** - 통계적으로
  매우 얇다. 특히 `cluster_b`(3쌍)는 leave-one-out 시 학습 데이터가
  2쌍뿐이라 매트릭스 피팅이 ridge 정규화(=1.0)에 크게 의존한다.
- **DOWNSAMPLE_MAX_DIM=512로 축소한 이미지에서 피팅/측정** - 3x3
  매트릭스와 2-파라미터 chroma LUT 둘 다 공간 정보가 아니라 색 분포에만
  의존하는 전역 변환이라 실질적 영향은 작다고 보지만, 원본 해상도에서
  재측정하면 수치가 달라질 수 있다.
- **chroma LUT 그리드가 성기다**(`sat_mult` 7개 x `hue_shift_deg` 7개) -
  더 촘촘한 그리드나 연속 최적화가 이 결과를 바꿀 수 있다.
- **`apply_hncs()`를 대체하지 않는다** - 이 실험이 이겨도 Stable로
  승격하지 않는다(별도 논의).

**기존 v8~v12 RMSE 23.3과의 관계**: 그 수치는 다른 표본/다른 측정
방식(RMSE, 이 실험은 ΔE)이라 그대로 비교하지 않고, 이 실험 안에서
`apply_hncs()`의 ΔE를 같은 13쌍 raw 기반으로 재측정했다(위 표의
`apply_hncs()` 행).
```

Fill in every `<...>` placeholder with the literal numbers/strings from Task 3's captured output before committing — none of these bracketed markers should remain in the committed file.

- [ ] **Step 2: Fill in the results section of both research documents**

In both `docs/hncs_structural_research.md` and `docs/hncs_structural_research.en.md`, replace the `<!-- 결과는 tools/evaluate_hncs_structural.py 실행 후 채워짐 -->` / `<!-- Results filled in after running tools/evaluate_hncs_structural.py -->` comment with a short results paragraph plus the same results table used in `EVALUATION.md` Step 1 (Korean numbers/wording in the `.md`, English in the `.en.md`), and a one-line pointer: `자세한 방법론과 한계는 hybrid_engine/EVALUATION.md의 "HNCS 구조 실험" 절 참고.` (Korean file) / `See the "HNCS Structural Experiment" section of hybrid_engine/EVALUATION.md for full methodology and limitations.` (English file).

- [ ] **Step 3: Add a README "Further Reading" link**

In `README.md`, in the "## Further Reading" section (around the existing `docs/brands.en.md`/`docs/project_structure.en.md` bullet list), add one bullet:

```markdown
- [docs/hncs_structural_research.en.md](docs/hncs_structural_research.en.md) -
  research-only comparison of HNCS's real 4-stage pipeline vs.
  `apply_hncs()`'s 3-stage simplification, with a leave-one-out ΔE
  experiment
```

- [ ] **Step 4: Run the full test suite one more time**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (no code changed in this task, but this confirms the branch is still green before the final commit)

- [ ] **Step 5: Commit**

```bash
git add hybrid_engine/EVALUATION.md docs/hncs_structural_research.md docs/hncs_structural_research.en.md README.md
git commit -m "Record HNCS structural experiment results in EVALUATION.md and docs"
```
