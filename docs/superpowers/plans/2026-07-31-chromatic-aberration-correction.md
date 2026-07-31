# Chromatic Aberration Correction Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine, with full LOO cross-validation and significance testing, whether rawpy's `chromatic_aberration` decode-stage parameter reduces ΔE against real camera JPEGs for the 13 real Hasselblad raw+jpeg pairs already on disk — a genuinely new axis (decode stage) none of this session's 20+ prior tuning experiments (all post-decode) have touched.

**Architecture:** Add an optional `chromatic_aberration` parameter to the existing `decode_raw()` utility (default `None` preserves current behavior for every existing call site, mirroring the `demosaic_algorithm` parameter already added for the Fuji demosaic experiment). Then a standalone research script grid-searches `(red_scale, blue_scale)` over a 9x9 grid with leave-one-out cross-validation across the 13 pairs, reusing this project's established `summarize()`/`_sign_test_p()` significance-testing pattern (`tools/evaluate_hncs_structural.py`, `tools/evaluate_darktable_vs_rawpy.py`).

**Tech Stack:** Python 3, `rawpy` (already a dependency), `colour-science` (via `hybrid_engine.utils.evaluate`), `numpy`, `opencv-python` (`cv2`), `unittest`.

## Global Constraints

- `brands/hasselblad.py`'s `apply_hncs()` must NEVER be modified.
- `hybrid_engine/assets/profiles/hasselblad.json` and any `.dcp` calibration artifact must NEVER be touched by this experiment.
- `decode_raw(path)` and `decode_raw(path, demosaic_algorithm=...)` (all existing call sites, e.g. `hybrid_engine/main.py`, `hybrid_engine/evaluation/fidelity.py`, `hybrid_engine/calibrate_profile.py`, `hybrid_engine/utils/evaluate.py`, `tools/evaluate_hncs_structural.py`, `tools/evaluate_fuji_demosaic.py`, etc.) must see **zero behavior change** — the new `chromatic_aberration` parameter must default to `None` and only affect `raw.postprocess()`'s kwargs when explicitly set.
- Grid: `red_scale` and `blue_scale` each range over `[0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]` (9 values, 0.005 step), full 9x9=81 cross product, per the approved spec (`docs/superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md`).
- Dataset: the 13 Hasselblad raw+jpeg pairs only (`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` + `raw_calib_cache/`, both already present on this container's local disk, `raw_calib_cache/` is git-ignored). No Fuji pairs in this experiment.
- **Measured decode cost (verified live in this environment, not estimated):** a single `chromatic_aberration`-parameterized `decode_raw()` call takes ~19.6s the first time a given RAW file is read (cold OS page cache) and ~2-4.6s on subsequent calls against the same file (warm cache, confirmed `(1.0, 1.0)` produces a byte-identical decode to omitting the kwarg entirely — verified with `np.array_equal`). Caching decoded+downsampled results by `(pair_name, red_scale, blue_scale)` and reusing them across all 13 LOO folds (each fold's grid search only needs the training pairs' already-cached values) keeps total real decode work at exactly 13 pairs x 81 grid points = 1053 decodes, no more, regardless of fold count. Measured total runtime for the full real run: **~60-70 minutes** (13 cold reads + 1040 warm reads). This MUST run as a background process (`run_in_background` or equivalent) — do not attempt to run it synchronously and wait.
- Downsample decoded+target images to `DOWNSAMPLE_MAX_DIM = 512` (long edge) immediately after each decode, before caching or computing ΔE — same pattern as `tools/evaluate_hncs_structural.py`/`tools/evaluate_darktable_vs_rawpy.py`. This does not meaningfully distort the result because chromatic aberration correction is a global per-channel scale operation, not spatially localized detail.
- ΔE measurement: `hybrid_engine.utils.evaluate.mean_delta_e` (CIEDE2000, this project's standard metric) exclusively.
- Never declare a winner from a raw mean-difference alone. Report the full `summarize()` output (paired t-test, sign test via `math.comb`, bootstrap 95% CI, drop-one sensitivity) and treat a 95% CI that straddles zero as "판정 보류" (inconclusive) — this project's established rule after 3 prior false "decisive" conclusions this session.
- Record the result in `hybrid_engine/EVALUATION.md` honestly whether it wins, loses, or is inconclusive.
- `raw_calib_cache/` and `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` paths and file-naming convention (`{jpeg_basename}.{raw_ext}` for the RAW, `{jpeg_basename}.target.jpg` for the target) are exactly as used in `tools/evaluate_hncs_structural.py` — reuse that same lookup logic (`_pair_names()`, `_raw_path_for()`, `_target_path_for()`), copied into the new standalone script per this project's established convention of not cross-importing between `tools/evaluate_*.py` research scripts.

---

### Task 1: `decode_raw()` optional `chromatic_aberration` parameter

**Files:**
- Modify: `hybrid_engine/utils/io.py:16-38` (the `decode_raw()` function)
- Test: `tests/test_io_decode_raw.py` (existing file — add a new test class, do not remove the existing `TestDecodeRawDemosaicParam` class)

**Interfaces:**
- Consumes: nothing new (`rawpy`, `numpy` already imported in `hybrid_engine/utils/io.py`).
- Produces: `decode_raw(raw_path, demosaic_algorithm=None, chromatic_aberration=None)` — same return type as before (`np.ndarray`, float64, shape `(H, W, 3)`, RGB, `[0, 1]`-ish range). Task 2 imports this and calls `decode_raw(raw_path, chromatic_aberration=(red_scale, blue_scale))`.

- [ ] **Step 1: Write the failing tests**

Add this new class to the end of `tests/test_io_decode_raw.py` (keep the existing `TestDecodeRawDemosaicParam` class and its imports untouched):

```python
class TestDecodeRawChromaticAberrationParam(unittest.TestCase):
    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_default_none_omits_chromatic_aberration_kwarg(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw")

        _, kwargs = mock_raw.postprocess.call_args
        self.assertNotIn("chromatic_aberration", kwargs)

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_explicit_tuple_is_passed_through(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", chromatic_aberration=(1.01, 0.99))

        _, kwargs = mock_raw.postprocess.call_args
        self.assertEqual(kwargs["chromatic_aberration"], (1.01, 0.99))

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_both_new_params_can_be_combined(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT,
                    chromatic_aberration=(1.0, 1.02))

        _, kwargs = mock_raw.postprocess.call_args
        self.assertEqual(kwargs["demosaic_algorithm"], rawpy.DemosaicAlgorithm.DHT)
        self.assertEqual(kwargs["chromatic_aberration"], (1.0, 1.02))

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_other_kwargs_unchanged_by_new_parameter(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", chromatic_aberration=(1.01, 0.99))

        _, kwargs = mock_raw.postprocess.call_args
        self.assertTrue(kwargs["use_camera_wb"])
        self.assertTrue(kwargs["no_auto_bright"])
        self.assertEqual(kwargs["output_bps"], 16)
        self.assertEqual(kwargs["output_color"], rawpy.ColorSpace.sRGB)
        self.assertEqual(kwargs["gamma"], (1, 1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_io_decode_raw -v`
Expected: the 4 new tests FAIL with `TypeError: decode_raw() got an unexpected keyword argument 'chromatic_aberration'`; the pre-existing `TestDecodeRawDemosaicParam` tests still PASS.

- [ ] **Step 3: Modify `decode_raw()`**

Replace `hybrid_engine/utils/io.py:16-38` (the current `decode_raw` function) with:

```python
def decode_raw(raw_path, demosaic_algorithm=None, chromatic_aberration=None):
    """RAW -> Linear RGB, float64 [0, 1] 근방(하이라이트는 1을 넘을 수
    있음), shape (H, W, 3), RGB 순서. 카메라 고유 색공간이 아니라 sRGB
    프라이머리 기준 선형광(linear light) 값 - 이후 core/pipeline이
    이 프라이머리를 그대로 XYZ 변환 기준으로 쓴다.

    demosaic_algorithm: None(기본값)이면 rawpy 기본 데모자이크를 쓰고
    기존 호출부와 100% 동일하게 동작한다. rawpy.DemosaicAlgorithm 값을
    넘기면 raw.postprocess()에 그대로 전달된다(예: X-Trans용 DHT 비교
    실험 - tools/evaluate_fuji_demosaic.py 참고). AMAZE는 이 프로젝트가
    쓰는 LibRaw 빌드에 GPL3 데모자이크 팩이 없어 런타임 에러가 난다.

    chromatic_aberration: None(기본값)이면 색수차 보정 없이 기존과
    100% 동일하게 동작한다(rawpy 기본값 (1.0, 1.0)과 결과가 바이트
    단위로 동일함을 실측 확인). (red_scale, blue_scale) 튜플을 넘기면
    raw.postprocess()에 그대로 전달돼 R/B 채널을 스케일링해서 렌즈
    색수차를 보정한다(tools/evaluate_chromatic_aberration.py 참고)."""
    kwargs = dict(
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(1, 1),  # 순수 linear
    )
    if demosaic_algorithm is not None:
        kwargs["demosaic_algorithm"] = demosaic_algorithm
    if chromatic_aberration is not None:
        kwargs["chromatic_aberration"] = chromatic_aberration
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(**kwargs)
    return rgb16.astype(np.float64) / 65535.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_io_decode_raw -v`
Expected: all 8 tests PASS (4 pre-existing + 4 new).

- [ ] **Step 5: Run the full test suite to confirm no regression**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (490 pre-existing + 4 new = 494).

- [ ] **Step 6: Commit**

```bash
git add hybrid_engine/utils/io.py tests/test_io_decode_raw.py
git commit -m "Add optional chromatic_aberration parameter to decode_raw()"
```

---

### Task 2: `tools/evaluate_chromatic_aberration.py` — grid search + LOO CV + real run + documentation

**Files:**
- Create: `tools/evaluate_chromatic_aberration.py`
- Test: `tests/test_evaluate_chromatic_aberration.py`
- Modify: `hybrid_engine/EVALUATION.md` (append new section at the end)

**Interfaces:**
- Consumes: `decode_raw(raw_path, chromatic_aberration=(red_scale, blue_scale))` from Task 1; `hybrid_engine.utils.io.load_image_linear`; `hybrid_engine.utils.evaluate.mean_delta_e`.
- Produces: `load_pairs()`, `grid_search(train_pairs)`, `run_loocv()`, `summarize(per_fold)`, `_sign_test_p(wins, losses)`, `print_summary(s)`, `_resize_max_dim(img, max_dim)` — all pure/standalone functions in `tools/evaluate_chromatic_aberration.py`, importable by the test file.

- [ ] **Step 1: Write the failing portable unit tests**

Create `tests/test_evaluate_chromatic_aberration.py`:

```python
import csv
import os
import tempfile
import unittest

import numpy as np

from tools.evaluate_chromatic_aberration import (
    _resize_max_dim, _sign_test_p, load_pairs, summarize,
)

_FIELDS = ["camera", "lens", "photographer", "jpeg_url", "raw_url", "page_url",
           "exif_datetime_original", "exif_camera_model", "exif_lens",
           "exif_iso", "exif_focal_length", "exif_pair_verified"]


class TestLoadPairs(unittest.TestCase):
    def _write_manifest_and_cache(self, jpeg_names):
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        cache_dir = tempfile.mkdtemp()
        with os.fdopen(csv_fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            for name in jpeg_names:
                row = {field: "" for field in _FIELDS}
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

    def test_known_exact_value(self):
        # C(13,3) 이하 누적 / 2^13, 양측 - 부호검정 정의 자체를 검증
        self.assertAlmostEqual(_sign_test_p(10, 3), 0.046142578125, places=9)


class TestSummarizeShape(unittest.TestCase):
    """summarize()가 반환하는 dict의 키/타입만 검증 - 실제 13쌍 실행
    결과에 대한 회귀 테스트는 실행 후 Step 7에서 별도로 추가한다."""

    def test_returns_expected_keys(self):
        per_fold = [
            ("p1", 10.0, 8.0, 1.0, 0.99),
            ("p2", 12.0, 12.5, 1.0, 1.0),
            ("p3", 9.0, 7.5, 0.99, 1.0),
        ]
        s = summarize(per_fold)
        for key in ("n", "mean_baseline", "mean_corrected", "mean_diff",
                    "median_diff", "improvement_pct", "corrected_wins",
                    "baseline_wins", "sd_diff", "sem_diff", "t_stat",
                    "sign_test_p", "ci_diff", "ci_pct", "dropone_pct_min",
                    "dropone_pct_max", "dropone_flips_sign", "inconclusive",
                    "verdict"):
            self.assertIn(key, s)
        self.assertEqual(s["n"], 3)
        self.assertEqual(s["corrected_wins"], 2)
        self.assertEqual(s["baseline_wins"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_evaluate_chromatic_aberration -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.evaluate_chromatic_aberration'`.

- [ ] **Step 3: Implement `tools/evaluate_chromatic_aberration.py`**

```python
"""rawpy postprocess()의 chromatic_aberration=(red_scale, blue_scale)
파라미터가 핫셀블라드 13쌍(raw+jpeg)의 ΔE(CIEDE2000)를 줄이는지
leave-one-out 교차검증으로 확인한다. 설계 근거:
docs/superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md

  python3 -m tools.evaluate_chromatic_aberration

이번 세션에서 처음으로 "디코드 단계"(그 이전 20여 회의 모든 실험은
디코드 이후 그레이월드/톤커브/LUT/공간연산만 조정)를 건드리는 실험이다.

**측정된 성능 특성** (설계 문서에 근거 기록): chromatic_aberration이
지정된 decode_raw() 호출은 같은 RAW 파일을 처음 열 때(OS 페이지캐시
미스) ~19.6초, 같은 파일을 다시 열 때(캐시 히트) ~2~4.6초 걸린다.
(1.0, 1.0)은 인자를 아예 안 넘긴 것과 바이트 단위로 동일한 결과를
낸다(실측 확인) - 그래서 베이스라인도 그리드의 (1.0, 1.0) 지점 재사용.
디코드+축소본을 (pair명, red_scale, blue_scale)로 캐시해서 13개 LOO
폴드 전체에서 같은 조합을 한 번만 디코드한다 - 총 13쌍 x 81격자점 =
1053회 디코드, 실측 총 실행시간 ~60~70분. 반드시 백그라운드로 돌릴 것.
"""
import csv
import glob
import itertools
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from hybrid_engine.utils.evaluate import mean_delta_e
from hybrid_engine.utils.io import decode_raw, load_image_linear

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
CSV_PATH = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")

RED_GRID = [0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]
BLUE_GRID = [0.98, 0.985, 0.99, 0.995, 1.0, 1.005, 1.01, 1.015, 1.02]

DOWNSAMPLE_MAX_DIM = 512

_DECODE_CACHE = {}
_TARGET_CACHE = {}


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


def _decoded_and_target(pair, red_scale, blue_scale):
    """(디코드+축소본, 축소된 타깃) - (name, red_scale, blue_scale)로
    캐시해서 LOO 폴드 간 같은 조합의 RAW 재디코드를 막는다."""
    key = (pair["name"], red_scale, blue_scale)
    if key not in _DECODE_CACHE:
        decoded = decode_raw(pair["raw_path"],
                              chromatic_aberration=(red_scale, blue_scale))
        _DECODE_CACHE[key] = _resize_max_dim(decoded, DOWNSAMPLE_MAX_DIM)
    decoded = _DECODE_CACHE[key]
    name = pair["name"]
    if name not in _TARGET_CACHE:
        _TARGET_CACHE[name] = load_image_linear(pair["target_path"],
                                                  resize_to=decoded.shape[:2])
    return decoded, _TARGET_CACHE[name]


def delta_e_for(pair, red_scale, blue_scale):
    decoded, target = _decoded_and_target(pair, red_scale, blue_scale)
    return mean_delta_e(decoded, target)


def grid_search(train_pairs):
    """train_pairs 평균 ΔE(CIEDE2000)가 최소인 (red_scale, blue_scale)
    반환 - 9x9=81 전 조합 탐색."""
    best_params, best_de = (1.0, 1.0), float("inf")
    for red_scale, blue_scale in itertools.product(RED_GRID, BLUE_GRID):
        des = [delta_e_for(p, red_scale, blue_scale) for p in train_pairs]
        mean_de = float(np.mean(des))
        if mean_de < best_de:
            best_de, best_params = mean_de, (red_scale, blue_scale)
    return best_params


def run_loocv():
    pairs = load_pairs()
    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        best_red, best_blue = grid_search(train)
        de_baseline = delta_e_for(held_out, 1.0, 1.0)
        de_corrected = delta_e_for(held_out, best_red, best_blue)
        per_fold.append((held_out["name"], de_baseline, de_corrected,
                          best_red, best_blue))
        print(f"  [{held_out['name']}] baseline ΔE={de_baseline:.3f} "
              f"corrected ΔE={de_corrected:.3f} "
              f"params=({best_red}, {best_blue})", flush=True)
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
    """폴드별 (name, de_baseline, de_corrected, red_scale, blue_scale)
    리스트 -> 요약 통계 dict. 평균 차이 하나로 승패를 선언하지 않는다 -
    부호검정, 부트스트랩 신뢰구간, drop-one 민감도를 같이 내고 0을
    포함하면 '판정 보류'로 보고한다. 순수 함수라 기록된 폴드 결과만
    으로도 재현할 수 있다(tests/test_evaluate_chromatic_aberration.py)."""
    baseline = np.array([row[1] for row in per_fold], dtype=np.float64)
    corrected = np.array([row[2] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = baseline - corrected  # 양수 = 보정이 그 폴드에서 더 좋음(ΔE 감소)
    mean_baseline = float(baseline.mean())
    mean_corrected = float(corrected.mean())
    improvement_pct = (mean_baseline - mean_corrected) / mean_baseline * 100.0

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
        boot_pct.append(float((baseline[idx].mean() - corrected[idx].mean())
                              / baseline[idx].mean() * 100.0))
    ci_diff = tuple(float(v) for v in np.percentile(boot_diff, [2.5, 97.5]))
    ci_pct = tuple(float(v) for v in np.percentile(boot_pct, [2.5, 97.5]))

    dropone = []
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        dropone.append(float((baseline[keep].mean() - corrected[keep].mean())
                             / baseline[keep].mean() * 100.0))

    inconclusive = ci_diff[0] <= 0.0 <= ci_diff[1]
    if inconclusive:
        verdict = ("판정 보류 - 평균 차이가 0과 구분되지 않는다"
                   "(95% 부트스트랩 CI가 0을 포함)")
    elif improvement_pct > 0:
        verdict = "색수차 보정이 이겼다"
    else:
        verdict = "보정 없음(기존 decode_raw())이 더 낫다"

    return {
        "n": n,
        "mean_baseline": mean_baseline,
        "mean_corrected": mean_corrected,
        "mean_diff": float(diff.mean()),
        "median_diff": float(np.median(diff)),
        "improvement_pct": improvement_pct,
        "corrected_wins": wins,
        "baseline_wins": losses,
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


def print_summary(s):
    print()
    print(f"평균 baseline ΔE (CIEDE2000, n={s['n']}): {s['mean_baseline']:.3f}")
    print(f"평균 corrected ΔE (CIEDE2000, n={s['n']}): {s['mean_corrected']:.3f}")
    print(f"개선폭: {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: 보정 {s['corrected_wins']}승 {s['baseline_wins']}패")
    print(f"페어드 차이: 평균 {s['mean_diff']:+.3f} / 중앙값 "
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
    per_fold = run_loocv()
    print_summary(summarize(per_fold))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the portable unit tests to verify they pass**

Run: `python3 -m unittest tests.test_evaluate_chromatic_aberration -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit the script and portable tests**

```bash
git add tools/evaluate_chromatic_aberration.py tests/test_evaluate_chromatic_aberration.py
git commit -m "Add chromatic aberration correction evaluation script (LOO CV + significance tests)"
```

- [ ] **Step 6: Run the real 13-pair LOO experiment in the background**

This takes ~60-70 minutes (measured decode cost, see Global Constraints). Run it in the background and capture output to a log file:

```bash
nohup python3 -m tools.evaluate_chromatic_aberration > /tmp/ca_eval_output.log 2>&1 &
```

Poll periodically (e.g. `tail -20 /tmp/ca_eval_output.log`) until the process completes and `판정:` appears in the output. Do not block synchronously waiting — if your turn ends while this is still running, the next turn should check `/tmp/ca_eval_output.log` for completion before re-running (re-running from scratch wastes ~60 minutes; the decode cache is in-process only, not persisted to disk, so a genuinely interrupted run must restart from Step 6, not resume).

- [ ] **Step 7: Add a regression test reproducing the real recorded run**

Once Step 6 completes, copy the 13 per-fold lines (`[name] baseline ΔE=... corrected ΔE=... params=(...)`) from `/tmp/ca_eval_output.log` into a hardcoded list, and append this class to `tests/test_evaluate_chromatic_aberration.py` (following the exact pattern of `tests/test_evaluate_darktable_vs_rawpy.py`'s `TestSummarizeRecordedRun`/`_RECORDED_16_PAIR_RUN`):

```python
# 실제 13쌍 LOO 교차검증 재실행 기록값 - hybrid_engine/EVALUATION.md의
# "색수차 보정(chromatic aberration) 실험" 절에 실린 것과 정확히 같다.
# (name, de_baseline, de_corrected, best_red, best_blue)
_RECORDED_13_PAIR_RUN = [
    # <실제 Step 6 로그의 13줄을 여기 그대로 옮겨적는다>
]


class TestSummarizeRecordedRun(unittest.TestCase):
    """hybrid_engine/EVALUATION.md에 기록된 실제 13쌍 LOO 결과를
    재현하는 회귀 테스트 - 스크립트를 다시 안 돌려도(60~70분 소요)
    문서의 통계 수치를 검증할 수 있다."""

    def setUp(self):
        self.s = summarize(_RECORDED_13_PAIR_RUN)

    def test_reproduces_documented_means(self):
        self.assertAlmostEqual(self.s["mean_baseline"], <실제값>, places=2)
        self.assertAlmostEqual(self.s["mean_corrected"], <실제값>, places=2)

    def test_reproduces_documented_win_counts(self):
        self.assertEqual(self.s["corrected_wins"], <실제값>)
        self.assertEqual(self.s["baseline_wins"], <실제값>)

    def test_reproduces_documented_sign_test_p(self):
        self.assertAlmostEqual(self.s["sign_test_p"], <실제값>, places=9)

    def test_reproduces_documented_t_stat(self):
        self.assertAlmostEqual(self.s["t_stat"], <실제값>, places=3)
```

Fill in every `<실제값>` with the actual numbers `summarize()` printed in Step 6's log (do not guess or round by hand — read them directly from `print_summary()`'s output, which already prints `mean_baseline`, `mean_corrected`, `sign_test_p`, `t_stat`, etc. to the precision needed). This mirrors `tests/test_evaluate_darktable_vs_rawpy.py:107-140` exactly.

Run: `python3 -m unittest tests.test_evaluate_chromatic_aberration -v`
Expected: all tests PASS, including the new `TestSummarizeRecordedRun` class.

- [ ] **Step 8: Document the result in `hybrid_engine/EVALUATION.md`**

Append a new section at the end of `hybrid_engine/EVALUATION.md`:

```markdown
## 색수차 보정(chromatic aberration) 실험

이번 세션의 20여 회 후속 실측은 전부 디코드 이후 단계(그레이월드,
톤커브, hue/chroma LUT, 공간 연산)만 건드렸다. 이 실험은 처음으로
디코드 단계 자체 - rawpy의 `chromatic_aberration=(red_scale,
blue_scale)` 파라미터(R/B 채널 스케일링으로 렌즈 횡색수차 보정) - 를
건드린다. 설계 근거:
[docs/superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md](superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md).

핫셀블라드 13쌍(`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` +
`raw_calib_cache/`)에 대해 red_scale/blue_scale 각 9값(0.98~1.02,
0.005 간격, 9x9=81 조합) 그리드서치 + leave-one-out 교차검증.
베이스라인은 보정 없음((1.0, 1.0), `decode_raw()` 기본 동작과 바이트
단위로 동일함을 실측 확인).

<실제 13행 페어별 표를 여기 삽입: name | baseline ΔE | corrected ΔE |
선택된 (red_scale, blue_scale)>

평균 baseline ΔE (CIEDE2000, n=13): <실제값>
평균 corrected ΔE (CIEDE2000, n=13): <실제값>
개선폭: <실제값>%
폴드 승패: 보정 <N>승 베이스라인 <M>패
부호검정 양측 p = <실제값>
대응표본 t-검정: t(12) = <실제값>
부트스트랩 95% CI - 평균 ΔE 차이: [<실제값>, <실제값>]
drop-one 민감도: <실제값>

**판정: <summarize()가 낸 verdict를 그대로, 이기든 지든 애매하든
정직하게>**

이 실험은 `apply_hncs()`(`brands/hasselblad.py`)나
`hasselblad.json`/`.dcp` 캘리브레이션 아티팩트를 전혀 건드리지
않았다 - 순수히 `decode_raw()` 유틸리티 레벨 비교.
```

Fill in every `<실제값>`/`<실제 13행...>` placeholder with the real numbers from Step 6/7 (verbatim from `print_summary()`'s output and the per-fold log lines) — do not invent or approximate them.

- [ ] **Step 9: Run the full test suite**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (494 pre-existing after Task 1 + new evaluate-script tests).

- [ ] **Step 10: Commit the real results**

```bash
git add tests/test_evaluate_chromatic_aberration.py hybrid_engine/EVALUATION.md
git commit -m "Record chromatic aberration correction LOO CV result (13 real Hasselblad pairs)"
```
