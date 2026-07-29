# Fuji X-Trans Demosaic Algorithm Comparison Implementation Plan

> **정정(2026-07-29, 최종 리뷰 이후)**: 이 플랜이 구현한 "기본 vs DHT"
> 비교는 X-Trans에서 두 조건이 코드 레벨에서 동일했던 것으로 밝혀졌다
> (LibRaw가 quality>2 알고리즘을 전부 Markesteijn으로 합침) - 코드
> 자체(Task 1의 `demosaic_algorithm` 파라미터)는 정상 동작하고 유효한
> 추가지만, Task 2가 검증하려던 가설은 이 경로로는 성립하지 않는다.
> 자세한 내용과 정정된 결론은
> `docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md`와
> `hybrid_engine/EVALUATION.md`의 해당 절 참고. 아래 태스크 내용은
> 실행 당시 그대로 남겨둔다(역사 기록).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine (with an honest, small-sample caveat) whether decoding Fuji X-Trans RAWs with `rawpy`'s DHT demosaic algorithm instead of its default reduces ΔE against the real camera JPEG, using the 3 real local raw+jpeg pairs already on disk.

**Architecture:** Add an optional `demosaic_algorithm` parameter to the existing `decode_raw()` utility (default `None` preserves current behavior for all 12 existing call sites), then a small standalone comparison script decodes each of the 3 pairs twice (default vs DHT) and measures ΔE (CIEDE2000) against the same camera JPEG target, reusing this project's existing evaluation helpers.

**Tech Stack:** Python 3, `rawpy` (already a dependency, `DemosaicAlgorithm.DHT` confirmed working in this environment), `colour-science` (via existing `hybrid_engine.utils.evaluate`), `unittest`.

## Global Constraints

- `brands/hasselblad.py`'s `apply_hncs()` must NEVER be modified.
- `brands/fuji.py`'s existing `apply_*` preset functions must NEVER be modified — this plan only touches the lower-level `decode_raw()` utility and a new standalone research script.
- `hybrid_engine/utils/io.py`'s `decode_raw_native()` must NOT be touched — out of scope (used for the unrelated DCP camera-native-matrix path).
- `decode_raw(path)` called with a single positional argument (all 12 existing call sites: `hybrid_engine/main.py`, `hybrid_engine/evaluation/fidelity.py`, `hybrid_engine/evaluation/cross_camera.py`, `hybrid_engine/calibrate_profile.py`, `hybrid_engine/utils/evaluate.py`, `tools/analyze_colorchecker_matrix.py`, `tools/evaluate_hncs_structural.py`, `tools/analyze_pixel_errors.py`, etc.) must see **zero behavior change** — the new parameter must default to `None` and only affect `raw.postprocess()`'s kwargs when explicitly set.
- `rawpy.DemosaicAlgorithm.AMAZE` is NOT usable in this environment (`Demosaic algorithm AMAZE requires GPL3 demosaic pack`, confirmed by direct testing) — only `DHT` is used in this plan.
- No new external programs (darktable-cli, RawTherapee-cli, etc.) are installed as part of this plan — out of scope, a possible future escalation only if this experiment's signal warrants it.
- The real comparison uses only 3 raw+jpeg pairs (`fuji_pairs_manifest.csv`, all Fujifilm X-T3/X-T30, all F0/Standard "Provia" film mode) — **do not run any significance test (t-test, sign test, bootstrap, etc.) on n=3.** Report only the raw per-pair numbers and whether the direction agrees across all 3 pairs. State explicitly that n=3 cannot support a statistical conclusion.
- `fuji_pairs_manifest.csv` and `raw_calib_cache_fuji/` are git-ignored (confirmed via `.gitignore`) — present on this container's local disk but not available in CI. Any committed automated test must NOT depend on their presence; use temp files / mocks instead, per this project's established convention for RAW-cache-dependent code (see `tools/analyze_camera_native_matrix.py`, which has no committed test file, and `tools/evaluate_hncs_structural.py`'s tests, which only cover CSV-parsing/portable helpers).

---

### Task 1: `decode_raw()` optional `demosaic_algorithm` parameter

**Files:**
- Modify: `hybrid_engine/utils/io.py:12-25` (the `decode_raw()` function)
- Test: `tests/test_io_decode_raw.py`

**Interfaces:**
- Consumes: nothing new (uses `rawpy` and `numpy`, already imported in `hybrid_engine/utils/io.py`).
- Produces: `decode_raw(raw_path, demosaic_algorithm=None)` — same return type as before (`np.ndarray`, float64, shape `(H, W, 3)`, RGB, [0, 1]-ish range). Task 2 imports this updated signature and passes `demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_io_decode_raw.py`:

```python
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import rawpy

from hybrid_engine.utils.io import decode_raw


def _mock_raw_context(shape=(4, 4, 3)):
    mock_raw = MagicMock()
    mock_raw.postprocess.return_value = np.zeros(shape, dtype=np.uint16)
    mock_raw.__enter__.return_value = mock_raw
    mock_raw.__exit__.return_value = False
    return mock_raw


class TestDecodeRawDemosaicParam(unittest.TestCase):
    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_default_none_omits_demosaic_algorithm_kwarg(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw")

        _, kwargs = mock_raw.postprocess.call_args
        self.assertNotIn("demosaic_algorithm", kwargs)

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_explicit_algorithm_is_passed_through(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw", demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)

        _, kwargs = mock_raw.postprocess.call_args
        self.assertEqual(kwargs["demosaic_algorithm"], rawpy.DemosaicAlgorithm.DHT)

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_other_kwargs_unchanged_by_new_parameter(self, mock_imread):
        mock_raw = _mock_raw_context()
        mock_imread.return_value = mock_raw

        decode_raw("fake.raw")

        _, kwargs = mock_raw.postprocess.call_args
        self.assertTrue(kwargs["use_camera_wb"])
        self.assertTrue(kwargs["no_auto_bright"])
        self.assertEqual(kwargs["output_bps"], 16)
        self.assertEqual(kwargs["output_color"], rawpy.ColorSpace.sRGB)
        self.assertEqual(kwargs["gamma"], (1, 1))

    @patch("hybrid_engine.utils.io.rawpy.imread")
    def test_return_value_still_normalized_to_unit_range(self, mock_imread):
        mock_raw = _mock_raw_context(shape=(2, 2, 3))
        mock_raw.postprocess.return_value = np.full((2, 2, 3), 65535, dtype=np.uint16)
        mock_imread.return_value = mock_raw

        result = decode_raw("fake.raw")

        self.assertEqual(result.dtype, np.float64)
        np.testing.assert_allclose(result, 1.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_io_decode_raw -v`
Expected: FAIL with `TypeError: decode_raw() got an unexpected keyword argument 'demosaic_algorithm'`

- [ ] **Step 3: Modify `decode_raw()`**

Replace `hybrid_engine/utils/io.py:12-25` (the current `decode_raw` function) with:

```python
def decode_raw(raw_path, demosaic_algorithm=None):
    """RAW -> Linear RGB, float64 [0, 1] 근방(하이라이트는 1을 넘을 수
    있음), shape (H, W, 3), RGB 순서. 카메라 고유 색공간이 아니라 sRGB
    프라이머리 기준 선형광(linear light) 값 - 이후 core/pipeline이
    이 프라이머리를 그대로 XYZ 변환 기준으로 쓴다.

    demosaic_algorithm: None(기본값)이면 rawpy 기본 데모자이크를 쓰고
    기존 호출부와 100% 동일하게 동작한다. rawpy.DemosaicAlgorithm 값을
    넘기면 raw.postprocess()에 그대로 전달된다(예: X-Trans용 DHT 비교
    실험 - tools/evaluate_fuji_demosaic.py 참고). AMAZE는 이 프로젝트가
    쓰는 LibRaw 빌드에 GPL3 데모자이크 팩이 없어 런타임 에러가 난다."""
    kwargs = dict(
        use_camera_wb=True,
        no_auto_bright=True,
        output_bps=16,
        output_color=rawpy.ColorSpace.sRGB,
        gamma=(1, 1),  # 순수 linear
    )
    if demosaic_algorithm is not None:
        kwargs["demosaic_algorithm"] = demosaic_algorithm
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(**kwargs)
    return rgb16.astype(np.float64) / 65535.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_io_decode_raw -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python3 -m unittest discover -s tests`
Expected: all existing tests still PASS (460 baseline + 4 new = 464), confirming the new optional parameter didn't change behavior for any of the 12 existing `decode_raw(path)` call sites.

- [ ] **Step 6: Manual smoke test against a real RAW file**

`hybrid_engine/utils/io.py` has no other automated tests (RAW-decode correctness is verified manually per this project's convention — see e.g. `tools/analyze_camera_native_matrix.py`, which has no test file). Confirm the new parameter works against a real file:

```bash
python3 -c "
from hybrid_engine.utils.io import decode_raw
import rawpy
default = decode_raw('raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF')
dht = decode_raw('raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF', demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)
print('shapes match:', default.shape == dht.shape)
print('identical:', (default == dht).all())
print('default range:', default.min(), default.max())
print('dht range:', dht.min(), dht.max())
"
```

Expected: shapes match, NOT identical (different demosaic should produce different pixel values), both in a sane [0, ~a few] range (no NaN/negative garbage). Record the actual output in the task report.

- [ ] **Step 7: Commit**

```bash
git add hybrid_engine/utils/io.py tests/test_io_decode_raw.py
git commit -m "Add optional demosaic_algorithm parameter to decode_raw()"
```

---

### Task 2: `tools/evaluate_fuji_demosaic.py` + real comparison + record results

**Files:**
- Create: `tools/evaluate_fuji_demosaic.py`
- Test: `tests/test_evaluate_fuji_demosaic.py`
- Modify: `hybrid_engine/EVALUATION.md` (append new section)

**Interfaces:**
- Consumes: Task 1's `decode_raw(raw_path, demosaic_algorithm=None)`. `hybrid_engine.utils.evaluate.mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000")` and `load_image_linear_for_evaluate(target_path, result_shape, resize_to_match=True)` (both already exist, signatures unchanged by this plan). `rawpy.DemosaicAlgorithm.DHT`.
- Produces: `load_pairs(manifest_path=MANIFEST_PATH)` (unit-tested, portable — accepts an override path so tests never touch the real git-ignored manifest). `compare_pair()`, `run_comparison()`, `main()` (real-data-dependent, verified by actually running the script, matching this project's established precedent — see `tools/evaluate_hncs_structural.py`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluate_fuji_demosaic.py`:

```python
import csv
import os
import tempfile
import unittest

from tools.evaluate_fuji_demosaic import load_pairs

_FIELDS = ["camera", "datetime", "film_mode", "raw_path", "jpeg_path"]


class TestLoadPairs(unittest.TestCase):
    def _write_manifest(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def test_parses_all_fields(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T3",
            "datetime": "2018:10:06 15:56:45",
            "film_mode": "F0/Standard (Provia)",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T3/jpeg/DSCF3954.jpg",
        }])
        pairs = load_pairs(manifest_path=path)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["camera"], "Fujifilm X-T3")
        self.assertEqual(pairs[0]["datetime"], "2018:10:06 15:56:45")
        self.assertEqual(pairs[0]["film_mode"], "F0/Standard (Provia)")

    def test_raw_and_jpeg_paths_are_absolute(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T30", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T30/jpeg/DSCF7030.JPG",
        }])
        pairs = load_pairs(manifest_path=path)
        self.assertTrue(os.path.isabs(pairs[0]["raw_path"]))
        self.assertTrue(os.path.isabs(pairs[0]["jpeg_path"]))
        self.assertTrue(pairs[0]["raw_path"].endswith(
            "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF"))

    def test_multiple_rows_preserve_csv_order(self):
        path = self._write_manifest([
            {"camera": "A", "datetime": "t1", "film_mode": "m1",
             "raw_path": "r1.RAF", "jpeg_path": "j1.jpg"},
            {"camera": "B", "datetime": "t2", "film_mode": "m2",
             "raw_path": "r2.RAF", "jpeg_path": "j2.jpg"},
        ])
        pairs = load_pairs(manifest_path=path)
        self.assertEqual([p["camera"] for p in pairs], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_evaluate_fuji_demosaic -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.evaluate_fuji_demosaic'`

- [ ] **Step 3: Write the implementation**

Create `tools/evaluate_fuji_demosaic.py`:

```python
"""Fuji X-Trans 데모자이크 알고리즘(rawpy 기본 vs DHT) ΔE 비교 - 로컬에
있는 실제 raw+jpeg 페어 3쌍(fuji_pairs_manifest.csv)으로 예비 신호만
확인한다. 표본이 3장뿐이라 통계적 결론은 내지 않는다(방향 일치 여부만
보고). 설계 근거:
docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md

  python3 -m tools.evaluate_fuji_demosaic
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rawpy

from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.io import decode_raw

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(_ROOT, "fuji_pairs_manifest.csv")


def load_pairs(manifest_path=MANIFEST_PATH):
    """manifest_path(csv, 컬럼: camera/datetime/film_mode/raw_path/
    jpeg_path)를 dict 리스트로 반환 - raw_path/jpeg_path는 리포 루트
    기준 상대경로를 절대경로로 바꿔서 반환한다."""
    pairs = []
    with open(manifest_path, newline="") as f:
        for row in csv.DictReader(f):
            pairs.append({
                "camera": row["camera"],
                "datetime": row["datetime"],
                "film_mode": row["film_mode"],
                "raw_path": os.path.join(_ROOT, row["raw_path"]),
                "jpeg_path": os.path.join(_ROOT, row["jpeg_path"]),
            })
    return pairs


def compare_pair(pair):
    """(기본 데모자이크 ΔE, DHT ΔE) 반환 - 같은 카메라 JPEG 타깃 대비.
    데모자이크 알고리즘을 바꿔도 출력 해상도는 동일하므로 타깃은
    한 번만 로드한다."""
    default_linear = decode_raw(pair["raw_path"])
    dht_linear = decode_raw(pair["raw_path"], demosaic_algorithm=rawpy.DemosaicAlgorithm.DHT)
    target = load_image_linear_for_evaluate(pair["jpeg_path"], default_linear.shape)
    de_default = mean_delta_e(default_linear, target)
    de_dht = mean_delta_e(dht_linear, target)
    return de_default, de_dht


def run_comparison():
    pairs = load_pairs()
    results = []
    for pair in pairs:
        de_default, de_dht = compare_pair(pair)
        improved = de_dht < de_default
        results.append((pair["camera"], de_default, de_dht, improved))
        print(f"  [{pair['camera']}] 기본 ΔE={de_default:.3f} DHT ΔE={de_dht:.3f} "
              f"({'DHT 개선' if improved else '기본이 더 나음'})", flush=True)
    return results


def main():
    results = run_comparison()
    n_improved = sum(1 for _, _, _, improved in results if improved)
    n_total = len(results)
    print()
    print(f"DHT가 더 나은 페어: {n_improved}/{n_total}")
    print("(표본이 작아 통계적 유의성 검정은 하지 않음 - 방향만 보고)")
    if n_improved == n_total:
        print("결론: 전 페어에서 DHT가 개선 - 방향 일치, 추가 표본으로 재검증 가치 있음")
    elif n_improved == 0:
        print("결론: 전 페어에서 기본이 더 나음 - DHT로 바꿀 근거 없음")
    else:
        print("결론: 방향이 엇갈림 - 표본 3장으로는 판단 불가")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_evaluate_fuji_demosaic -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (464 from Task 1 + 3 new = 467)

- [ ] **Step 6: Run the real comparison against the 3 local pairs**

Run: `python3 -m tools.evaluate_fuji_demosaic`

Capture the **full stdout output verbatim** (all 3 per-pair lines plus the summary block). This is required input for Step 7 — do not paraphrase or round it, copy it exactly into the task report.

- [ ] **Step 7: Record the results in `hybrid_engine/EVALUATION.md`**

Using Step 6's actual captured output, append this section to the end of `hybrid_engine/EVALUATION.md` (fill every `<...>` placeholder with the literal values from the real run — none may remain in the committed file):

```markdown

## Fuji X-Trans 데모자이크 알고리즘 비교: 기본 vs DHT

**배경**: `brands/fuji.py`는 raw 기반 캘리브레이션을 시도했다가 raw+jpeg
페어가 3쌍뿐이라(EXIF 촬영시각 일치 기준) population 비교로 전환한
이력이 있다(`brands/fuji.py` docstring 참고). 이번 실험은 raw 기반
캘리브레이션을 되살리려는 게 아니라 더 좁게, rawpy(LibRaw)의 기본
데모자이크가 Fuji X-Trans 센서에 최적이 아닐 수 있다는 가설만
확인한다 - 데모자이크 단계의 색 오차는 이후 어떤 매트릭스/커브
피팅으로도 못 되돌리기 때문에, raw 기반 경로를 재시도하기 전에
점검할 가치가 있는 지점. 설계 근거:
`docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md`.

`rawpy.DemosaicAlgorithm.AMAZE`(RawTherapee가 쓰는 알고리즘)는 이
프로젝트가 쓰는 LibRaw 빌드에 GPL3 데모자이크 팩이 없어 런타임
에러가 난다(실측 확인). 특허프리 대안인 DHT만 시도했다.

**결과** (로컬에 있는 실제 raw+jpeg 페어 3쌍, 전부 F0/Standard(Provia),
같은 카메라 JPEG 타깃 대비 ΔE CIEDE2000):

| 카메라 | 기본 ΔE | DHT ΔE | DHT가 나음? |
|---|---|---|---|
| <카메라1> | <기본ΔE1> | <DHTΔE1> | <예/아니오> |
| <카메라2> | <기본ΔE2> | <DHTΔE2> | <예/아니오> |
| <카메라3> | <기본ΔE3> | <DHTΔE3> | <예/아니오> |

DHT가 더 나은 페어: <N>/3

**판정**: <3/3이면 "방향 일치 - DHT가 일관되게 낫다, 추가 표본으로
재검증 가치 있음"을, 0/3이면 "방향 일치 - 기본이 일관되게 낫다, DHT로
바꿀 근거 없음"을, 엇갈리면 "방향 엇갈림 - 표본 3장으로는 판단 불가"를
그대로 정직하게 기록>

**알려진 한계**:
- **표본 3쌍, 전부 같은 필름모드(Provia)** - 통계적 결론을 낼 수 없는
  크기다. t-검정/부호검정/부트스트랩 같은 유의성 검정은 시도하지
  않았다(직전 HNCS 구조 실험에서 n=13조차 유의하지 않았던 걸 감안하면
  n=3은 애초에 시도할 이유가 없다) - 이 실험은 방향이 일관되는지만
  보는 예비 신호 확인이다.
- **AMaZE/Markesteijn(darktable) 등 다른 데모자이크는 시도하지
  않았다** - 이 환경에서 바로 쓸 수 있는 DHT만 비교했다. 더 강한 신호가
  필요하면 darktable-cli 등 외부 프로그램 도입을 별도로 검토해야
  한다(이 실험의 범위 밖).
- **`apply_hncs()`/`brands/fuji.py`의 실제 프리셋 함수는 이 실험과
  무관하다** - 이번 비교는 `decode_raw()`라는 하위 유틸리티 레벨
  비교일 뿐, 두 함수 다 이 결과로 바뀌지 않았다.
```

- [ ] **Step 8: Run the full test suite one more time**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (no code changed in this step, but confirms the branch is still green before the final commit)

- [ ] **Step 9: Commit**

```bash
git add tools/evaluate_fuji_demosaic.py tests/test_evaluate_fuji_demosaic.py hybrid_engine/EVALUATION.md
git commit -m "Add Fuji X-Trans demosaic (default vs DHT) comparison, record results"
```

---
