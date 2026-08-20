# v11↔v12 하이브리드(regularize) 74쌍 재실행 + 유의성 검정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tools/calibrate.py`의 `regularize` 모드(v11 파라메트릭 ↔ v12
학습 LUT 하이브리드)를 74쌍(공식 13 + local-mixed-2026-07 61, 4세대)으로
재실행하고, 최적 λ가 순수 v11/v12 대비 통계적으로 유의미한지 검정한다.

**Architecture:** 기존 `_collect_pair_pixels()`가 공식 페어만 쓰던 걸
`_resolve_pairs()`(이미 공식+로컬 병합 지원) 기반으로 바꾸고, 페어별
`(counts, sums)`를 한 번만 계산해 전체 합에서 held-out 분을 빼는
방식으로 LOO를 재작성한다(재계산 없이 O(256)로 폴드 처리 - 병렬화
불필요). 유의성 검정은 `tools/evaluate_hncs_blend.py`의 부호검정/
부트스트랩CI/drop-one 코드를 복사해 붙인다.

**Tech Stack:** Python, numpy, rawpy, cv2. 신규 의존성 없음.

## Global Constraints

- `apply_hncs()`(`brands/hasselblad.py`)와 `hasselblad.json`/`.dcp`는
  어떤 태스크에서도 건드리지 않는다.
- ΔE(CIEDE2000) 기반이 아니라 이 파일의 기존 관례(b2/w995 percentile
  RMSE)를 그대로 따른다 - `tools/evaluate_*.py`의 ΔE 관례를 여기 섞지
  않는다.
- 통계 함수는 `tools/evaluate_hncs_blend.py`에서 복사(import 아님) -
  `tools/CLAUDE.md`: "Standalone. Never import from a sibling
  evaluate_*.py — copy the loader instead."
- 뺄셈 기반 LOO가 기존 재계산 방식과 **수학적으로 동일한 결과**를
  내는지 반드시 테스트로 고정한다(이번 리팩토링의 핵심 불변조건).
- 결과 기록은 파일별 기존 컨벤션을 따른다: `brands/*.py`는 docstring에
  날짜 붙여 append, `docs/measurements.md`/`.en.md`는 새 표만 추가
  (기존 표는 안 건드림).

---

### Task 1: 로컬 페어 세대 라벨 + `_resolve_pairs()`에 `generation` 필드 추가

**Files:**
- Modify: `tools/calibrate.py` (`collect_local_pairs()` 약 L57-77,
  `_resolve_pairs()` 약 L209-225)
- Test: `tests/test_calibrate.py` (신규 파일)

**Interfaces:**
- Consumes: 없음 (최하위 태스크)
- Produces: `_generation_for(camera: str) -> str`, `collect_local_pairs()`가
  반환하는 각 dict에 `generation` 키 추가, `_resolve_pairs()`가 반환하는
  각 dict에도 `generation` 키 추가(공식=`"공식 샘플(X1D 계열)"` 고정,
  로컬=`_generation_for(camera)`). Task 2/3이 이 `generation` 필드를
  그대로 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_calibrate.py` 새로 생성:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.calibrate import _generation_for


class TestGenerationFor(unittest.TestCase):
    def test_cfv_passthrough(self):
        self.assertEqual(_generation_for("CFV 100C/907X"), "CFV 100C/907X")

    def test_x2d_passthrough(self):
        self.assertEqual(_generation_for("X2D 100C"), "X2D 100C")

    def test_x1d_ii_mapped(self):
        self.assertEqual(_generation_for("Hasselblad X1D II 50C"), "X1D II 50C")

    def test_x1d_mapped(self):
        self.assertEqual(_generation_for("Hasselblad X1D"), "X1D")

    def test_unknown_camera_passthrough(self):
        self.assertEqual(_generation_for("Some New Camera"), "Some New Camera")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python3 -m unittest tests.test_calibrate -v`
Expected: FAIL - `ImportError: cannot import name '_generation_for'`

- [ ] **Step 3: `tools/calibrate.py`에 `_generation_for` 추가 + `collect_local_pairs()`/`_resolve_pairs()` 수정**

`import rawpy` 아래, `sys.path.insert` 위/아래 상관없이 모듈 상단부에
추가(다른 모듈 상수들 근처, `CACHE_DIR`/`CSV_PATH` 정의 다음 줄부터):

```python
_GENERATION_MAP = {
    "Hasselblad X1D II 50C": "X1D II 50C",
    "Hasselblad X1D": "X1D",
}


def _generation_for(camera):
    """로컬 기여 manifest.csv의 camera 필드를 docs/measurements.md의
    기존 세대 버킷 라벨로 정규화. 이미 그 라벨 형태인 값(CFV 100C/907X,
    X2D 100C)은 그대로 통과."""
    return _GENERATION_MAP.get(camera, camera)
```

`collect_local_pairs()`의 `pairs.append(...)` 블록을 다음으로 교체
(파일 안 함수 전체는 아래처럼 됨 - 바뀐 줄만 표시):

```python
def collect_local_pairs():
    """datasets/hasselblad/contributed/<세트>/manifest.csv의 로컬 raw+jpeg
    페어 수집 (tools.verify_contributed_pairs 통과 전제 - 여기선 파일 존재만
    재확인). 공식 샘플(collect_pairs, 원격 URL)과 별개 출처라 함수를 분리."""
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "datasets", "hasselblad", "contributed")
    pairs = []
    if not os.path.isdir(base):
        return pairs
    for set_name in sorted(os.listdir(base)):
        manifest = os.path.join(base, set_name, "manifest.csv")
        if not os.path.exists(manifest):
            continue
        for row in csv.DictReader(open(manifest, encoding='utf-8-sig')):
            raw_path = os.path.join(base, set_name, "raw", row["filename_raw"])
            jpeg_path = os.path.join(base, set_name, "jpeg", row["filename_jpeg"])
            if os.path.exists(raw_path) and os.path.exists(jpeg_path):
                pairs.append(dict(
                    filename=f"{set_name}__{os.path.splitext(row['filename_raw'])[0]}",
                    raw_path=raw_path, jpeg_path=jpeg_path,
                    generation=_generation_for(row["camera"])))
    return pairs
```

`_resolve_pairs()`의 공식 페어 append 줄에 `generation` 고정값 추가
(바뀐 부분만):

```python
def _resolve_pairs():
    """공식 샘플(collect_pairs, 원격 URL - 다운로드해서 캐시에 확보) + 로컬
    기여 페어(collect_local_pairs, 이미 로컬에 있음)를 raw_path/jpeg_path가
    바로 붙은 공통 포맷으로 합친다. generation 필드도 붙여 반환(공식은
    한 버킷 "공식 샘플(X1D 계열)", 로컬은 카메라별)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    resolved = []
    for r in collect_pairs():
        ext = os.path.splitext(r['raw_url'])[1]
        raw_path = os.path.join(CACHE_DIR, r['filename'] + ext)
        jpeg_path = os.path.join(CACHE_DIR, r['filename'] + '.target.jpg')
        if download(r['raw_url'].strip(), raw_path) and download(r['jpeg_url'].strip(), jpeg_path):
            resolved.append(dict(filename=r['filename'], raw_path=raw_path, jpeg_path=jpeg_path,
                                  generation="공식 샘플(X1D 계열)"))
    n_official = len(resolved)
    local_pairs = collect_local_pairs()
    resolved.extend(local_pairs)
    print(f"공식 샘플 페어 {n_official}개 + 로컬 기여 페어 {len(local_pairs)}개 = 총 {len(resolved)}개")
    return resolved
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `python3 -m unittest tests.test_calibrate -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 기존 테스트/전체 스위트가 안 깨졌는지 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 기존 535개 + 신규 5개 = 540개 전부 PASS (calibrate.py를 쓰는
다른 코드가 `generation` 필드 추가로 깨지지 않는지 확인 - 특히
`hybrid_engine/utils/pairs.py::load_local_pairs()`는 dict에서 필요한
키만 골라 쓰므로 영향 없어야 함)

- [ ] **Step 6: 커밋**

```bash
git add tools/calibrate.py tests/test_calibrate.py
git commit -m "Add camera-generation labeling to calibrate.py pair loaders"
```

---

### Task 2: `_pair_counts_sums` + `_build_lut_from_counts` (뺄셈 LOO의 기반)

**Files:**
- Modify: `tools/calibrate.py` (`_build_lut` 약 L372-380)
- Test: `tests/test_calibrate.py`

**Interfaces:**
- Consumes: 없음 (순수 함수, Task 1과 독립)
- Produces: `_pair_counts_sums(neutral_l: np.ndarray, target_l: np.ndarray) -> (counts: np.ndarray[256], sums: np.ndarray[256])`,
  `_build_lut_from_counts(counts, sums, prior, lam) -> np.ndarray[256] float32`.
  Task 3이 이 두 함수로 뺄셈 기반 LOO 루프를 만든다. 기존 `_build_lut(neutral_l, target_l, prior, lam)`은
  **삭제**(더 이상 쓰는 곳이 없어짐 - `run_regularize()`가 Task 3에서
  `_build_lut_from_counts`로 완전히 대체됨).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_calibrate.py`에 추가:

```python
import numpy as np


class TestPairCountsSums(unittest.TestCase):
    def test_matches_manual_bincount(self):
        from tools.calibrate import _pair_counts_sums
        neutral_l = np.array([10, 10, 20, 250], dtype=np.int64)
        target_l = np.array([12.0, 14.0, 22.0, 240.0], dtype=np.float64)
        counts, sums = _pair_counts_sums(neutral_l, target_l)
        self.assertEqual(counts.shape, (256,))
        self.assertEqual(sums.shape, (256,))
        self.assertEqual(counts[10], 2)
        self.assertEqual(sums[10], 26.0)
        self.assertEqual(counts[20], 1)
        self.assertEqual(sums[20], 22.0)
        self.assertEqual(counts[250], 1)
        self.assertEqual(sums[250], 240.0)
        self.assertEqual(counts[0], 0)
        self.assertEqual(sums[0], 0.0)


class TestBuildLutFromCounts(unittest.TestCase):
    def test_lambda_zero_is_pure_empirical_mean(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.zeros(256, dtype=np.float64)
        sums = np.zeros(256, dtype=np.float64)
        counts[100] = 4
        sums[100] = 4 * 150.0  # 평균 150
        prior = np.arange(256, dtype=np.float32)  # prior[100] = 100
        lut = _build_lut_from_counts(counts, sums, prior, lam=0)
        self.assertAlmostEqual(lut[100], 150.0, places=4)

    def test_huge_lambda_converges_to_prior(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.zeros(256, dtype=np.float64)
        sums = np.zeros(256, dtype=np.float64)
        counts[100] = 4
        sums[100] = 4 * 150.0
        prior = np.arange(256, dtype=np.float32)
        lut = _build_lut_from_counts(counts, sums, prior, lam=1e9)
        self.assertAlmostEqual(lut[100], 100.0, places=1)

    def test_empty_bin_falls_back_to_prior(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.zeros(256, dtype=np.float64)
        sums = np.zeros(256, dtype=np.float64)
        prior = np.arange(256, dtype=np.float32)
        lut = _build_lut_from_counts(counts, sums, prior, lam=0)
        self.assertAlmostEqual(lut[50], 50.0, places=4)

    def test_monotonic_nondecreasing(self):
        from tools.calibrate import _build_lut_from_counts
        counts = np.array([0, 5, 0, 3] + [0] * 252, dtype=np.float64)
        sums = np.array([0, 5 * 200.0, 0, 3 * 10.0] + [0.0] * 252, dtype=np.float64)
        prior = np.arange(256, dtype=np.float32)
        lut = _build_lut_from_counts(counts, sums, prior, lam=0)
        self.assertTrue(np.all(np.diff(lut) >= 0))
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python3 -m unittest tests.test_calibrate -v`
Expected: FAIL - `ImportError: cannot import name '_pair_counts_sums'`

- [ ] **Step 3: `tools/calibrate.py`에서 `_build_lut`를 아래로 교체**

기존 `_build_lut(neutral_l, target_l, prior, lam)` 함수 전체를 삭제하고
그 자리에:

```python
def _pair_counts_sums(neutral_l, target_l):
    """페어 한 장의 neutral_L->target_L 픽셀 대응을 bincount로 집계.
    LOO 뺄셈에 쓰기 위해 페어별로 한 번만 계산해둔다."""
    counts = np.bincount(neutral_l, minlength=256).astype(np.float64)
    sums = np.bincount(neutral_l, weights=target_l.astype(np.float64), minlength=256)
    return counts, sums


def _build_lut_from_counts(counts, sums, prior, lam):
    """counts/sums(여러 페어를 이미 합친 것이든, 전체에서 한 페어를 뺀
    것이든 상관없이)로부터 ridge-정규화 LUT을 만든다. lam=0이면 순수
    경험적 평균(빈 bin은 prior로 대체), lam이 크면 prior에 수렴."""
    lut = np.where(counts > 0, (sums + lam * prior) / (counts + lam), prior)
    lut = np.maximum.accumulate(lut)  # 단조 증가 보정
    return lut.astype(np.float32)
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `python3 -m unittest tests.test_calibrate -v`
Expected: PASS (Task 1의 5개 + 이번 9개 = 14개)

- [ ] **Step 5: 커밋**

```bash
git add tools/calibrate.py tests/test_calibrate.py
git commit -m "Replace _build_lut with counts/sums-based _build_lut_from_counts"
```

(주의: 이 시점에서 `run_regularize()`는 아직 옛 `_build_lut`를 호출하고
있어 깨진 상태다 - Task 3에서 바로 고친다. 커밋 전 `python3 -m
unittest discover -s tests`는 통과하지만(단위 테스트가 `run_regularize()`를
호출하지 않으므로), `python3 -m tools.calibrate regularize`를 지금
실행하면 `NameError`가 난다는 걸 다음 태스크 시작 전에 인지할 것.)

---

### Task 3: `_collect_pair_pixels()` 74쌍화 + `run_regularize()` 뺄셈 기반 LOO

**Files:**
- Modify: `tools/calibrate.py` (`_collect_pair_pixels()` 약 L340-370,
  `run_regularize()` 약 L383-421)
- Test: `tests/test_calibrate.py`

**Interfaces:**
- Consumes: `_resolve_pairs()`(Task 1, `generation` 필드 포함),
  `_pair_counts_sums`/`_build_lut_from_counts`(Task 2)
- Produces: `_collect_pair_pixels()`가 반환하는 각 dict에 `generation`
  키 추가(기존 `name/neutral_l/target_l/b2/w995/shadow_valid`는 유지).
  `run_regularize()`가 `dataset`(리스트)과 `per_fold_by_lambda`(dict:
  `lambda -> [(name, generation, sqrt_e), ...]`, 74개 원소)를 만드는
  구조로 바뀜 - Task 4/5가 `per_fold_by_lambda`를 그대로 소비한다.

- [ ] **Step 1: 실패하는 테스트 작성 (뺄셈 LOO == 재계산 LOO 불변조건)**

`tests/test_calibrate.py`에 추가 - 합성 소규모 데이터셋으로 "전체 합에서
빼는 방식"이 "매번 훈련 집합을 다시 합쳐서 계산하는 방식"과 bit-level로
같은 결과를 내는지 확인:

```python
class TestSubtractionLooMatchesRecompute(unittest.TestCase):
    def test_subtraction_equals_full_recompute(self):
        from tools.calibrate import _pair_counts_sums, _build_lut_from_counts

        rng = np.random.default_rng(42)
        pairs = []
        for _ in range(4):
            neutral_l = rng.integers(0, 256, size=30).astype(np.int64)
            target_l = neutral_l.astype(np.float64) + rng.normal(0, 5, size=30)
            counts, sums = _pair_counts_sums(neutral_l, target_l)
            pairs.append(dict(neutral_l=neutral_l, target_l=target_l,
                               counts=counts, sums=sums))

        prior = np.arange(256, dtype=np.float32)
        lam = 500

        counts_all = sum(p['counts'] for p in pairs)
        sums_all = sum(p['sums'] for p in pairs)

        for i, held_out in enumerate(pairs):
            # 뺄셈 방식
            train_counts_sub = counts_all - held_out['counts']
            train_sums_sub = sums_all - held_out['sums']
            lut_sub = _build_lut_from_counts(train_counts_sub, train_sums_sub, prior, lam)

            # 재계산 방식 (기존 방식 그대로 재현)
            train = [p for j, p in enumerate(pairs) if j != i]
            train_counts_full = sum(p['counts'] for p in train)
            train_sums_full = sum(p['sums'] for p in train)
            lut_full = _build_lut_from_counts(train_counts_full, train_sums_full, prior, lam)

            np.testing.assert_array_equal(lut_sub, lut_full)
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python3 -m unittest tests.test_calibrate.TestSubtractionLooMatchesRecompute -v`
Expected: 이 테스트는 `_pair_counts_sums`/`_build_lut_from_counts`가
이미 Task 2에서 만들어졌으므로 **이 시점에 이미 PASS해야 정상**(순수
수학적 동등성이라 새 프로덕션 코드가 필요 없음 - 이 테스트의 목적은
"뺄셈이 재계산과 같다"는 걸 `run_regularize()` 리팩토링 **전에** 문서화된
불변조건으로 고정해두는 것). PASS 확인되면 다음 스텝으로.

- [ ] **Step 3: `_collect_pair_pixels()`를 `_resolve_pairs()` 기반 74쌍으로 교체**

기존 `_collect_pair_pixels()` 전체를 아래로 교체:

```python
def _collect_pair_pixels():
    dataset = []
    for r in _resolve_pairs():
        raw_path = r['raw_path']
        jpeg_path = r['jpeg_path']
        if not (os.path.exists(raw_path) and os.path.exists(jpeg_path)):
            continue

        target = cv2.imread(jpeg_path)
        if target is None:
            continue
        target = _resize_to_max_dim(target, 1200)

        with rawpy.imread(raw_path) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                                   output_bps=8, gamma=(2.222, 4.5))
        neutral = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if neutral.shape[:2] != target.shape[:2]:
            neutral = cv2.resize(neutral, (target.shape[1], target.shape[0]), interpolation=cv2.INTER_AREA)

        n_l = cv2.cvtColor(neutral, cv2.COLOR_BGR2LAB)[:, :, 0].ravel()
        t_l = cv2.cvtColor(target, cv2.COLOR_BGR2LAB)[:, :, 0].ravel()
        t_stats = gray_stats(target)

        dataset.append(dict(name=r['filename'], neutral_l=n_l, target_l=t_l,
                             generation=r['generation'],
                             b2=t_stats['b2'], w995=t_stats['w995'],
                             shadow_valid=t_stats['dark_pct'] > 5))
        print(f"  {r['filename']} ({r['generation']}) - {n_l.size}px")
    return dataset
```

(바뀐 부분: `collect_pairs()` 직접 순회 + 수동 캐시 경로 조립 대신
`_resolve_pairs()`가 이미 다운로드/병합해준 `raw_path`/`jpeg_path`/
`generation`을 그대로 씀 - 74쌍 전부 커버.)

- [ ] **Step 4: `run_regularize()`를 뺄셈 기반으로 재작성**

```python
def run_regularize():
    dataset = _collect_pair_pixels()
    prior = _parametric_prior()
    print(f"\n{len(dataset)}장 로드 완료\n")

    for d in dataset:
        d['counts'], d['sums'] = _pair_counts_sums(d['neutral_l'], d['target_l'])

    counts_all = sum(d['counts'] for d in dataset)
    sums_all = sum(d['sums'] for d in dataset)

    lambdas = [0, 50, 200, 500, 1000, 2000, 5000, 20000, 1e9]

    print(f"{'lambda':>10s}  {'LOO RMSE':>10s}")
    results = []
    per_fold_by_lambda = {}
    for lam in lambdas:
        sq_err = 0.0
        n = 0
        per_fold = []
        for held_out in dataset:
            train_counts = counts_all - held_out['counts']
            train_sums = sums_all - held_out['sums']
            lut = _build_lut_from_counts(train_counts, train_sums, prior, lam)

            pred_l = lut[held_out['neutral_l'].astype(np.int32)]
            pred_stats = dict(b2=np.percentile(pred_l, 2), w995=np.percentile(pred_l, 99.5))

            e = (pred_stats['w995'] - held_out['w995']) ** 2
            if held_out['shadow_valid']:
                e += (pred_stats['b2'] - held_out['b2']) ** 2
            sq_err += e
            n += 1
            per_fold.append((held_out['name'], held_out['generation'], e ** 0.5))
        rmse = (sq_err / n) ** 0.5
        results.append((lam, rmse))
        per_fold_by_lambda[lam] = per_fold
        print(f"{lam:10.0f}  {rmse:10.2f}")

    best_lam, best_rmse = min(results, key=lambda t: t[1])
    print(f"\n최적 lambda={best_lam} (LOO RMSE={best_rmse:.2f})")

    # 최적 lambda로 전체 74쌍 사용해 최종 LUT 생성
    final_lut = _build_lut_from_counts(counts_all, sums_all, prior, best_lam)
    np.save("regularized_tone_lut.npy", np.clip(final_lut, 0, 255).astype(np.uint8))
    print("저장: regularized_tone_lut.npy")

    return per_fold_by_lambda, best_lam
```

(Task 4/5가 유의성 검정 + 세대별 분해를 이 함수 끝(LUT 저장 앞 또는
뒤)에 이어붙인다 - 지금은 반환값만 마련해서 독립적으로 테스트 가능하게
해둔다. 기존에는 반환값이 없었지만(`main()`에서 안 씀), 이 파일의
`if __name__ == "__main__":` 디스패치는 반환값을 무시하므로 하위
호환에 영향 없음.)

- [ ] **Step 5: 테스트 실행해서 전부 통과 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS (이 태스크는 새 단위 테스트를 추가하지 않음 -
`run_regularize()` 자체는 실제 RAW 파일이 있어야 돌아가서 단위
테스트 대상이 아니고, Task 1/2에서 이미 고정한 불변조건을 재사용)

- [ ] **Step 6: 커밋**

```bash
git add tools/calibrate.py
git commit -m "Rewrite run_regularize() as subtraction-based LOO over 74 pairs"
```

---

### Task 4: 유의성 검정 (부호검정 + 부트스트랩 CI + drop-one) 이식

**Files:**
- Modify: `tools/calibrate.py` (`run_regularize()` 끝부분)
- Test: `tests/test_calibrate.py`

**Interfaces:**
- Consumes: Task 3의 `per_fold_by_lambda: dict[float, list[(name, generation, sqrt_e)]]`
- Produces: `summarize(per_fold, n_bootstrap=20000, seed=0) -> dict`,
  `print_summary(s, label_a, label_b)`, `_sign_test_p(wins, losses) -> float`
  (전부 `tools/evaluate_hncs_blend.py`에서 그대로 복사 - 시그니처 동일).
  `run_regularize()`가 최적 λ vs λ=0, 최적 λ vs λ=1e9 비교를 출력하고
  반환값에 두 `summary` dict를 추가.

- [ ] **Step 1: 실패하는 테스트 작성 (하드코딩 회귀 테스트, 기존 evaluate_hncs_blend 테스트와 동일 패턴)**

`tests/test_calibrate.py`에 추가:

```python
class TestSignTestP(unittest.TestCase):
    def test_no_pairs_is_p_one(self):
        from tools.calibrate import _sign_test_p
        self.assertEqual(_sign_test_p(0, 0), 1.0)

    def test_even_split_is_p_one(self):
        from tools.calibrate import _sign_test_p
        self.assertAlmostEqual(_sign_test_p(5, 5), 1.0)

    def test_all_wins_is_significant(self):
        from tools.calibrate import _sign_test_p
        p = _sign_test_p(10, 0)
        self.assertLess(p, 0.05)


class TestSummarizeShape(unittest.TestCase):
    def test_returns_expected_keys(self):
        from tools.calibrate import summarize
        per_fold = [(f"pair{i}", 10.0, 9.0) for i in range(20)]
        s = summarize(per_fold)
        expected_keys = {
            "n", "mean_a", "mean_b", "mean_diff", "median_diff",
            "improvement_pct", "b_wins", "a_wins", "sd_diff", "sem_diff",
            "t_stat", "sign_test_p", "ci_diff", "ci_pct",
            "dropone_pct_min", "dropone_pct_max", "dropone_flips_sign",
            "inconclusive", "verdict",
        }
        self.assertEqual(set(s.keys()), expected_keys)
        self.assertEqual(s["n"], 20)
        self.assertAlmostEqual(s["mean_a"], 10.0)
        self.assertAlmostEqual(s["mean_b"], 9.0)

    def test_identical_values_is_inconclusive(self):
        from tools.calibrate import summarize
        per_fold = [(f"pair{i}", 10.0, 10.0) for i in range(20)]
        s = summarize(per_fold)
        self.assertTrue(s["inconclusive"])
        self.assertIn("판정 보류", s["verdict"])
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python3 -m unittest tests.test_calibrate -v`
Expected: FAIL - `ImportError: cannot import name '_sign_test_p'`

- [ ] **Step 3: `tools/calibrate.py`에 `_sign_test_p`/`summarize`/`print_summary` 복사 이식**

파일 상단 `import csv` 옆에 `import math` 추가:

```python
import csv
import math
import os
import sys
import urllib.request
```

`run_regularize()` 함수 **앞**에 (즉 Task 2/3에서 만든 헬퍼들 다음,
`run_regularize()` 정의 전) 추가 - `tools/evaluate_hncs_blend.py`의
코드를 그대로 복사하되 "ΔE (CIEDE2000...)" 표현만 이 파일의 실제
지표(percentile 기반 오차)에 맞게 "오차"로 바꿈:

```python
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
    개선폭/verdict는 value_b가 value_a보다 작을 때(=b가 더 좋음, 오차
    낮을수록 좋음) 양수가 되도록 정의한다."""
    a = np.array([row[1] for row in per_fold], dtype=np.float64)
    b = np.array([row[2] for row in per_fold], dtype=np.float64)
    n = len(per_fold)
    diff = a - b
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
    print(f"평균 {label_a} 오차(RMSE 기여값, n={s['n']}): {s['mean_a']:.3f}")
    print(f"평균 {label_b} 오차(RMSE 기여값, n={s['n']}): {s['mean_b']:.3f}")
    print(f"개선폭({label_b} 기준): {s['improvement_pct']:.1f}%")
    print(f"폴드 승패: {label_b} {s['b_wins']}승 {label_a} {s['a_wins']}패")
    print(f"페어드 차이({label_a}-{label_b}): 평균 {s['mean_diff']:+.3f} / 중앙값 "
          f"{s['median_diff']:+.3f} / 표준편차 {s['sd_diff']:.3f} "
          f"(t={s['t_stat']:.2f}, df={s['n'] - 1})")
    print(f"부호검정 양측 p = {s['sign_test_p']:.3f}")
    print(f"부트스트랩 95% CI - 평균 오차 차이: "
          f"[{s['ci_diff'][0]:+.3f}, {s['ci_diff'][1]:+.3f}] / "
          f"개선폭: [{s['ci_pct'][0]:+.1f}%, {s['ci_pct'][1]:+.1f}%]")
    print(f"drop-one 민감도: 한 쌍을 빼면 개선폭이 "
          f"{s['dropone_pct_min']:.1f}% ~ {s['dropone_pct_max']:.1f}% 사이로 움직인다"
          + (" (부호가 뒤집힌다)" if s["dropone_flips_sign"] else ""))
    print(f"판정: {s['verdict']}")
```

- [ ] **Step 4: `run_regularize()`에 유의성 검정 호출 추가**

`run_regularize()`의 `best_lam, best_rmse = min(...)` 출력 다음,
`final_lut` 생성 앞에 삽입:

```python
    # --- 유의성 검정: 최적 lambda vs λ=0(v12) / λ=1e9(v11) ---
    best_fold = per_fold_by_lambda[best_lam]
    summaries = {}
    for baseline_lam, label in [(0, "v12(학습LUT)"), (1e9, "v11(파라메트릭)")]:
        if baseline_lam == best_lam:
            print(f"\n최적 lambda가 {label}과 동일 - 비교 생략")
            continue
        baseline_fold = per_fold_by_lambda[baseline_lam]
        paired = [(best_name, base_e, best_e)
                  for (best_name, _, best_e), (_, _, base_e)
                  in zip(best_fold, baseline_fold)]
        summary = summarize(paired)
        summaries[label] = summary
        print(f"\n=== 최적 하이브리드(λ={best_lam}) vs {label} ===")
        print_summary(summary, label_a=label, label_b=f"하이브리드(λ={best_lam})")
```

그리고 함수 마지막의 `return per_fold_by_lambda, best_lam`을
`return per_fold_by_lambda, best_lam, summaries`로 바꾼다.

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add tools/calibrate.py tests/test_calibrate.py
git commit -m "Add sign-test/bootstrap-CI/drop-one significance testing to regularize mode"
```

---

### Task 5: 세대별 오차 분해 표 출력

**Files:**
- Modify: `tools/calibrate.py` (`run_regularize()` 끝부분)
- Test: `tests/test_calibrate.py`

**Interfaces:**
- Consumes: Task 3의 `per_fold_by_lambda`(각 원소가 `(name, generation, sqrt_e)`)
- Produces: `_generation_breakdown(fold: list[(str, str, float)]) -> list[(str, int, float)]`
  (generation, n, rmse 튜플 리스트, generation 알파벳/가나다 순 정렬).
  `run_regularize()`가 최적 λ 기준으로 이 표를 출력.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
class TestGenerationBreakdown(unittest.TestCase):
    def test_groups_and_computes_rmse(self):
        from tools.calibrate import _generation_breakdown
        fold = [
            ("a", "X1D", 3.0),
            ("b", "X1D", 5.0),
            ("c", "X2D 100C", 4.0),
        ]
        result = _generation_breakdown(fold)
        by_gen = {gen: (n, rmse) for gen, n, rmse in result}
        self.assertEqual(by_gen["X1D"][0], 2)
        self.assertAlmostEqual(by_gen["X1D"][1], (3.0 ** 2 + 5.0 ** 2) ** 0.5 / (2 ** 0.5))
        self.assertEqual(by_gen["X2D 100C"][0], 1)
        self.assertAlmostEqual(by_gen["X2D 100C"][1], 4.0)

    def test_sorted_by_generation_name(self):
        from tools.calibrate import _generation_breakdown
        fold = [("a", "X2D 100C", 1.0), ("b", "CFV 100C/907X", 1.0)]
        result = _generation_breakdown(fold)
        gens = [gen for gen, _, _ in result]
        self.assertEqual(gens, sorted(gens))
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `python3 -m unittest tests.test_calibrate -v`
Expected: FAIL - `ImportError: cannot import name '_generation_breakdown'`

- [ ] **Step 3: `tools/calibrate.py`에 `_generation_breakdown` 추가**

`print_summary` 함수 다음, `run_regularize()` 함수 앞에 추가:

```python
def _generation_breakdown(fold):
    """(name, generation, sqrt_e) 리스트를 generation별로 묶어
    (generation, n, rmse) 리스트로 반환 - generation 이름 순 정렬."""
    by_gen = {}
    for _, gen, sqrt_e in fold:
        by_gen.setdefault(gen, []).append(sqrt_e)
    result = []
    for gen in sorted(by_gen):
        errs = by_gen[gen]
        rmse = (sum(e ** 2 for e in errs) / len(errs)) ** 0.5
        result.append((gen, len(errs), rmse))
    return result
```

- [ ] **Step 4: `run_regularize()`에 세대별 분해 출력 추가**

유의성 검정 블록 다음, `final_lut` 생성 앞에 삽입:

```python
    print(f"\n=== 세대별 오차 분해 (λ={best_lam}) ===")
    print(f"{'세대':20s} {'n':>4s}  {'하이브리드 RMSE':>14s}")
    for gen, n_gen, rmse_gen in _generation_breakdown(best_fold):
        print(f"{gen:20s} {n_gen:4d}  {rmse_gen:14.2f}")
```

- [ ] **Step 5: 테스트 실행해서 통과 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add tools/calibrate.py tests/test_calibrate.py
git commit -m "Add per-generation RMSE breakdown to regularize mode output"
```

---

### Task 6: 실제 74쌍 실행 + 결과 기록 (코드 태스크 아님 - 실행/문서화)

**Files:**
- Run: `tools/calibrate.py` (`regularize` 모드)
- Modify: `brands/hasselblad_learned.py` (docstring)
- Modify: `docs/measurements.md`, `docs/measurements.en.md`

**Interfaces:**
- Consumes: Task 1-5의 완성된 `run_regularize()`
- Produces: 없음 (최종 태스크) - `EVALUATION.md` 스타일이 아니라
  `brands/CLAUDE.md`/`docs/CLAUDE.md` 컨벤션(docstring append, 새 표
  추가)으로 결과를 남긴다.

- [ ] **Step 1: 백그라운드로 실행**

`tools/CLAUDE.md`의 "Long runs" 컨벤션 그대로:

```bash
nohup python3 -m tools.calibrate regularize > /tmp/calibrate_regularize_74pair.log 2>&1 &
```

`Monitor`로 `ΔE=|판정:|lambda|Traceback|Error|Killed|OOM` 패턴 감시
(이 파일은 ΔE를 안 쓰지만 필터에 넣어도 무해 - 실제로 찍히는 신호는
`lambda`/`판정:`/`저장:`).

뺄셈 기반 LOO라 9 lambda x 74폴드가 O(256) 연산이라 병렬화 없이도
수 초~수 분 안에 끝날 것으로 예상(Task 3 설계 근거) - 만약 실측이
예상과 크게 다르면(예: RAW 디코드 자체가 병목이라 여전히 오래 걸리면)
그 사실을 그대로 보고할 것, 예상과 다르다고 조용히 넘어가지 않는다.

- [ ] **Step 2: 결과 검증**

로그에서 확인할 것:
- 9개 lambda 전부의 LOO RMSE
- 최적 lambda
- 최적 λ vs λ=0, 최적 λ vs λ=1e9 각각의 `print_summary` 전체 출력
  (평균/개선폭/부호검정 p/부트스트랩 CI/drop-one/판정)
- 세대별 오차 분해 표(5행: CFV 100C/907X, X2D 100C, 공식 샘플(X1D
  계열), X1D II 50C, X1D)
- 에러 없이 74쌍 전부 로드됐는지("74장 로드 완료" 출력 확인)

- [ ] **Step 3: `brands/hasselblad_learned.py` docstring에 날짜 붙여 기록**

기존 "실험 기록 (음성 결과): v12 LUT이 raw+jpeg 10장뿐이라..." 문단
**바로 다음**(다른 기존 문단은 그대로 두고) 새 문단 삽입:

```
**하이브리드 재검증(2026-08, local-mixed-2026-07 74쌍/4세대)**: 위
정규화 실험(X1D 10장, lambda=0 최적)을 74쌍으로 재실행. [실제 로그의
9개 lambda RMSE 표, 최적 lambda, 최적 λ vs λ=0/λ=1e9 유의성 검정
결과(부호검정 p, 부트스트랩 CI, 판정)를 verbatim으로 기록]. 세대별
분해: [세대별 RMSE 표]. `tools/calibrate.py`의 `_pair_counts_sums`/
`_build_lut_from_counts`(뺄셈 기반 LOO)로 재현 가능:
`python3 -m tools.calibrate regularize`.
```

(위 텍스트의 대괄호 부분은 Step 1의 실제 실행 결과 숫자로 채운다 -
숫자를 지어내지 않는다.)

- [ ] **Step 4: `docs/measurements.md` 세대별 표 아래에 하이브리드 열 추가**

"로컬 기여 데이터셋으로 세대 간 pooling 첫 실측" 절의 기존 표
(파라메트릭/학습LUT 2열)는 그대로 두고, 그 표 바로 다음에 새 문단 +
표 추가:

```
**하이브리드(regularize) 재검증(2026-08)**: 위 두 버전(v11/v12) 재검증과
같은 74쌍으로 `tools/calibrate.py regularize` 모드(v11↔v12 ridge
하이브리드)도 재실행. 최적 lambda=[값], LOO RMSE=[값] - [파라메트릭/
학습LUT 대비 유의성 검정 결과 요약, 판정 그대로 인용].

| 카메라 | n | 하이브리드(λ=[값]) RMSE |
|---|---|---|
| [Step 2에서 얻은 실제 세대별 표] |
```

- [ ] **Step 5: `docs/measurements.en.md`에 대응 영문 문단 추가**

Step 4와 동일 내용을 영어로. "First real cross-generation pooling
test via a local contributed dataset" 절의 기존 표 다음에 삽입.

- [ ] **Step 6: 커밋**

```bash
git add brands/hasselblad_learned.py docs/measurements.md docs/measurements.en.md
git commit -m "Record 74-pair hybrid (v11/v12 regularize) re-run results"
```

## 다음 단계 (이 플랜 밖)

- 하이브리드가 유의미하게 이기면 `apply_hncs()` 기본값 교체는 별도
  논의(스펙의 "다음 단계" 참고).
- 세대별 개별 LUT 학습은 표본 부족으로 이 플랜 밖.
