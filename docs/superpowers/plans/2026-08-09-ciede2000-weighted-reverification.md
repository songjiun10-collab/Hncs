# CIEDE2000 (kL,kC,kH) Weighted Re-verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional (kL, kC, kH) weighting to this project's CIEDE2000 measurement, verify it reproduces the existing default exactly, then re-run 3 of the project's ΔE-based research experiments under a published paper's optimized weights (4.1, 1.1, 1.6) to see whether any past verdict changes.

**Architecture:** `hybrid_engine/utils/evaluate.py` gains a `delta_E_CIE2000_weighted()` helper that reuses `colour.difference.delta_e.intermediate_attributes_CIE2000()`'s pre-combination terms (colour-science's own `delta_E_CIE2000` has no way to pass arbitrary kL/kC/kH — confirmed by reading its source, it only supports a fixed `textiles=True` → kL=2 preset). `mean_delta_e()`/`delta_e_map()` grow optional `kL=1.0, kC=1.0, kH=1.0` keyword arguments routed through this helper, defaulting to today's exact behavior. Three research scripts (`tools/evaluate_hncs_blend.py`, `tools/evaluate_fuji_demosaic.py`, `tools/evaluate_darktable_vs_rawpy.py`) get a matching `--kl/--kc/--kh` CLI flag threaded down to every `mean_delta_e()` call in their pipelines, then get re-run for real with (4.1, 1.1, 1.6) and their results recorded in `hybrid_engine/EVALUATION.md`.

**Tech Stack:** Python 3, `colour-science` 0.4.7 (already a dependency, no version change), `numpy`, `unittest`.

## Global Constraints

- `brands/hasselblad.py`'s `apply_hncs()` and its parameters must NEVER be modified. This plan re-measures existing experiment pipelines with a different ΔE formula — it never re-fits or re-derives anything shipped.
- `hybrid_engine/assets/profiles/hasselblad.json` and any `.dcp` file must NEVER be touched.
- `mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000")` and `delta_e_map(rgb_a_linear, rgb_b_linear, method="CIE 2000")` keep their exact current default behavior — new `kL=1.0, kC=1.0, kH=1.0` keyword arguments only, no positional signature change, so all 7 existing call sites need zero changes.
- `delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=1.0, kC=1.0, kH=1.0)` at kL=kC=kH=1.0 must equal `colour.delta_E(Lab_1, Lab_2, method="CIE 2000")` bit-for-bit (verified during spec research: max abs diff 0.0 over 1000 random Lab pairs, and cross-checked against `colour.delta_E(..., textiles=True)` at kL=2.0 with the same exact-match result).
- Paper's optimized weights for the re-verification runs: **(kL, kC, kH) = (4.1, 1.1, 1.6)**.
- Scope is 3 scripts only, not 5: `evaluate_hncs_structural.py` and `evaluate_chromatic_aberration.py` were independently rewritten by another session to use `skimage.color.deltaE_ciede2000` against a hardcoded local macOS path (`RAW_DIR = "/Users/songjiun/Documents/raw pair"`) and dpreview-sourced data not present in this container — do not modify those two files in this plan.
- `evaluate_hncs_blend.py`'s hard-cluster comparisons (`HARD_CLUSTER_DE` constant, a (1,1,1)-era hardcoded baseline) are **not** re-verified — only its self-contained RB-vs-CCT direct comparison, which needs no external baseline, runs under new weights.
- Record results in `hybrid_engine/EVALUATION.md` as a **new subsection appended under each experiment's existing section** (not a `> 정정(...)` correction blockquote — the old (1,1,1) numbers aren't wrong, they're a different, still-valid measurement).

---

### Task 1: `hybrid_engine/utils/evaluate.py` — weighted CIEDE2000 core

**Files:**
- Modify: `hybrid_engine/utils/evaluate.py`
- Test: `tests/test_hybrid_engine.py` (existing file — add to the existing `TestEvaluate` class and one new class)

**Interfaces:**
- Produces: `delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=1.0, kC=1.0, kH=1.0) -> np.ndarray`, `mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000", kL=1.0, kC=1.0, kH=1.0) -> float`, `delta_e_map(rgb_a_linear, rgb_b_linear, method="CIE 2000", kL=1.0, kC=1.0, kH=1.0) -> np.ndarray`. Tasks 2-4 import `mean_delta_e` unchanged and pass the new keyword arguments.

- [ ] **Step 1: Write the failing tests**

Add this import and these two things to `tests/test_hybrid_engine.py`: extend the existing `from hybrid_engine.utils.evaluate import mean_delta_e` line to also import `delta_E_CIE2000_weighted`, and add a new test class after `TestEvaluate` (leave `TestEvaluate`'s 3 existing tests untouched):

```python
from hybrid_engine.utils.evaluate import delta_E_CIE2000_weighted, mean_delta_e
```

```python
class TestDeltaE2000Weighted(unittest.TestCase):
    """delta_E_CIE2000_weighted()가 (1,1,1)에서 colour.delta_E()와
    정확히 같은지, 그리고 mean_delta_e()의 kL/kC/kH 인자가 기본값일 때
    기존 동작을 안 바꾸는지 확인."""

    def test_matches_colour_science_default_at_111(self):
        import colour
        rng = np.random.default_rng(0)
        Lab_1 = rng.uniform([0, -80, -80], [100, 80, 80], size=(200, 3))
        Lab_2 = rng.uniform([0, -80, -80], [100, 80, 80], size=(200, 3))
        official = colour.delta_E(Lab_1, Lab_2, method="CIE 2000")
        mine = delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=1.0, kC=1.0, kH=1.0)
        np.testing.assert_allclose(mine, official, atol=1e-9)

    def test_matches_colour_science_textiles_at_kl2(self):
        import colour
        rng = np.random.default_rng(1)
        Lab_1 = rng.uniform([0, -80, -80], [100, 80, 80], size=(50, 3))
        Lab_2 = rng.uniform([0, -80, -80], [100, 80, 80], size=(50, 3))
        official_textiles = colour.delta_E(Lab_1, Lab_2, method="CIE 2000", textiles=True)
        mine_kl2 = delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=2.0, kC=1.0, kH=1.0)
        np.testing.assert_allclose(mine_kl2, official_textiles, atol=1e-9)

    def test_higher_kl_reduces_lightness_dominated_delta_e(self):
        # 순수 명도차만 있는 두 Lab 값 - kL을 올리면 ΔE가 줄어야 한다
        Lab_1 = np.array([[50.0, 0.0, 0.0]])
        Lab_2 = np.array([[70.0, 0.0, 0.0]])
        de_default = delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=1.0, kC=1.0, kH=1.0)
        de_high_kl = delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=4.1, kC=1.1, kH=1.6)
        self.assertLess(de_high_kl[0], de_default[0])


class TestMeanDeltaEWeightedDefaultUnchanged(unittest.TestCase):
    """mean_delta_e()/delta_e_map()에 kL/kC/kH 기본값(1.0)으로 호출하면
    새 인자를 아예 안 넘긴 것과 결과가 완전히 같아야 한다 - 기존 7개
    호출부의 동작이 이 변경으로 바뀌지 않는다는 회귀 증거."""

    def test_mean_delta_e_default_matches_no_kwargs(self):
        rng = np.random.default_rng(2)
        a = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        b = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        self.assertEqual(mean_delta_e(a, b), mean_delta_e(a, b, kL=1.0, kC=1.0, kH=1.0))

    def test_mean_delta_e_weighted_differs_from_default(self):
        rng = np.random.default_rng(3)
        a = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        b = rng.uniform(0.05, 0.9, size=(6, 6, 3))
        default = mean_delta_e(a, b)
        weighted = mean_delta_e(a, b, kL=4.1, kC=1.1, kH=1.6)
        self.assertNotEqual(default, weighted)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest tests.test_hybrid_engine.TestDeltaE2000Weighted tests.test_hybrid_engine.TestMeanDeltaEWeightedDefaultUnchanged -v`
Expected: `ImportError: cannot import name 'delta_E_CIE2000_weighted'`.

- [ ] **Step 3: Implement in `hybrid_engine/utils/evaluate.py`**

Add near the top (after the existing `import colour` and `_SRGB = ...` lines, before `_linear_rgb_to_lab`):

```python
from colour.difference.delta_e import intermediate_attributes_CIE2000
from dataclasses import astuple


def delta_E_CIE2000_weighted(Lab_1, Lab_2, kL=1.0, kC=1.0, kH=1.0):
    """CIEDE2000을 커스텀 (kL, kC, kH)로 계산. colour-science의
    delta_E_CIE2000()은 kL/kC/kH를 임의로 못 받는다(textiles=True일 때
    kL=2 고정만 지원 - 소스 확인함, colour/difference/delta_e.py). 결합
    전 중간값(S_L, S_C, S_H, ΔL', ΔC', ΔH', R_T)을 반환하는
    intermediate_attributes_CIE2000()을 재사용해서 직접 결합한다 -
    hue 회전 등 복잡한 기하 계산은 colour-science 것을 그대로 쓰므로
    재구현 위험이 없다. kL=kC=kH=1.0이면 colour.delta_E(method="CIE
    2000")과 정확히 같아야 한다(tests/test_hybrid_engine.py의
    TestDeltaE2000Weighted가 확인)."""
    S_L, S_C, S_H, delta_L_p, delta_C_p, delta_H_p, R_T = astuple(
        intermediate_attributes_CIE2000(Lab_1, Lab_2))
    return np.sqrt(
        (delta_L_p / (kL * S_L)) ** 2
        + (delta_C_p / (kC * S_C)) ** 2
        + (delta_H_p / (kH * S_H)) ** 2
        + R_T * (delta_C_p / (kC * S_C)) * (delta_H_p / (kH * S_H))
    )
```

Then change `mean_delta_e` and `delta_e_map` to:

```python
def mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000", kL=1.0, kC=1.0, kH=1.0):
    """두 linear RGB 이미지(shape 동일) 사이 픽셀별 ΔE 평균. kL/kC/kH는
    method=="CIE 2000"일 때만 의미가 있다(다른 method는 무시하고 기존
    colour.delta_E 그대로) - 기본값 1.0이면 이 세 인자를 추가하기 전과
    완전히 동일하게 동작한다."""
    if rgb_a_linear.shape != rgb_b_linear.shape:
        raise ValueError(f"shape mismatch: {rgb_a_linear.shape} vs {rgb_b_linear.shape}")
    lab_a = _linear_rgb_to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _linear_rgb_to_lab(rgb_b_linear).reshape(-1, 3)
    if method == "CIE 2000":
        delta = delta_E_CIE2000_weighted(lab_a, lab_b, kL=kL, kC=kC, kH=kH)
    else:
        delta = colour.delta_E(lab_a, lab_b, method=method)
    return float(np.mean(delta))


def delta_e_map(rgb_a_linear, rgb_b_linear, method="CIE 2000", kL=1.0, kC=1.0, kH=1.0):
    """픽셀별 ΔE 맵 (H, W) - 오차가 큰 영역을 시각화할 때 사용."""
    if rgb_a_linear.shape != rgb_b_linear.shape:
        raise ValueError(f"shape mismatch: {rgb_a_linear.shape} vs {rgb_b_linear.shape}")
    h, w = rgb_a_linear.shape[:2]
    lab_a = _linear_rgb_to_lab(rgb_a_linear).reshape(-1, 3)
    lab_b = _linear_rgb_to_lab(rgb_b_linear).reshape(-1, 3)
    if method == "CIE 2000":
        delta = delta_E_CIE2000_weighted(lab_a, lab_b, kL=kL, kC=kC, kH=kH)
    else:
        delta = colour.delta_E(lab_a, lab_b, method=method)
    return np.asarray(delta).reshape(h, w)
```

Do not change any other function in this file (`load_image_linear_for_evaluate`, `evaluate`) — they call `mean_delta_e` with no `method`/`kL`/`kC`/`kH` arguments and inherit the new defaults automatically.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest tests.test_hybrid_engine -v`
Expected: all tests PASS, including the 5 new ones and the pre-existing `TestEvaluate` tests (unchanged behavior).

- [ ] **Step 5: Commit**

```bash
git add hybrid_engine/utils/evaluate.py tests/test_hybrid_engine.py
git commit -m "Add optional (kL,kC,kH) weighting to mean_delta_e/delta_e_map

colour-science's delta_E_CIE2000 has no way to pass arbitrary kL/kC/kH
(only a fixed textiles=True -> kL=2 preset) - reuses its
intermediate_attributes_CIE2000() pre-combination terms instead of
reimplementing the geometry. Verified bit-exact at (1,1,1) and against
textiles mode. Defaults unchanged, so all existing callers are
unaffected."
```

---

### Task 2: `tools/evaluate_hncs_blend.py` — weighted RB-vs-CCT re-verification

**Files:**
- Modify: `tools/evaluate_hncs_blend.py`

**Interfaces:**
- Consumes: `mean_delta_e` from Task 1 (now accepts `kL`/`kC`/`kH`).
- Produces: `main()` now accepts `--kl/--kc/--kh` CLI flags (default 1.0 each). When any is not 1.0, it skips the two hard-cluster comparisons and only runs+prints the RB-vs-CCT direct comparison.

- [ ] **Step 1: Thread `kL`/`kC`/`kH` through the fitting/evaluation chain**

Modify `_blend_combo_mean` (currently at line 277) to accept and use the weights:

```python
def _blend_combo_mean(names, weights, matrix_a, matrix_b, sat_mult, hue_shift_deg,
                       kL=1.0, kC=1.0, kH=1.0):
    sum_a, total_a, sum_b, total_b = 0.0, 0.0, 0.0, 0.0
    for name in names:
        w = weights[name]
        wb_rgb, target = _PAIR_DATA_CACHE[name]
        blended_matrix = (1.0 - w) * matrix_a + w * matrix_b
        matrixed = apply_color_matrix(wb_rgb, blended_matrix)
        chroma_applied = apply_chroma_lut(matrixed, sat_mult, hue_shift_deg)
        result = film_curve(chroma_applied, toe_lift=FILM_CURVE_TOE_LIFT,
                             shoulder_start=FILM_CURVE_SHOULDER_START,
                             white_point=FILM_CURVE_WHITE_POINT)
        de = mean_delta_e(result, target, kL=kL, kC=kC, kH=kH)
        sum_a += (1.0 - w) * de
        total_a += (1.0 - w)
        sum_b += w * de
        total_b += w
    return sum_a, total_a, sum_b, total_b
```

Modify `_blend_combo_task` to unpack the extra 3 values (it's called via `pool.map`, which only passes one positional argument, so the weights ride inside the same tuple):

```python
def _blend_combo_task(args):
    names, weights, matrix_a, matrix_b, sat_mult, hue_shift_deg, kL, kC, kH = args
    sum_a, total_a, sum_b, total_b = _blend_combo_mean(
        names, weights, matrix_a, matrix_b, sat_mult, hue_shift_deg, kL, kC, kH)
    return (sat_mult, hue_shift_deg), sum_a, total_a, sum_b, total_b
```

Modify `fit_weighted_chroma_lut` (currently at line 303) to accept and forward the weights:

```python
def fit_weighted_chroma_lut(train_pairs, weights, matrix_a, matrix_b, pool=None,
                             kL=1.0, kC=1.0, kH=1.0):
    """앵커A/B용 (sat_mult, hue_shift_deg)를 각각 가중 평균 ΔE 최소화로
    그리드서치. 매트릭스는 이미 그 폴드에서 피팅된 blended matrix(각
    페어 자기 가중치로 블렌딩)를 먼저 적용한 뒤 후보 chroma 파라미터를
    얹어 평가한다 - apply_hncs_structural_blend()가 예측 시 실제로
    하는 순서와 일치시키기 위함. pool이 있으면 49개 콤보를 워커들에
    나눠 계산한다(결과는 직렬 실행과 수학적으로 동일). kL/kC/kH는
    이 그리드서치의 선택 기준 자체를 바꾼다 - 기본(1,1,1)에서 벗어나면
    최적 (sat_mult, hue_shift_deg)도 달라질 수 있다."""
    names = [p["name"] for p in train_pairs]
    combos = list(itertools.product(SAT_MULT_GRID, HUE_SHIFT_GRID))
    if pool is None:
        results = [((s, h), *_blend_combo_mean(names, weights, matrix_a, matrix_b, s, h,
                                                 kL, kC, kH))
                   for s, h in combos]
    else:
        tasks = [(names, weights, matrix_a, matrix_b, s, h, kL, kC, kH) for s, h in combos]
        results = pool.map(_blend_combo_task, tasks)

    best_a, best_a_score = (1.0, 0.0), float("inf")
    best_b, best_b_score = (1.0, 0.0), float("inf")
    for combo, sum_a, total_a, sum_b, total_b in results:
        if total_a > 0:
            score_a = sum_a / total_a
            if score_a < best_a_score:
                best_a_score, best_a = score_a, combo
        if total_b > 0:
            score_b = sum_b / total_b
            if score_b < best_b_score:
                best_b_score, best_b = score_b, combo
    return best_a, best_b
```

Modify `run_loocv` (currently at line 333) to accept and forward the weights, and to skip the `HARD_CLUSTER_DE` lookup entirely when weighted (that constant is only valid at (1,1,1) — see Global Constraints):

```python
def run_loocv(weight_fn_name, pool=None, kL=1.0, kC=1.0, kH=1.0):
    """weight_fn_name: "rb" 또는 "cct". 74개 폴드 전부에 대해
    (name, de_hard, de_blend, weight) 튜플 리스트를 반환한다. kL/kC/kH가
    (1,1,1)이 아니면 de_hard는 None이다 - HARD_CLUSTER_DE는 (1,1,1)
    기준으로 측정된 상수라 다른 가중치에서는 안 맞다(사용하려면
    evaluate_hncs_structural.py를 그 가중치로 다시 돌려야 하는데, 그
    스크립트는 이 환경에서 실행 불가 - docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md
    참고)."""
    pairs = combine_pairs(load_pairs())
    bounds = compute_population_bounds(pairs)
    weight_fn = pair_weight_rb if weight_fn_name == "rb" else pair_weight_cct
    weights = compute_weights_by_name(pairs, weight_fn, bounds)
    is_weighted = (kL, kC, kH) != (1.0, 1.0, 1.0)

    per_fold = []
    for i, held_out in enumerate(pairs):
        train = pairs[:i] + pairs[i + 1:]
        matrix_a, matrix_b = fit_weighted_matrices(train, weights)
        chroma_a, chroma_b = fit_weighted_chroma_lut(train, weights, matrix_a, matrix_b, pool,
                                                       kL, kC, kH)

        w_held = weights[held_out["name"]]
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
        de_blend = mean_delta_e(result, target, kL=kL, kC=kC, kH=kH)
        de_hard = None if is_weighted else HARD_CLUSTER_DE[held_out["name"]]

        per_fold.append((held_out["name"], de_hard, de_blend, w_held))
        hard_str = "N/A(가중 모드)" if is_weighted else f"{de_hard:.3f}"
        print(f"  [{held_out['name']}] hard-cluster ΔE={hard_str} "
              f"blend({weight_fn_name}) ΔE={de_blend:.3f} "
              f"weight={w_held:.3f}", flush=True)
    return per_fold
```

- [ ] **Step 2: Add the CLI flag and branch `main()`**

Replace `main()` with:

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kl", type=float, default=1.0, help="CIEDE2000 kL 가중치 (기본 1.0)")
    parser.add_argument("--kc", type=float, default=1.0, help="CIEDE2000 kC 가중치 (기본 1.0)")
    parser.add_argument("--kh", type=float, default=1.0, help="CIEDE2000 kH 가중치 (기본 1.0)")
    args = parser.parse_args()
    kL, kC, kH = args.kl, args.kc, args.kh
    is_weighted = (kL, kC, kH) != (1.0, 1.0, 1.0)

    pairs = combine_pairs(load_pairs())
    print(f"페어 {len(pairs)}개 - 디코드 캐시 준비 중(메인 프로세스)", flush=True)
    _init_worker(pairs)  # 메인 프로세스도 fit_weighted_matrices()/held-out 평가용으로 필요
    pool = mp.Pool(processes=N_WORKERS, initializer=_init_worker, initargs=(pairs,)) \
        if N_WORKERS > 1 else None
    if pool is not None:
        print(f"워커 {N_WORKERS}개에 디코드 캐시 배포 중 (RB/CCT 두 실행이 공유)", flush=True)
    try:
        if is_weighted:
            print(f"=== 가중 모드 (kL={kL}, kC={kC}, kH={kH}) - 하드클러스터 비교 생략 ===")
        else:
            print("=== R/B 선형 블렌딩 vs 하드-클러스터 ===")
        per_fold_rb = run_loocv("rb", pool, kL, kC, kH)
        if not is_weighted:
            summary_rb = summarize(per_fold_rb)
            print_summary(summary_rb, label_a="하드클러스터", label_b="RB블렌딩")

        print()
        if not is_weighted:
            print("=== CCT/mired 블렌딩 vs 하드-클러스터 ===")
        per_fold_cct = run_loocv("cct", pool, kL, kC, kH)
        if not is_weighted:
            summary_cct = summarize(per_fold_cct)
            print_summary(summary_cct, label_a="하드클러스터", label_b="CCT블렌딩")
    finally:
        if pool is not None:
            pool.close()
            pool.join()

    print()
    print("=== RB블렌딩 vs CCT블렌딩 직접 비교 ===")
    per_fold_direct = [(r[0], r[2], c[2]) for r, c in zip(per_fold_rb, per_fold_cct)]
    summary_direct = summarize(per_fold_direct)
    print_summary(summary_direct, label_a="RB블렌딩", label_b="CCT블렌딩")


if __name__ == "__main__":
    main()
```

Add `import argparse` to the top of the file alongside the other stdlib imports (`csv`, `glob`, `itertools`, `math`, `multiprocessing as mp`, `os`, `sys`).

- [ ] **Step 3: Run the portable tests to verify nothing broke**

Run: `python3 -m unittest tests.test_evaluate_hncs_blend -v`
Expected: all pre-existing tests PASS (this task doesn't touch `summarize`/`_sign_test_p`/`print_summary`, only the fitting/evaluation chain and `main()`).

- [ ] **Step 4: Smoke-test the new CLI flag parses and threads through correctly**

Run: `python3 -c "
import tools.evaluate_hncs_blend as m
import inspect
sig = inspect.signature(m.run_loocv)
assert list(sig.parameters) == ['weight_fn_name', 'pool', 'kL', 'kC', 'kH'], sig
sig2 = inspect.signature(m._blend_combo_mean)
assert list(sig2.parameters) == ['names', 'weights', 'matrix_a', 'matrix_b', 'sat_mult', 'hue_shift_deg', 'kL', 'kC', 'kH'], sig2
print('signatures OK')
"`
Expected: `signatures OK`, no errors.

- [ ] **Step 5: Commit**

```bash
git add tools/evaluate_hncs_blend.py
git commit -m "Add --kl/--kc/--kh to evaluate_hncs_blend.py

Threads custom CIEDE2000 weights through the chroma-LUT grid search
and LOO evaluation. Hard-cluster comparisons are skipped in weighted
mode (HARD_CLUSTER_DE is a (1,1,1)-era constant, invalid at other
weights) - only the self-contained RB-vs-CCT direct comparison runs."
```

---

### Task 3: `tools/evaluate_fuji_demosaic.py` — weighted re-verification

**Files:**
- Modify: `tools/evaluate_fuji_demosaic.py`

**Interfaces:**
- Consumes: `mean_delta_e` from Task 1.
- Produces: `main()` accepts `--kl/--kc/--kh` (default 1.0 each).

- [ ] **Step 1: Thread `kL`/`kC`/`kH` through**

Modify `compare_pair`:

```python
def compare_pair(pair, kL=1.0, kC=1.0, kH=1.0):
    """(기본 데모자이크 ΔE, DHT ΔE) 반환 - 같은 카메라 JPEG 타깃 대비.
    데모자이크 알고리즘을 바꿔도 출력 해상도는 동일하므로 타깃은
    한 번만 로드한다."""
    default_linear = decode_raw(pair["raw_path"])
    dht_linear = decode_raw(pair["raw_path"], demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)
    target = load_image_linear_for_evaluate(pair["jpeg_path"], default_linear.shape)
    de_default = mean_delta_e(default_linear, target, kL=kL, kC=kC, kH=kH)
    de_dht = mean_delta_e(dht_linear, target, kL=kL, kC=kC, kH=kH)
    return de_default, de_dht
```

Modify `run_comparison`:

```python
def run_comparison(kL=1.0, kC=1.0, kH=1.0):
    pairs = load_pairs()
    results = []
    for pair in pairs:
        de_default, de_dht = compare_pair(pair, kL, kC, kH)
        improved = de_dht < de_default
        results.append((pair["camera"], de_default, de_dht, improved))
        print(f"  [{pair['camera']}] 기본 ΔE={de_default:.3f} DHT ΔE={de_dht:.3f} "
              f"({'DHT 개선' if improved else '기본이 더 나음'})", flush=True)
    return results
```

Replace `main()`:

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kl", type=float, default=1.0, help="CIEDE2000 kL 가중치 (기본 1.0)")
    parser.add_argument("--kc", type=float, default=1.0, help="CIEDE2000 kC 가중치 (기본 1.0)")
    parser.add_argument("--kh", type=float, default=1.0, help="CIEDE2000 kH 가중치 (기본 1.0)")
    args = parser.parse_args()

    results = run_comparison(args.kl, args.kc, args.kh)
    n_improved = sum(1 for _, _, _, improved in results if improved)
    n_total = len(results)
    print()
    print(f"DHT가 더 나은 페어: {n_improved}/{n_total}")
    print("주의: X-Trans에서 LibRaw는 AHD/DHT/AAHD를 전부 같은 Markesteijn")
    print("데모자이크로 합친다 - 위 숫자 차이는 알고리즘 차이가 아니라")
    print("멀티스레드 디코드의 논디터미니즘이다(OMP_NUM_THREADS=1로 고정하면")
    print("바이트 단위로 동일해짐, 직접 확인됨). 자세한 내용은")
    print("hybrid_engine/EVALUATION.md 참고.")


if __name__ == "__main__":
    main()
```

Add `import argparse` to the top of the file alongside the existing `csv`, `os`, `sys` imports.

- [ ] **Step 2: Smoke-test signatures**

Run: `python3 -c "
import tools.evaluate_fuji_demosaic as m
import inspect
assert list(inspect.signature(m.compare_pair).parameters) == ['pair', 'kL', 'kC', 'kH']
assert list(inspect.signature(m.run_comparison).parameters) == ['kL', 'kC', 'kH']
print('signatures OK')
"`
Expected: `signatures OK`, no errors.

- [ ] **Step 3: Commit**

```bash
git add tools/evaluate_fuji_demosaic.py
git commit -m "Add --kl/--kc/--kh to evaluate_fuji_demosaic.py"
```

---

### Task 4: `tools/evaluate_darktable_vs_rawpy.py` — weighted re-verification

**Files:**
- Modify: `tools/evaluate_darktable_vs_rawpy.py`

**Interfaces:**
- Consumes: `mean_delta_e` from Task 1.
- Produces: `main()` accepts `--kl/--kc/--kh` (default 1.0 each).

- [ ] **Step 1: Thread `kL`/`kC`/`kH` through**

Modify `check_determinism`:

```python
def check_determinism(pair, kL=1.0, kC=1.0, kH=1.0):
    """같은 파일을 rawpy/darktable 각각 두 번 디코드해서 재현성
    노이즈 바닥을 ΔE(CIEDE2000) 단위로 잰다(두 디코드끼리 직접 비교,
    JPEG 타깃 없이) - 실제 비교(디코더 간 ΔE 차이)와 같은 단위라야
    "노이즈보다 큰가"를 판단할 수 있다."""
    rawpy_1 = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    rawpy_2 = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    rawpy_noise_de = mean_delta_e(rawpy_1, rawpy_2, kL=kL, kC=kC, kH=kH)

    dt_1 = _resize_max_dim(decode_raw_darktable(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    dt_2 = _resize_max_dim(decode_raw_darktable(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    dt_noise_de = mean_delta_e(dt_1, dt_2, kL=kL, kC=kC, kH=kH)

    print(f"  [{pair['name']}] rawpy 반복-디코드 ΔE={rawpy_noise_de:.6f}  "
          f"darktable 반복-디코드 ΔE={dt_noise_de:.6f}", flush=True)
    return rawpy_noise_de, dt_noise_de
```

Modify `compare_pair`:

```python
def compare_pair(pair, kL=1.0, kC=1.0, kH=1.0):
    """(rawpy ΔE, darktable ΔE) 반환 - 같은 카메라 JPEG 타깃 대비."""
    rawpy_linear = _resize_max_dim(decode_raw(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    dt_linear = _resize_max_dim(decode_raw_darktable(pair["raw_path"]), DOWNSAMPLE_MAX_DIM)
    target_rawpy = load_image_linear_for_evaluate(pair["jpeg_path"], rawpy_linear.shape)
    target_dt = load_image_linear_for_evaluate(pair["jpeg_path"], dt_linear.shape)
    de_rawpy = mean_delta_e(rawpy_linear, target_rawpy, kL=kL, kC=kC, kH=kH)
    de_dt = mean_delta_e(dt_linear, target_dt, kL=kL, kC=kC, kH=kH)
    return de_rawpy, de_dt
```

Modify `run_comparison`:

```python
def run_comparison(kL=1.0, kC=1.0, kH=1.0):
    pairs = load_all_pairs()
    results = []
    for pair in pairs:
        de_rawpy, de_dt = compare_pair(pair, kL, kC, kH)
        improved = de_dt < de_rawpy
        results.append((pair["camera"], pair["name"], de_rawpy, de_dt, improved))
        print(f"  [{pair['camera']}/{pair['name']}] rawpy ΔE={de_rawpy:.3f} "
              f"darktable ΔE={de_dt:.3f} "
              f"({'darktable 개선' if improved else 'rawpy가 더 나음'})", flush=True)
    return results
```

Replace `main()`:

```python
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kl", type=float, default=1.0, help="CIEDE2000 kL 가중치 (기본 1.0)")
    parser.add_argument("--kc", type=float, default=1.0, help="CIEDE2000 kC 가중치 (기본 1.0)")
    parser.add_argument("--kh", type=float, default=1.0, help="CIEDE2000 kH 가중치 (기본 1.0)")
    args = parser.parse_args()
    kL, kC, kH = args.kl, args.kc, args.kh

    print("반복-디코드 노이즈 바닥 측정 (ΔE CIEDE2000 단위, 대표 파일 각 1장):")
    hasselblad_pairs = load_hasselblad_pairs()
    fuji_pairs = load_fuji_pairs()
    noise_pairs = [check_determinism(hasselblad_pairs[0], kL, kC, kH),
                   check_determinism(fuji_pairs[0], kL, kC, kH)]
    max_noise_de = max(n for pair_noise in noise_pairs for n in pair_noise)
    print(f"측정된 최대 노이즈 바닥: ΔE {max_noise_de:.6f}")
    print("(참고: 이 값은 반복-디코드 재현성만 재는 것이지 통계적 유의성")
    print(" 검정이 아니다 - 실제 유의성은 아래 부호검정/t-통계량을 본다)")
    print()

    print("전체 16쌍 비교:")
    results = run_comparison(kL, kC, kH)
    s = summarize(results)
    print_summary(s)


if __name__ == "__main__":
    main()
```

Add `import argparse` to the top of the file alongside the existing `csv`, `glob`, `math`, `os`, `sys` imports.

- [ ] **Step 2: Smoke-test signatures**

Run: `python3 -c "
import tools.evaluate_darktable_vs_rawpy as m
import inspect
assert list(inspect.signature(m.check_determinism).parameters) == ['pair', 'kL', 'kC', 'kH']
assert list(inspect.signature(m.compare_pair).parameters) == ['pair', 'kL', 'kC', 'kH']
assert list(inspect.signature(m.run_comparison).parameters) == ['kL', 'kC', 'kH']
print('signatures OK')
"`
Expected: `signatures OK`, no errors.

- [ ] **Step 3: Commit**

```bash
git add tools/evaluate_darktable_vs_rawpy.py
git commit -m "Add --kl/--kc/--kh to evaluate_darktable_vs_rawpy.py"
```

---

### Task 5: Run all 3 under (4.1, 1.1, 1.6) and record results

**Files:**
- Modify: `hybrid_engine/EVALUATION.md` (append a new subsection under each of the 3 experiments' existing sections)

**Interfaces:**
- Consumes: Tasks 2-4's `--kl/--kc/--kh` CLI flags.
- Produces: nothing further consumes this — terminal task of this plan.

- [ ] **Step 1: Launch all 3 in background simultaneously**

None of these 3 depend on each other (unlike the original 5-script design — see the spec's "재검증 범위" section). Launch all three at once:

```bash
nohup python3 -m tools.evaluate_hncs_blend --kl 4.1 --kc 1.1 --kh 1.6 > /tmp/hncs_blend_weighted.log 2>&1 &
nohup python3 -m tools.evaluate_fuji_demosaic --kl 4.1 --kc 1.1 --kh 1.6 > /tmp/fuji_demosaic_weighted.log 2>&1 &
nohup python3 -m tools.evaluate_darktable_vs_rawpy --kl 4.1 --kc 1.1 --kh 1.6 > /tmp/darktable_vs_rawpy_weighted.log 2>&1 &
```

`evaluate_fuji_demosaic` (3 pairs, no grid search) and
`evaluate_darktable_vs_rawpy` (16 pairs, no grid search) should finish in
minutes. `evaluate_hncs_blend` (74-pair LOO with a 49-combo grid search
per fold) originally took 4h22m at (1,1,1) with 3 workers — expect a
similar duration here. Use `Monitor` to watch all three logs, filtering
for progress **and** failure: `ΔE=|판정:|Traceback|Error|Killed|OOM`. If
your turn ends before `evaluate_hncs_blend` finishes, report
`DONE_WITH_CONCERNS` with the log path — do not fabricate its result.

- [ ] **Step 2: Record `evaluate_fuji_demosaic`'s result**

Once `/tmp/fuji_demosaic_weighted.log` completes, read it and append this subsection to `hybrid_engine/EVALUATION.md` directly under the existing "Fuji X-Trans 데모자이크 알고리즘 비교" section (find it with `grep -n "Fuji X-Trans 데모자이크" hybrid_engine/EVALUATION.md`):

```markdown
#### (kL,kC,kH)=(4.1,1.1,1.6) 가중치 재검증 (2026-08-09)

이수연·곽영신, "디지털 영상의 색차 측정을 위한 CIEDE2000 최적화"
(한국색채학회 2014 춘계학술대회, DBpia/KCI가 이 환경에서 접근 차단이라
원문 전체는 미확인 - 사용자 캡처 화면 + DBpia AI 요약카드로 확인한
값에 의존)이 STRESS 지표로 찾은 디지털 영상용 최적 파라미터로 재실행.
설계 근거: [docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md](../docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md).

<Step 1 로그의 3개 페어 결과 표: 카메라 | 기본 ΔE | DHT ΔE>

DHT가 더 나은 페어: <실제값>/3. 기존 (1,1,1) 결과와 <같음/다름> - 이
실험은 애초에 두 디코드 경로가 X-Trans에서 바이트 단위로 동일한
출력을 내므로(멀티스레드 논디터미니즘만 차이) ΔE 공식을 바꿔도 결론
("DHT vs 기본은 실질적으로 같은 코드")이 바뀔 근거가 없다 - 그대로
확인됐다면 이 재검증 자체가 그 사실의 교차검증이다.
```

Fill in every `<...>` with the real log output — do not invent or approximate.

- [ ] **Step 3: Record `evaluate_darktable_vs_rawpy`'s result**

Once `/tmp/darktable_vs_rawpy_weighted.log` completes, find the existing section (`grep -n "rawpy vs darktable\|RAW 디코드 프로그램" hybrid_engine/EVALUATION.md`) and append:

```markdown
#### (kL,kC,kH)=(4.1,1.1,1.6) 가중치 재검증 (2026-08-09)

같은 논문 근거로 재실행(위 Fuji 데모자이크 절 참고). 설계 근거:
[docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md](../docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md).

평균 rawpy ΔE: <실제값>, 평균 darktable ΔE: <실제값>, 부호검정 p=<실제값>.
기존 (1,1,1) 판정(거의 대등, rawpy 평균 ΔE 11.460 vs darktable 11.970,
부호검정 p=0.021)과 <같음/다름>.
```

Fill in every `<...>` with the real log output.

- [ ] **Step 4: Record `evaluate_hncs_blend`'s result and add a regression test**

Once `/tmp/hncs_blend_weighted.log` completes, find the RB-vs-CCT
direct-comparison section's output (the last `=== RB블렌딩 vs CCT블렌딩
직접 비교 ===` block in the log) and append to
`tests/test_evaluate_hncs_blend.py` (add `from tools.evaluate_hncs_blend
import summarize` if not already imported at module level — check first,
the file already has `summarize` defined locally so no import is
needed, just use it directly):

```python
# 실제 (kL,kC,kH)=(4.1,1.1,1.6) 재검증 재실행 기록값 - RB-vs-CCT
# 직접비교만(하드클러스터 비교는 가중 모드에서 생략, 스펙 참고).
# hybrid_engine/EVALUATION.md의 새 하위절에 실린 것과 정확히 같다.
_RECORDED_WEIGHTED_RB_VS_CCT = [
    # <Step 1 로그의 "RB블렌딩 vs CCT블렌딩 직접 비교" 페어별 값을 여기 옮겨적는다>
]


class TestWeightedReverificationRecordedRun(unittest.TestCase):
    def test_reproduces_documented_weighted_verdict(self):
        s = summarize(_RECORDED_WEIGHTED_RB_VS_CCT)
        self.assertAlmostEqual(s["mean_a"], <실제값>, places=2)
        self.assertAlmostEqual(s["mean_b"], <실제값>, places=2)
        self.assertAlmostEqual(s["sign_test_p"], <실제값>, places=9)
```

Fill in every `<...>` from the real log — do not guess or hand-round.
Then find the existing "HNCS 조명 블렌딩 실험" section in
`hybrid_engine/EVALUATION.md` and append:

```markdown
#### (kL,kC,kH)=(4.1,1.1,1.6) 가중치 재검증 - RB vs CCT만 (2026-08-09)

같은 논문 근거로 재실행(위 Fuji 데모자이크 절 참고). 하드클러스터
대비 비교(RB/CCT 각각)는 이번엔 뺐다 - `HARD_CLUSTER_DE`가 (1,1,1)
기준 상수라 다른 가중치와 비교하면 자가 달라진다(설계 근거:
[docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md](../docs/superpowers/specs/2026-08-09-ciede2000-weighted-reverification-design.md)).
RB 블렌딩 vs CCT 블렌딩 직접 비교만 재검증(양쪽 다 같은 실행에서
라이브로 재므로 기준선 문제 없음).

평균 RB ΔE: <실제값>, 평균 CCT ΔE: <실제값>, 부호검정 p=<실제값>. 기존
(1,1,1) 판정(RB vs CCT는 판정 보류 - 둘이 사실상 동일)과 <같음/다름>.
```

Run: `python3 -m unittest tests.test_evaluate_hncs_blend -v`
Expected: all tests PASS including the new one.

- [ ] **Step 5: Run the full test suite**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS except the pre-existing environment-only
failures already present before this plan (missing `torch`/GUI deps,
missing `skimage`-based `evaluate_chromatic_aberration`/
`evaluate_hncs_structural` tests — none of those are touched by this
plan).

- [ ] **Step 6: Commit**

```bash
git add hybrid_engine/EVALUATION.md tests/test_evaluate_hncs_blend.py
git commit -m "Record CIEDE2000 (4.1,1.1,1.6) re-verification results

Re-ran evaluate_hncs_blend (RB-vs-CCT only), evaluate_fuji_demosaic,
and evaluate_darktable_vs_rawpy under the paper's optimized weights.
evaluate_hncs_structural.py and evaluate_chromatic_aberration.py were
out of scope (rewritten by another session to depend on a local macOS
path and skimage, unavailable in this container)."
```

If any verdict changed from the (1,1,1) baseline, say so explicitly when reporting this task complete — don't bury it in the commit message alone.
