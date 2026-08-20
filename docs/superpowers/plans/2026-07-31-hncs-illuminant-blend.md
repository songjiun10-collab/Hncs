# HNCS Illuminant Blend Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, with full LOO cross-validation and significance testing, whether continuous illuminant-weight blending of the two anchor color matrices/chroma LUTs (as real HNCS reportedly does — dual-illuminant-style interpolation per external forum analysis) beats the existing hard 2-cluster structural model on the same 13 real Hasselblad pairs, using two different blend-weight formulas (R/B ratio, CCT/mired).

**Architecture:** Add three new functions to `hybrid_engine/research/hncs_structural.py` (continuous blend-weight computation in two variants, plus a blended-pipeline apply function) alongside the existing hard-cluster functions, which stay untouched. A new standalone research script (`tools/evaluate_hncs_blend.py`) reuses `fit_color_matrix()`'s existing per-pixel weight support to do weighted least-squares fitting where all 13 pairs contribute to both anchor matrices, runs LOO CV for both weight formulas, and compares each against the already-recorded hard-cluster per-fold ΔE values (no need to re-run the hard-cluster experiment).

**Tech Stack:** Python 3, `colour-science` (CCT computation, already a dependency), `numpy`, `opencv-python` (`cv2`, via existing `apply_chroma_lut`), `unittest`.

## Global Constraints

- `brands/hasselblad.py`'s `apply_hncs()` must NEVER be modified.
- `hybrid_engine/assets/profiles/hasselblad.json` and any `.dcp` calibration artifact must NEVER be touched.
- The existing hard-cluster functions in `hybrid_engine/research/hncs_structural.py` (`CLUSTER_THRESHOLD_R_OVER_B`, `classify_illuminant_cluster`, `apply_hncs_structural`) must NOT be modified or removed — only new functions are added alongside them.
- Blend weight convention: `weight=0.0` means fully anchor A, `weight=1.0` means fully anchor B. Blending is linear: `(1.0 - weight) * value_a + weight * value_b`, applied identically to the 3x3 matrix and to both chroma LUT scalars (`sat_mult`, `hue_shift_deg`).
- R/B-blend normalization range and CCT/mired-blend normalization range are each computed **once from the full 13-pair population**, not per LOO fold — a per-fold-shifting normalization range would make fold-to-fold comparison meaningless.
- Grid for the weighted chroma LUT search: `SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]`, `HUE_SHIFT_GRID = [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]` (identical values to `tools/evaluate_hncs_structural.py`, already validated on this data).
- `MATRIX_RIDGE = 1.0` for `fit_color_matrix()` calls (matches `tools/evaluate_hncs_structural.py`'s value, documented there as effectively a no-op at this pixel-count scale but kept for reproducibility).
- Shared film curve constants stay fixed and un-fitted, matching the hard-cluster experiment: `FILM_CURVE_TOE_LIFT = 0.001`, `FILM_CURVE_SHOULDER_START = 0.78`, `FILM_CURVE_WHITE_POINT = 1.0`.
- ΔE measurement: `hybrid_engine.utils.evaluate.mean_delta_e` (CIEDE2000) exclusively.
- Never declare a winner from a raw mean-difference alone. Report the full `summarize()` output (paired t-test, sign test via `math.comb`, bootstrap 95% CI, drop-one sensitivity) and treat a 95% CI that straddles zero as "판정 보류" (inconclusive).
- Dataset: the same 13 Hasselblad pairs used by `tools/evaluate_hncs_structural.py` (`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` + `raw_calib_cache/`, both already present on this container's local disk, `raw_calib_cache/` is git-ignored).
- Decode is not the bottleneck for this experiment (unlike the chromatic-aberration experiment): `decode_and_white_balance()` runs once per pair and the result is cached; all grid-search and LOO-fold work operates on the cached, downsampled (`DOWNSAMPLE_MAX_DIM = 512`) arrays.
- The hard-cluster comparison baseline is a **hardcoded constant** (`HARD_CLUSTER_DE`, 13 name→ΔE entries) copied verbatim from `hybrid_engine/EVALUATION.md`'s "HNCS 구조 실험" section's "폴드별 상세" table — the hard-cluster experiment is NOT re-run.
- Record the result in `hybrid_engine/EVALUATION.md` honestly whether it wins, loses, or is inconclusive, for both weight formulas, plus a direct RB-vs-CCT comparison.

---

### Task 1: `hncs_structural.py` blend-weight and blended-pipeline functions

**Files:**
- Modify: `hybrid_engine/research/hncs_structural.py` (add `import colour`, a module constant, and 3 new functions at the end of the file, after line 106 — the existing `apply_hncs_structural` function)
- Test: `tests/test_hncs_structural.py` (existing file — add 3 new test classes, do not remove or modify the existing 4 test classes)

**Interfaces:**
- Consumes: `apply_color_matrix` (already imported in this module from `hybrid_engine.core.raw_baseline`), `apply_chroma_lut`/`film_curve`/`decode_and_white_balance` (already defined in this module), `colour.RGB_COLOURSPACES`, `colour.RGB_to_XYZ`, `colour.XYZ_to_xy`, `colour.temperature.xy_to_CCT`.
- Produces: `compute_blend_weight_rb(as_shot_neutral, rb_min, rb_max) -> float`, `compute_blend_weight_cct(as_shot_neutral, mired_min, mired_max) -> float`, `apply_hncs_structural_blend(raw_path, weight, matrix_a, matrix_b, chroma_lut_a, chroma_lut_b, toe_lift, shoulder_start, white_point) -> np.ndarray`. Task 2 imports and calls all three.

- [ ] **Step 1: Write the failing tests**

Add these three classes to the end of `tests/test_hncs_structural.py` (the existing 4 classes and their imports at the top stay untouched; add the new names to the existing `from hybrid_engine.research.hncs_structural import (...)` block):

```python
from hybrid_engine.research.hncs_structural import (
    CLUSTER_THRESHOLD_R_OVER_B,
    apply_chroma_lut,
    apply_hncs_structural,
    apply_hncs_structural_blend,
    classify_illuminant_cluster,
    compute_blend_weight_cct,
    compute_blend_weight_rb,
    decode_and_white_balance,
)
```

```python
class TestComputeBlendWeightRb(unittest.TestCase):
    def test_at_min_is_zero(self):
        # R/B = 0.4/1.0 = 0.4
        self.assertAlmostEqual(
            compute_blend_weight_rb(np.array([0.4, 1.0, 1.0]), rb_min=0.4, rb_max=1.2), 0.0)

    def test_at_max_is_one(self):
        # R/B = 1.2/1.0 = 1.2
        self.assertAlmostEqual(
            compute_blend_weight_rb(np.array([1.2, 1.0, 1.0]), rb_min=0.4, rb_max=1.2), 1.0)

    def test_midpoint_is_half(self):
        # R/B = 0.8/1.0 = 0.8, midpoint of [0.4, 1.2]
        self.assertAlmostEqual(
            compute_blend_weight_rb(np.array([0.8, 1.0, 1.0]), rb_min=0.4, rb_max=1.2), 0.5)

    def test_extrapolates_outside_observed_range(self):
        # R/B = 1.6/1.0 = 1.6, above rb_max=1.2 -> weight > 1 (allowed extrapolation)
        w = compute_blend_weight_rb(np.array([1.6, 1.0, 1.0]), rb_min=0.4, rb_max=1.2)
        self.assertGreater(w, 1.0)


class TestComputeBlendWeightCct(unittest.TestCase):
    def test_lower_r_over_b_gives_lower_weight_than_higher_r_over_b(self):
        # 실측값(로컬 raw_calib_cache/에서 확인, 이 스펙 문서 참고):
        # B0001395.jpg: R/B=0.365(낮음) -> CCT~9377K -> mired~106.65(낮음)
        low_rb = np.array([0.3389641154, 1.0, 0.9288508419])
        # x1d-II-sample-09.jpg: R/B=1.316(높음) -> CCT~5807K -> mired~172.19(높음)
        high_rb = np.array([0.570155902, 1.0, 0.4331641286])
        w_low = compute_blend_weight_cct(low_rb, mired_min=106.65, mired_max=172.19)
        w_high = compute_blend_weight_cct(high_rb, mired_min=106.65, mired_max=172.19)
        self.assertAlmostEqual(w_low, 0.0, delta=0.02)
        self.assertAlmostEqual(w_high, 1.0, delta=0.02)
        self.assertLess(w_low, w_high)


class TestApplyHncsStructuralBlend(unittest.TestCase):
    @patch("hybrid_engine.research.hncs_structural.decode_and_white_balance")
    def test_weight_zero_matches_anchor_a_only(self, mock_decode):
        rng = np.random.default_rng(4)
        wb_rgb = rng.uniform(0.02, 0.3, size=(4, 4, 3))
        mock_decode.return_value = wb_rgb

        matrix_a = np.eye(3) * 1.1
        matrix_b = np.eye(3) * 0.7
        chroma_a = (1.05, 2.0)
        chroma_b = (0.9, -3.0)

        result = apply_hncs_structural_blend(
            "fake.3FR", weight=0.0, matrix_a=matrix_a, matrix_b=matrix_b,
            chroma_lut_a=chroma_a, chroma_lut_b=chroma_b,
            toe_lift=0.001, shoulder_start=0.78, white_point=1.0)

        from core.curve import film_curve
        from hybrid_engine.core.raw_baseline import apply_color_matrix
        matrixed = apply_color_matrix(wb_rgb, matrix_a)
        chroma_applied = apply_chroma_lut(matrixed, chroma_a[0], chroma_a[1])
        expected = film_curve(chroma_applied, toe_lift=0.001,
                               shoulder_start=0.78, white_point=1.0)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    @patch("hybrid_engine.research.hncs_structural.decode_and_white_balance")
    def test_weight_one_matches_anchor_b_only(self, mock_decode):
        rng = np.random.default_rng(5)
        wb_rgb = rng.uniform(0.02, 0.3, size=(4, 4, 3))
        mock_decode.return_value = wb_rgb

        matrix_a = np.eye(3) * 1.1
        matrix_b = np.eye(3) * 0.7
        chroma_a = (1.05, 2.0)
        chroma_b = (0.9, -3.0)

        result = apply_hncs_structural_blend(
            "fake.3FR", weight=1.0, matrix_a=matrix_a, matrix_b=matrix_b,
            chroma_lut_a=chroma_a, chroma_lut_b=chroma_b,
            toe_lift=0.001, shoulder_start=0.78, white_point=1.0)

        from core.curve import film_curve
        from hybrid_engine.core.raw_baseline import apply_color_matrix
        matrixed = apply_color_matrix(wb_rgb, matrix_b)
        chroma_applied = apply_chroma_lut(matrixed, chroma_b[0], chroma_b[1])
        expected = film_curve(chroma_applied, toe_lift=0.001,
                               shoulder_start=0.78, white_point=1.0)
        np.testing.assert_allclose(result, expected, atol=1e-6)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_hncs_structural -v`
Expected: the 6 new tests FAIL with `ImportError: cannot import name 'compute_blend_weight_rb'` (or similar); the 8 pre-existing tests still PASS once the import line is fixed to not error — note the whole file will fail to import until Step 3 adds the new names, so at this stage the entire run shows import failure, which is the expected "fails for the right reason" state for this step.

- [ ] **Step 3: Add the new functions**

Add `import colour` near the top of `hybrid_engine/research/hncs_structural.py` (after the existing `import numpy as np` line), and a module-level constant right after the existing `CLUSTER_THRESHOLD_R_OVER_B = 0.9` line:

```python
_SRGB = colour.RGB_COLOURSPACES["sRGB"]
```

Then append these three functions to the end of the file (after the existing `apply_hncs_structural` function, i.e. after line 106):

```python
def compute_blend_weight_rb(as_shot_neutral, rb_min, rb_max):
    """AsShotNeutral의 R/B 비율을 [rb_min, rb_max] 범위 기준으로
    [0, 1]로 정규화한 블렌딩 가중치. 0에 가까울수록 앵커A(저 R/B),
    1에 가까울수록 앵커B. rb_min/rb_max는 13쌍 전체에서 관측된 실제
    최솟값/최댓값을 호출부(평가 스크립트)가 넘긴다 - 하드코딩하지
    않는다. 관측 범위 밖 값이 오면 [0,1] 밖으로 나갈 수 있고, 이는
    의도된 외삽 허용이다."""
    r_over_b = as_shot_neutral[0] / as_shot_neutral[2]
    return (r_over_b - rb_min) / (rb_max - rb_min)


def compute_blend_weight_cct(as_shot_neutral, mired_min, mired_max):
    """AsShotNeutral을 대략적 CCT로 변환(camera-native RGB를 sRGB
    선형 RGB로 근사하는 가정 1개 추가 - 실제 카메라 분광감도를 모르니
    엄밀하지 않다, 이 실험 안에서만 쓰는 근사) 후 mired(=1e6/CCT) 공간
    에서 [mired_min, mired_max] 기준 [0, 1]로 정규화. mired 공간에서
    보간하는 건 Adobe DCP의 실제 dual-illuminant 보간 관례와 동일."""
    rgb = np.array(as_shot_neutral[:3], dtype=np.float64)
    xyz = colour.RGB_to_XYZ(rgb, _SRGB, apply_cctf_decoding=False)
    xy = colour.XYZ_to_xy(xyz)
    cct = colour.temperature.xy_to_CCT(xy, method="McCamy 1992")
    mired = 1e6 / cct
    return (mired - mired_min) / (mired_max - mired_min)


def apply_hncs_structural_blend(raw_path, weight, matrix_a, matrix_b,
                                 chroma_lut_a, chroma_lut_b,
                                 toe_lift, shoulder_start, white_point):
    """블렌딩 버전 4단계 파이프라인: WB적용 네이티브 RGB -> 가중
    평균 매트릭스((1-weight)*matrix_a + weight*matrix_b) -> 가중 평균
    chroma LUT 파라미터 -> 공유 필름커브(하드클러스터 버전과 동일하게
    조명 무관 고정). weight는 이미 계산된 스칼라를 받는다
    (compute_blend_weight_*는 평가 스크립트에서 호출) - 이 함수는
    블렌딩 로직만 담당한다."""
    wb_rgb = decode_and_white_balance(raw_path)
    blended_matrix = (1.0 - weight) * matrix_a + weight * matrix_b
    matrixed = apply_color_matrix(wb_rgb, blended_matrix)
    sat_a, hue_a = chroma_lut_a
    sat_b, hue_b = chroma_lut_b
    sat_mult = (1.0 - weight) * sat_a + weight * sat_b
    hue_shift_deg = (1.0 - weight) * hue_a + weight * hue_b
    chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
    return film_curve(chroma_applied, toe_lift=toe_lift,
                       shoulder_start=shoulder_start, white_point=white_point)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_hncs_structural -v`
Expected: all 14 tests PASS (8 pre-existing + 6 new).

- [ ] **Step 5: Run the full test suite to confirm no regression**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (507 pre-existing + 6 new = 513).

- [ ] **Step 6: Commit**

```bash
git add hybrid_engine/research/hncs_structural.py tests/test_hncs_structural.py
git commit -m "Add continuous illuminant-blend functions to hncs_structural.py"
```

---

### Task 2: `tools/evaluate_hncs_blend.py` — weighted LOO CV + real run + documentation

**Files:**
- Create: `tools/evaluate_hncs_blend.py`
- Test: `tests/test_evaluate_hncs_blend.py`
- Modify: `hybrid_engine/EVALUATION.md` (append new section at the end)

**Interfaces:**
- Consumes: `compute_blend_weight_rb`, `compute_blend_weight_cct` from Task 1's `hybrid_engine.research.hncs_structural`; `apply_color_matrix`, `fit_color_matrix` from `hybrid_engine.core.raw_baseline`; `apply_chroma_lut`, `decode_and_white_balance` from `hybrid_engine.research.hncs_structural`; `read_as_shot_neutral` from `hybrid_engine.utils.exif`; `film_curve` from `core.curve`; `mean_delta_e`, `load_image_linear_for_evaluate` style helpers from `hybrid_engine.utils.evaluate`/`hybrid_engine.utils.io`.
- Produces: `load_pairs()`, `compute_population_bounds(pairs)`, `fit_weighted_matrices(train_pairs, weight_fn, bounds)`, `fit_weighted_chroma_lut(train_pairs, weight_fn, bounds, matrix_a, matrix_b)`, `run_loocv(weight_fn_name)`, `summarize(per_fold)`, `_sign_test_p(wins, losses)`, `print_summary(s, label_a, label_b)`, `_resize_max_dim(img, max_dim)` — all importable by the test file.

- [ ] **Step 1: Write the failing portable unit tests**

Create `tests/test_evaluate_hncs_blend.py`:

```python
import csv
import os
import tempfile
import unittest

import numpy as np

from tools.evaluate_hncs_blend import (
    HARD_CLUSTER_DE, _resize_max_dim, _sign_test_p, load_pairs, summarize,
)


class TestLoadPairs(unittest.TestCase):
    def _write_manifest_and_cache(self, jpeg_names):
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        cache_dir = tempfile.mkdtemp()
        fields = ["camera", "lens", "photographer", "jpeg_url", "raw_url",
                  "page_url", "exif_datetime_original", "exif_camera_model",
                  "exif_lens", "exif_iso", "exif_focal_length",
                  "exif_pair_verified"]
        with os.fdopen(csv_fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for name in jpeg_names:
                row = {field: "" for field in fields}
                row["jpeg_url"] = f"https://cdn.example.com/{name}"
                writer.writerow(row)
        for name in jpeg_names:
            open(os.path.join(cache_dir, f"{name}.3FR"), "w").close()
            open(os.path.join(cache_dir, f"{name}.target.jpg"), "w").close()
        self.addCleanup(os.remove, csv_path)
        return csv_path, cache_dir

    def test_parses_names_and_paths(self):
        csv_path, cache_dir = self._write_manifest_and_cache(["x1d-xcd45-01.jpg"])
        pairs = load_pairs(csv_path=csv_path, cache_dir=cache_dir)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["name"], "x1d-xcd45-01.jpg")
        self.assertTrue(pairs[0]["raw_path"].endswith("x1d-xcd45-01.jpg.3FR"))
        self.assertTrue(pairs[0]["target_path"].endswith("x1d-xcd45-01.jpg.target.jpg"))

    def test_multiple_rows_preserve_order(self):
        csv_path, cache_dir = self._write_manifest_and_cache(["a.jpg", "b.jpg"])
        pairs = load_pairs(csv_path=csv_path, cache_dir=cache_dir)
        self.assertEqual([p["name"] for p in pairs], ["a.jpg", "b.jpg"])


class TestResizeMaxDim(unittest.TestCase):
    def test_noop_when_already_smaller_than_max_dim(self):
        img = np.random.default_rng(0).uniform(0, 1, size=(10, 20, 3))
        out = _resize_max_dim(img, max_dim=1024)
        self.assertEqual(out.shape, img.shape)

    def test_downsamples_when_larger_than_max_dim(self):
        img = np.random.default_rng(1).uniform(0, 1, size=(2000, 4000, 3))
        out = _resize_max_dim(img, max_dim=512)
        self.assertLessEqual(max(out.shape[:2]), 512)
        self.assertAlmostEqual(out.shape[1] / out.shape[0], 4000 / 2000, places=1)


class TestSignTestP(unittest.TestCase):
    def test_even_split_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(6, 6), 1.0)

    def test_no_pairs_is_p_one(self):
        self.assertAlmostEqual(_sign_test_p(0, 0), 1.0)

    def test_all_wins_is_significant(self):
        self.assertLess(_sign_test_p(13, 0), 0.001)


class TestHardClusterDeConstant(unittest.TestCase):
    def test_has_all_13_pairs(self):
        self.assertEqual(len(HARD_CLUSTER_DE), 13)

    def test_matches_documented_value_for_one_pair(self):
        # hybrid_engine/EVALUATION.md "HNCS 구조 실험" 절, 폴드별 상세 표
        self.assertAlmostEqual(HARD_CLUSTER_DE["x1d-II-sample-09.jpg"], 5.249)


class TestSummarizeShape(unittest.TestCase):
    """summarize()가 반환하는 dict의 키/타입만 검증 - 실제 13쌍 실행
    결과에 대한 회귀 테스트는 실행 후 Step 8에서 별도로 추가한다."""

    def test_returns_expected_keys(self):
        per_fold = [
            ("p1", 10.0, 8.0),
            ("p2", 12.0, 12.5),
            ("p3", 9.0, 7.5),
        ]
        s = summarize(per_fold)
        for key in ("n", "mean_a", "mean_b", "mean_diff", "median_diff",
                    "improvement_pct", "b_wins", "a_wins", "sd_diff",
                    "sem_diff", "t_stat", "sign_test_p", "ci_diff", "ci_pct",
                    "dropone_pct_min", "dropone_pct_max",
                    "dropone_flips_sign", "inconclusive", "verdict"):
            self.assertIn(key, s)
        self.assertEqual(s["n"], 3)
        self.assertEqual(s["b_wins"], 2)
        self.assertEqual(s["a_wins"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_evaluate_hncs_blend -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.evaluate_hncs_blend'`.

- [ ] **Step 3: Implement `tools/evaluate_hncs_blend.py`**

```python
"""HNCS 조명 블렌딩(illuminant blend) 실험 - hncs_structural.py의
하드-클러스터 구조 실험(cluster_a/cluster_b 하드 분류)을, 연속
블렌딩(Lightroom dual-illuminant DCP 방식과 유사, Luminous Landscape
포럼의 HNCS 메커니즘 분석이 시사하는 실제 구조)으로 바꾸면 ΔE가
낮아지는지 leave-one-out 교차검증으로 확인한다. 설계 근거:
docs/superpowers/specs/2026-07-31-hncs-illuminant-blend-design.md

  python3 -m tools.evaluate_hncs_blend

두 가지 블렌딩 가중치 공식(R/B 비율 선형, CCT/mired)을 각각 독립적으로
평가하고, 마지막에 둘을 직접 비교한다. 하드-클러스터 쪽은 재실행하지
않는다 - hybrid_engine/EVALUATION.md의 "HNCS 구조 실험" 절에 이미
기록된 13개 폴드 값을 HARD_CLUSTER_DE 상수로 그대로 가져와 쓴다.

매트릭스/chroma LUT 둘 다 **가중 최소자승**으로 피팅한다: 13쌍 전부가
두 앵커(A/B) 피팅에 다 기여하되, 각 페어의 블렌딩 가중치가 그대로
그 페어의 기여도가 된다 - 기존 하드-클러스터 버전에서 소수 클러스터
(cluster_b, 3쌍뿐)의 매트릭스가 사실상 2쌍(LOO 기준)으로만 피팅되던
문제를 근본적으로 해결한다.
"""
import csv
import glob
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import colour
import cv2
import numpy as np

from core.curve import film_curve
from hybrid_engine.core.raw_baseline import apply_color_matrix, fit_color_matrix
from hybrid_engine.research.hncs_structural import (
    apply_chroma_lut, compute_blend_weight_cct, compute_blend_weight_rb,
    decode_and_white_balance,
)
from hybrid_engine.utils.evaluate import mean_delta_e
from hybrid_engine.utils.exif import read_as_shot_neutral
from hybrid_engine.utils.io import load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

_SRGB = colour.RGB_COLOURSPACES["sRGB"]

SAT_MULT_GRID = [0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15]
HUE_SHIFT_GRID = [-6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0]
MATRIX_RIDGE = 1.0

FILM_CURVE_TOE_LIFT = 0.001
FILM_CURVE_SHOULDER_START = 0.78
FILM_CURVE_WHITE_POINT = 1.0

DOWNSAMPLE_MAX_DIM = 512

# hybrid_engine/EVALUATION.md "HNCS 구조 실험" 절, "폴드별 상세" 표에서
# 그대로 옮겨적은 하드-클러스터 구조 실험의 실측 ΔE(재실행 안 함).
HARD_CLUSTER_DE = {
    "x1d-II-sample-02.jpg": 10.787,
    "x1d-II-sample-09.jpg": 5.249,
    "B0000994.jpg": 14.223,
    "B0001395.jpg": 18.412,
    "x1d-xcd45-01.jpg": 13.194,
    "x1d-xcd45-03.jpg": 8.342,
    "x1d-xcd45-04.jpg": 4.729,
    "x1d-ii-xcd45p-01.jpg": 10.126,
    "x1d-ii-xcd45p-02.jpg": 11.055,
    "x1d-II-sample-01.jpg": 6.452,
    "x1d-II-sample-06.jpg": 11.726,
    "02709.jpg": 13.074,
    "00378.jpg": 5.115,
}

_PAIR_DATA_CACHE = {}


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


def load_pairs(csv_path=CSV_PATH, cache_dir=CACHE_DIR):
    """CSV의 jpeg_url basename 13개를 읽어 raw/target 경로와 함께
    dict 리스트로 반환."""
    pairs = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            name = os.path.basename(row["jpeg_url"])
            matches = [m for m in glob.glob(os.path.join(cache_dir, name + ".*"))
                       if not m.endswith(".target.jpg")]
            if len(matches) != 1:
                raise FileNotFoundError(f"raw for {name}: expected 1 match, got {matches}")
            pairs.append({
                "name": name,
                "raw_path": matches[0],
                "target_path": os.path.join(cache_dir, name + ".target.jpg"),
            })
    return pairs


def _pair_data(pair):
    """(디코드+WB+축소본, 축소된 타깃) - 페어명으로 캐시. 두 가중치
    방식(rb/cct) 모두 같은 캐시를 공유한다(디코드는 가중치 공식과
    무관)."""
    name = pair["name"]
    if name not in _PAIR_DATA_CACHE:
        wb_rgb = _resize_max_dim(decode_and_white_balance(pair["raw_path"]),
                                  DOWNSAMPLE_MAX_DIM)
        target = load_image_linear(pair["target_path"], resize_to=wb_rgb.shape[:2])
        _PAIR_DATA_CACHE[name] = (wb_rgb, target)
    return _PAIR_DATA_CACHE[name]


def _cct_mired(as_shot_neutral):
    rgb = np.array(as_shot_neutral[:3], dtype=np.float64)
    xyz = colour.RGB_to_XYZ(rgb, _SRGB, apply_cctf_decoding=False)
    xy = colour.XYZ_to_xy(xyz)
    cct = colour.temperature.xy_to_CCT(xy, method="McCamy 1992")
    return 1e6 / cct


def compute_population_bounds(pairs):
    """13쌍 전체에서 R/B 비율과 CCT(mired) 최솟값/최댓값을 한 번만
    계산 - LOO 폴드마다 다시 계산하지 않는다(정규화 범위가 폴드별로
    흔들리면 폴드 간 비교가 무의미해짐)."""
    r_over_bs, mireds = [], []
    for p in pairs:
        asn = read_as_shot_neutral(p["raw_path"])
        r_over_bs.append(asn[0] / asn[2])
        mireds.append(_cct_mired(asn))
    return {
        "rb_min": min(r_over_bs), "rb_max": max(r_over_bs),
        "mired_min": min(mireds), "mired_max": max(mireds),
    }


def pair_weight_rb(pair, bounds):
    asn = read_as_shot_neutral(pair["raw_path"])
    return compute_blend_weight_rb(asn, bounds["rb_min"], bounds["rb_max"])


def pair_weight_cct(pair, bounds):
    asn = read_as_shot_neutral(pair["raw_path"])
    return compute_blend_weight_cct(asn, bounds["mired_min"], bounds["mired_max"])


def fit_weighted_matrices(train_pairs, weight_fn, bounds):
    """train_pairs 전부가 매트릭스 A/B 피팅 둘 다에 기여(가중 최소자승)
    - 각 페어의 블렌딩 가중치가 그대로 그 페어의 피팅 기여도가 된다."""
    weights_b = [weight_fn(p, bounds) for p in train_pairs]
    sources = [_pair_data(p)[0] for p in train_pairs]
    targets = [_pair_data(p)[1] for p in train_pairs]
    w_a = [np.full(s.shape[:2], 1.0 - w) for s, w in zip(sources, weights_b)]
    w_b = [np.full(s.shape[:2], w) for s, w in zip(sources, weights_b)]
    matrix_a = fit_color_matrix(sources, targets, weights=w_a, ridge=MATRIX_RIDGE)
    matrix_b = fit_color_matrix(sources, targets, weights=w_b, ridge=MATRIX_RIDGE)
    return matrix_a, matrix_b


def fit_weighted_chroma_lut(train_pairs, weight_fn, bounds, matrix_a, matrix_b):
    """앵커A/B용 (sat_mult, hue_shift_deg)를 각각 가중 평균 ΔE 최소화로
    그리드서치. 매트릭스는 이미 그 폴드에서 피팅된 blended matrix(각
    페어 자기 가중치로 블렌딩)를 먼저 적용한 뒤 후보 chroma 파라미터를
    얹어 평가한다 - apply_hncs_structural_blend()가 예측 시 실제로
    하는 순서와 일치시키기 위함."""
    entries = []
    for p in train_pairs:
        w = weight_fn(p, bounds)
        wb_rgb, target = _pair_data(p)
        blended_matrix = (1.0 - w) * matrix_a + w * matrix_b
        matrixed = apply_color_matrix(wb_rgb, blended_matrix)
        entries.append((w, matrixed, target))

    best_a, best_a_score = (1.0, 0.0), float("inf")
    best_b, best_b_score = (1.0, 0.0), float("inf")
    for sat_mult, hue_shift_deg in itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID):
        sum_a, total_a, sum_b, total_b = 0.0, 0.0, 0.0, 0.0
        for w, matrixed, target in entries:
            chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
            result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                                 shoulder_start=FILM_CURVE_SHOULDER_START,
                                 white_point=FILM_CURVE_WHITE_POINT)
            de = mean_delta_e(result, target)
            sum_a += (1.0 - w) * de
            total_a += (1.0 - w)
            sum_b += w * de
            total_b += w
        if total_a > 0:
            score_a = sum_a / total_a
            if score_a < best_a_score:
                best_a_score, best_a = score_a, (sat_mult, hue_shift_deg)
        if total_b > 0:
            score_b = sum_b / total_b
            if score_b < best_b_score:
                best_b_score, best_b = score_b, (sat_mult, hue_shift_deg)
    return best_a, best_b


def run_loocv(weight_fn_name):
    """weight_fn_name: "rb" 또는 "cct". 13개 폴드 전부에 대해
    (name, de_hard, de_blend, weight) 튜플 리스트를 반환한다."""
    pairs = load_pairs()
    bounds = compute_population_bounds(pairs)
    weight_fn = pair_weight_rb if weight_fn_name == "rb" else pair_weight_cct

    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrix_a, matrix_b = fit_weighted_matrices(train, weight_fn, bounds)
        chroma_a, chroma_b = fit_weighted_chroma_lut(train, weight_fn, bounds,
                                                       matrix_a, matrix_b)

        w_held = weight_fn(held_out, bounds)
        wb_rgb, target = _pair_data(held_out)
        blended_matrix = (1.0 - w_held) * matrix_a + w_held * matrix_b
        matrixed = apply_color_matrix(wb_rgb, blended_matrix)
        sat_a, hue_a = chroma_a
        sat_b, hue_b = chroma_b
        sat_mult = (1.0 - w_held) * sat_a + w_held * sat_b
        hue_shift_deg = (1.0 - w_held) * hue_a + w_held * hue_b
        chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
        result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                             shoulder_start=FILM_CURVE_SHOULDER_START,
                             white_point=FILM_CURVE_WHITE_POINT)
        de_blend = mean_delta_e(result, target)
        de_hard = HARD_CLUSTER_DE[held_out["name"]]

        per_fold.append((held_out["name"], de_hard, de_blend, w_held))
        print(f"  [{held_out['name']}] hard-cluster ΔE={de_hard:.3f} "
              f"blend({weight_fn_name}) ΔE={de_blend:.3f} "
              f"weight={w_held:.3f}", flush=True)
    return per_fold


def _sign_test_p(wins, losses):
    """부호검정 양측 p값(정확 이항, 무승부 제외). scipy 의존 없이
    math.comb으로 직접 계산한다."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return min(1.0, 2.0 * tail)


def summarize(per_fold, n_bootstrap=20000, seed=0):
    """페어드 비교 통계. per_fold의 각 행은 (name, value_a, value_b, ...)
    형태(추가 필드는 무시) - value_a가 기준, value_b가 비교 대상이다.
    개선폭/verdict는 value_b가 value_a보다 작을 때(=b가 더 좋음, ΔE
    낮을수록 좋음) 양수가 되도록 정의한다. 평균 차이 하나로 승패를
    선언하지 않는다 - 부호검정, 부트스트랩 신뢰구간, drop-one 민감도를
    같이 내고 0을 포함하면 '판정 보류'로 보고한다."""
    a = np.array([row[1] for row in per_fold], dtype=np.float64)
    b = np.array([row[2] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = a - b  # 양수 = b가 그 폴드에서 더 좋음(ΔE 감소)
    mean_a = float(a.mean())
    mean_b = float(b.mean())
    improvement_pct = (mean_a - mean_b) / mean_a * 100.0

    wins = int((diff > 0).sum())
    losses = int((diff < 0).sum())
    sd_diff = float(diff.std(ddof=1)) if n > 1 else 0.0
    sem_diff = sd_diff / math.sqrt(n) if n > 1 else 0.0
    t_stat = float(diff.mean() / sem_diff) if sem_diff > 0 else 0.0

    rng = np.random.default_rng(seed)
    boot_diff, boot_pct = [], []
    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, n)
        boot_diff.append(float(diff[idx].mean()))
        boot_pct.append(float((a[idx].mean() - b[idx].mean())
                              / a[idx].mean() * 100.0))
    ci_diff = tuple(float(v) for v in np.percentile(boot_diff, [2.5, 97.5]))
    ci_pct = tuple(float(v) for v in np.percentile(boot_pct, [2.5, 97.5]))

    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((a[keep].mean() - b[keep].mean())
                             / a[keep].mean() * 100.0))

    inconclusive = ci_diff[0] <= 0.0 <= ci_diff[1]
    if inconclusive:
        verdict = ("판정 보류 - 평균 차이가 0과 구분되지 않는다"
                   "(95% 부트스트랩 CI가 0을 포함)")
    elif improvement_pct > 0:
        verdict = "B가 이겼다"
    else:
        verdict = "A가 더 낫다"

    return {
        "n": n,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_diff": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "b_wins": wins,
        "a_wins": losses,
        "sd_diff": sd_diff,
        "sem_diff": sem_diff,
        "t_stat": t_stat,
        "sign_test_p": _sign_test_p(wins, losses),
        "ci_diff": ci_diff,
        "ci_pct": ci_pct,
        "dropone_pct_min": min(dropone),
        "dropone_pct_max": max(dropone),
        "dropone_flips_sign": min(dropone) <= 0.0 <= max(dropone),
        "inconclusive": inconclusive,
        "verdict": verdict,
    }


def print_summary(s, label_a="A", label_b="B"):
    print()
    print(f"평균 {label_a} ΔE (CIEDE2000, n={s['n']}): {s['mean_a']:.3f}")
    print(f"평균 {label_b} ΔE (CIEDE2000, n={s['n']}): {s['mean_b']:.3f}")
    print(f"개선폭({label_b} 기준): {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: {label_b} {s['b_wins']}승 {label_a} {s['a_wins']}패")
    print(f"페어드 차이({label_a}-{label_b}): 평균 {s['mean_diff']:+.3f} / 중앙값 "
          f"{s['median_diff']:+.3f} / 표준편차 {s['sd_diff']:.3f} "
          f"(t={s['t_stat']:.2f}, df={s['n'] - 1})")
    print(f"부호검정 양측 p = {s['sign_test_p']:.3f}")
    print(f"부트스트랩 95% CI - 평균 ΔE 차이: "
          f"[{s['ci_diff'][0]:+.3f}, {s['ci_diff'][1]:+.3f}] / "
          f"개선폭: [{s['ci_pct'][0]:+.1f}%, {s['ci_pct'][1]:+.1f}%]")
    print(f"drop-one 민감도: 한 쌍을 빼면 개선폭이 "
          f"{s['dropone_pct_min']:.1f}% ~ {s['dropone_pct_max']:.1f}% 사이로 움직인다"
          + (" (부호가 뒤집힌다)" if s["dropone_flips_sign"] else ""))
    print(f"판정: {s['verdict']}")


def main():
    print("=== R/B 선형 블렌딩 vs 하드-클러스터 ===")
    per_fold_rb = run_loocv("rb")
    summary_rb = summarize(per_fold_rb)
    print_summary(summary_rb, label_a="하드클러스터", label_b="RB블렌딩")

    print()
    print("=== CCT/mired 블렌딩 vs 하드-클러스터 ===")
    per_fold_cct = run_loocv("cct")
    summary_cct = summarize(per_fold_cct)
    print_summary(summary_cct, label_a="하드클러스터", label_b="CCT블렌딩")

    print()
    print("=== RB블렌딩 vs CCT블렌딩 직접 비교 ===")
    per_fold_direct = [(r[0], r[2], c[2]) for r, c in zip(per_fold_rb, per_fold_cct)]
    summary_direct = summarize(per_fold_direct)
    print_summary(summary_direct, label_a="RB블렌딩", label_b="CCT블렌딩")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the portable unit tests to verify they pass**

Run: `python3 -m unittest tests.test_evaluate_hncs_blend -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit the script and portable tests**

```bash
git add tools/evaluate_hncs_blend.py tests/test_evaluate_hncs_blend.py
git commit -m "Add HNCS illuminant-blend evaluation script (weighted LOO CV + significance tests)"
```

- [ ] **Step 6: Run the real 13-pair LOO experiment**

Decode is cached and not the bottleneck for this experiment (unlike the chromatic-aberration experiment) — the grid search runs on already-decoded, downsampled arrays. Expected runtime is unmeasured but should be much faster than the ~60-70 minute chromatic-aberration run since no RAW re-decoding happens per grid point. Run it and capture output:

```bash
python3 -m tools.evaluate_hncs_blend > /tmp/hncs_blend_output.log 2>&1
```

If it runs long enough that your turn might end before it completes, switch to background execution (`nohup ... &`) and poll `/tmp/hncs_blend_output.log`, following this project's established pattern for long-running research scripts. Do not fabricate results if your turn ends first — report `DONE_WITH_CONCERNS` with the log path so the controller can finish once it completes.

- [ ] **Step 7: Add a regression test reproducing the real recorded run**

Once Step 6 completes, copy the per-fold lines from `/tmp/hncs_blend_output.log` (13 lines each for the "rb" and "cct" sections) into hardcoded lists, and append this class to `tests/test_evaluate_hncs_blend.py` (following the exact pattern of `tests/test_evaluate_darktable_vs_rawpy.py`'s `TestSummarizeRecordedRun`):

```python
# 실제 13쌍 LOO 교차검증 재실행 기록값 - hybrid_engine/EVALUATION.md의
# "HNCS 조명 블렌딩 실험" 절에 실린 것과 정확히 같다.
# (name, de_hard, de_blend, weight)
_RECORDED_RB_RUN = [
    # <실제 Step 6 로그의 "R/B 선형 블렌딩" 섹션 13줄을 여기 옮겨적는다>
]
_RECORDED_CCT_RUN = [
    # <실제 Step 6 로그의 "CCT/mired 블렌딩" 섹션 13줄을 여기 옮겨적는다>
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 실제 13쌍 LOO 결과를
    재현하는 회귀 테스트."""

    def test_rb_reproduces_documented_means(self):
        s = summarize(_RECORDED_RB_RUN)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=2)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=2)

    def test_rb_reproduces_documented_sign_test_p(self):
        s = summarize(_RECORDED_RB_RUN)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)

    def test_cct_reproduces_documented_means(self):
        s = summarize(_RECORDED_CCT_RUN)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=2)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=2)

    def test_cct_reproduces_documented_sign_test_p(self):
        s = summarize(_RECORDED_CCT_RUN)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)
```

Fill in every `<실제값>` with the actual numbers `print_summary()` printed in Step 6's log — read them directly, do not guess or round by hand. This mirrors `tests/test_evaluate_darktable_vs_rawpy.py:107-140`.

Run: `python3 -m unittest tests.test_evaluate_hncs_blend -v`
Expected: all tests PASS, including the new `TestSummarizeRecordedRun` class.

- [ ] **Step 8: Document the result in `hybrid_engine/EVALUATION.md`**

Append a new section at the end of `hybrid_engine/EVALUATION.md`:

```markdown
## HNCS 조명 블렌딩 실험

`hybrid_engine/research/hncs_structural.py`의 하드-클러스터 구조
실험(AsShotNeutral R/B 비율 임계값 0.9로 2-클러스터 하드 분류, 평균
ΔE=10.191)을, 실제 HNCS가 쓴다고 알려진 방식(Lightroom
dual-illuminant DCP와 유사한 연속 블렌딩 - Luminous Landscape 포럼의
HNCS 메커니즘 분석 참고)으로 바꾸면 개선되는지 검증했다. 설계 근거:
[docs/superpowers/specs/2026-07-31-hncs-illuminant-blend-design.md](superpowers/specs/2026-07-31-hncs-illuminant-blend-design.md).

핫셀블라드 13쌍에 대해 두 가지 블렌딩 가중치 공식(R/B 비율 선형,
CCT/mired)을 각각 leave-one-out 교차검증으로 하드-클러스터와 비교.
매트릭스/chroma LUT 둘 다 가중 최소자승으로 피팅해 13쌍 전부가 두
앵커 모두에 기여하도록 함(하드-클러스터의 소수 클러스터 3쌍 문제를
해결).

<실제 13행 페어별 표를 R/B, CCT 각각 삽입: name | hard-cluster ΔE |
blend ΔE | weight>

**R/B 선형 블렌딩**: 평균 <실제값> vs 하드클러스터 <실제값>, 개선폭
<실제값>%, 부호검정 p=<실제값>, 부트스트랩 95% CI <실제값>. 판정:
<summarize()의 verdict 그대로>

**CCT/mired 블렌딩**: 평균 <실제값> vs 하드클러스터 <실제값>, 개선폭
<실제값>%, 부호검정 p=<실제값>, 부트스트랩 95% CI <실제값>. 판정:
<summarize()의 verdict 그대로>

**RB 블렌딩 vs CCT 블렌딩 직접 비교**: <실제값>

이 실험은 `apply_hncs()`(`brands/hasselblad.py`)나
`hasselblad.json`/`.dcp` 캘리브레이션 아티팩트를 전혀 건드리지
않았다.
```

Fill in every `<실제값>`/`<실제 13행...>` placeholder with the real numbers from Step 6/7 (verbatim from `print_summary()`'s output and the per-fold log lines) — do not invent or approximate them.

- [ ] **Step 9: Run the full test suite**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (513 pre-existing after Task 1 + new evaluate-script tests).

- [ ] **Step 10: Commit the real results**

```bash
git add tests/test_evaluate_hncs_blend.py hybrid_engine/EVALUATION.md
git commit -m "Record HNCS illuminant-blend LOO CV result (13 real Hasselblad pairs)"
```
