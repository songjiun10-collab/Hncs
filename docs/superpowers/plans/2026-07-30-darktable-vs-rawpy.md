# darktable vs rawpy RAW Decode Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine (honestly, with a noise-floor sanity check built in from the start) whether decoding RAW files via `darktable-cli` instead of `rawpy`/LibRaw reduces ΔE against the real camera JPEG, across all 16 real local raw+jpeg pairs (13 Hasselblad + 3 Fuji).

**Architecture:** Add a new standalone `decode_raw_darktable()` function (subprocess wrapper around `darktable-cli`) alongside the existing `decode_raw()` — never replacing it, since every existing calibrated matrix/curve in this project was fit against `decode_raw()`'s specific output. A comparison script then measures a repeat-decode noise floor first (lesson learned from two prior experiments that only found their own measurement noise after the fact), then runs the real 16-pair comparison, and records results honestly.

**Tech Stack:** Python 3, `subprocess` (already stdlib), `darktable-cli` 4.6.1 (system package, already installed via `apt-get install darktable` in this environment — NOT a Python dependency, must be documented in README), `cv2`/`numpy` (already dependencies), `colour-science` (via existing `hybrid_engine.utils.evaluate`), `unittest`.

## Global Constraints

- `hybrid_engine/utils/io.py`'s existing `decode_raw()` and `decode_raw_native()` must NEVER be modified — only a new function is added to the same file.
- `brands/hasselblad.py`'s `apply_hncs()` must NEVER be modified.
- `brands/fuji.py`'s existing `apply_*` preset functions must NEVER be modified.
- `hybrid_engine/assets/profiles/*.dcp`, `hybrid_engine/hasselblad.json`, and any other existing calibrated artifact must NOT be regenerated or touched by this plan — they were fit against `decode_raw()`'s rawpy-based output and stay that way regardless of this experiment's outcome.
- The `darktable-cli` invocation for `decode_raw_darktable()` MUST use exactly this flag combination, already verified by direct testing to produce output statistically comparable to `decode_raw()`'s pure-linear convention (without it, darktable applies filmic tone-mapping by default and the comparison is meaningless — confirmed by direct testing in the design spec):
  - `--icc-type LIN_REC709`
  - `--core --conf plugins/imageio/format/tiff/bpp=32`
  - `--conf plugins/darkroom/workflow=none`
- The comparison script must measure a repeat-decode noise floor (in ΔE units, not raw pixel units) BEFORE reporting any rawpy-vs-darktable conclusion, and must explicitly state whether the measured difference is larger or smaller than that noise floor — this is a direct, mandatory response to two prior experiments in this project (`docs/superpowers/specs/2026-07-28-hncs-structural-research-design.md`, `docs/superpowers/specs/2026-07-29-fuji-demosaic-algorithm-design.md`) whose original conclusions were later found to be statistical/measurement noise, discovered only after the fact.
- `OMP_NUM_THREADS=1` must be set in the comparison script's process environment (rawpy/LibRaw's X-Trans decode path is known to be non-deterministic when multithreaded — confirmed in the Fuji demosaic experiment).
- `darktable-cli` is a system package (`apt-get install darktable`), not installable via `requirements.txt` — this must be disclosed in `README.md` as a reproduction prerequisite for this specific experiment (not a general project dependency).

---

### Task 1: `decode_raw_darktable()` in `hybrid_engine/utils/io.py`

**Files:**
- Modify: `hybrid_engine/utils/io.py` (add new function + 2 new imports; do not touch `decode_raw()`/`decode_raw_native()`)
- Test: `tests/test_io_decode_raw_darktable.py`

**Interfaces:**
- Consumes: `subprocess`, `tempfile` (new imports needed), `cv2`, `numpy`, `os` (all already available in this file or stdlib).
- Produces: `decode_raw_darktable(raw_path)` → `np.ndarray`, float64, shape `(H, W, 3)`, RGB order, values clipped to `[0.0, ...)` (no upper clip). Task 2 imports and calls this directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_io_decode_raw_darktable.py`:

```python
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from hybrid_engine.utils.io import decode_raw_darktable


class TestDecodeRawDarktable(unittest.TestCase):
    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_calls_darktable_cli_with_required_flags(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = np.zeros((4, 4, 3), dtype=np.float32)

        decode_raw_darktable("fake.RAF")

        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertEqual(cmd[0], "darktable-cli")
        self.assertEqual(cmd[1], "fake.RAF")
        self.assertIn("--icc-type", cmd)
        self.assertIn("LIN_REC709", cmd)
        self.assertIn("plugins/imageio/format/tiff/bpp=32", cmd)
        self.assertIn("plugins/darkroom/workflow=none", cmd)

    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_on_nonzero_returncode(self, mock_run, mock_imread):
        mock_run.return_value = MagicMock(returncode=1, stderr="boom")

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")
        mock_imread.assert_not_called()

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=False)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_output_file_missing(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")
        mock_imread.assert_not_called()

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_raises_when_imread_returns_none(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = None

        with self.assertRaises(RuntimeError):
            decode_raw_darktable("fake.RAF")

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_negative_values_clipped_to_zero(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        mock_imread.return_value = np.array([[[-0.5, 0.2, 1.5]]], dtype=np.float32)

        result = decode_raw_darktable("fake.RAF")

        self.assertGreaterEqual(result.min(), 0.0)

    @patch("hybrid_engine.utils.io.os.path.exists", return_value=True)
    @patch("hybrid_engine.utils.io.cv2.imread")
    @patch("hybrid_engine.utils.io.subprocess.run")
    def test_bgr_converted_to_rgb(self, mock_run, mock_imread, mock_exists):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # cv2 reads BGR order: blue=1.0, green=0.5, red=0.1
        mock_imread.return_value = np.array([[[1.0, 0.5, 0.1]]], dtype=np.float32)

        result = decode_raw_darktable("fake.RAF")

        # RGB order expected: red=0.1, green=0.5, blue=1.0
        np.testing.assert_allclose(result[0, 0], [0.1, 0.5, 1.0], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_io_decode_raw_darktable -v`
Expected: FAIL with `ImportError: cannot import name 'decode_raw_darktable'`

- [ ] **Step 3: Add imports and the new function**

At the top of `hybrid_engine/utils/io.py`, add these two imports alongside the existing ones (`numpy`, `rawpy`, `cv2`, `colour`):

```python
import subprocess
import tempfile
```

Then append this new function to the end of `hybrid_engine/utils/io.py` (after `decode_raw_native()`, do not modify anything above it):

```python
def decode_raw_darktable(raw_path):
    """RAW -> Linear RGB, darktable-cli 경유(연구용 전용 -
    decode_raw()를 대체하지 않는다, tools/evaluate_darktable_vs_rawpy.py
    전용). float64 [0, ~) 범위, shape (H, W, 3), RGB 순서,
    decode_raw()와 같은 sRGB(Rec.709) 프라이머리 기준 선형광 값이지만
    데모자이크/카메라 매트릭스/화이트밸런스를 rawpy(LibRaw)가 아니라
    darktable이 계산한다는 점이 다르다.

    subprocess로 darktable-cli를 호출해 32비트 float TIFF로 export한다.
    --icc-type LIN_REC709(선형, Rec.709 프라이머리)와
    plugins/darkroom/workflow=none(filmic/노출 자동보정 끔 - 안 끄면
    darktable 기본값이 톤매핑까지 적용해서 decode_raw()와 비교
    불가능한 결과가 나온다, 직접 확인함)이 핵심이다. darktable 출력은
    음수를 클립하지 않으므로 읽어온 뒤 0으로 클립해서 decode_raw()와
    하한을 맞춘다.

    subprocess+임시파일 기반이라 decode_raw()보다 훨씬 느리다(파일당
    10초 이상) - 프로덕션 경로가 아니라
    tools/evaluate_darktable_vs_rawpy.py 전용이다."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "out.tif")
        result = subprocess.run(
            ["darktable-cli", raw_path, out_path,
             "--icc-type", "LIN_REC709", "--out-ext", "tif",
             "--core",
             "--conf", "plugins/imageio/format/tiff/bpp=32",
             "--conf", "plugins/darkroom/workflow=none"],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not os.path.exists(out_path):
            raise RuntimeError(
                f"darktable-cli failed for {raw_path}: {result.stderr}")
        bgr = cv2.imread(out_path, cv2.IMREAD_UNCHANGED)
        if bgr is None:
            raise RuntimeError(
                f"failed to read darktable-cli output for {raw_path}")
    rgb = bgr[:, :, ::-1].astype(np.float64)
    return np.clip(rgb, 0.0, None)
```

Note: `hybrid_engine/utils/io.py` does not currently import `os` at module scope for a bare `import os` — check the top of the file; if `os` is not already imported, add `import os` alongside the new `subprocess`/`tempfile` imports (it's needed for `os.path.join`/`os.path.exists`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_io_decode_raw_darktable -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (467 baseline + 6 new = 473)

- [ ] **Step 6: Manual smoke test against a real RAW file**

`darktable-cli` is already installed in this environment (`darktable 4.6.1`, confirmed via `darktable-cli --version`). Confirm the new function works end-to-end against a real file:

```bash
python3 -c "
from hybrid_engine.utils.io import decode_raw, decode_raw_darktable
rawpy_out = decode_raw('raw_calib_cache/00378.jpg.3FR')
dt_out = decode_raw_darktable('raw_calib_cache/00378.jpg.3FR')
print('rawpy  shape/dtype:', rawpy_out.shape, rawpy_out.dtype)
print('dt     shape/dtype:', dt_out.shape, dt_out.dtype)
print('rawpy  min/max/mean:', rawpy_out.min(), rawpy_out.max(), rawpy_out.mean())
print('dt     min/max/mean:', dt_out.min(), dt_out.max(), dt_out.mean())
"
```

Expected: both are float64 `(H, W, 3)` arrays with `min() == 0.0` (both clipped at 0), roughly similar order-of-magnitude mean (both should be well under 0.1 for this scene — a "pure linear, no tone curve" decode looks very dark by design, not like a viewable photo). If darktable's output instead looks bright (mean well above 0.1, closer to what a normal photo preview looks like), something is wrong with the flags and this step should not be marked done — go back and check `plugins/darkroom/workflow=none` took effect. Record the actual numbers in the task report.

- [ ] **Step 7: Commit**

```bash
git add hybrid_engine/utils/io.py tests/test_io_decode_raw_darktable.py
git commit -m "Add decode_raw_darktable(): darktable-cli-based RAW decode for research comparison"
```

---

### Task 2: `tools/evaluate_darktable_vs_rawpy.py` + real 16-pair comparison + record results

**Files:**
- Create: `tools/evaluate_darktable_vs_rawpy.py`
- Test: `tests/test_evaluate_darktable_vs_rawpy.py`
- Modify: `hybrid_engine/EVALUATION.md` (append new section)
- Modify: `README.md` (add darktable system-dependency note)

**Interfaces:**
- Consumes: Task 1's `decode_raw_darktable(raw_path)`. `hybrid_engine.utils.io.decode_raw(raw_path)` (unchanged, existing). `hybrid_engine.utils.evaluate.mean_delta_e(rgb_a_linear, rgb_b_linear, method="CIE 2000")` and `load_image_linear_for_evaluate(target_path, result_shape, resize_to_match=True)` (both unchanged, existing).
- Produces: `load_hasselblad_pairs()`, `load_fuji_pairs(manifest_path=FUJI_MANIFEST)`, `load_all_pairs()` (unit-tested, portable helpers — `load_fuji_pairs` accepts an override path so tests never touch the real git-ignored manifest). `check_determinism()`, `compare_pair()`, `run_comparison()`, `main()` (real-data-dependent, verified by actually running the script, matching this project's established precedent).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_evaluate_darktable_vs_rawpy.py`:

```python
import csv
import os
import tempfile
import unittest

from tools.evaluate_darktable_vs_rawpy import load_fuji_pairs

_FIELDS = ["camera", "datetime", "film_mode", "raw_path", "jpeg_path"]


class TestLoadFujiPairs(unittest.TestCase):
    def _write_manifest(self, rows):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def test_parses_camera_and_paths(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T3", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T3/raw/DSCF3954.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T3/jpeg/DSCF3954.jpg",
        }])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]["camera"], "Fujifilm X-T3")
        self.assertEqual(pairs[0]["name"], "DSCF3954.RAF")

    def test_paths_are_absolute(self):
        path = self._write_manifest([{
            "camera": "Fujifilm X-T30", "datetime": "t", "film_mode": "m",
            "raw_path": "raw_calib_cache_fuji/Fujifilm_X-T30/raw/DSCF7030.RAF",
            "jpeg_path": "raw_calib_cache_fuji/Fujifilm_X-T30/jpeg/DSCF7030.JPG",
        }])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertTrue(os.path.isabs(pairs[0]["raw_path"]))
        self.assertTrue(os.path.isabs(pairs[0]["jpeg_path"]))

    def test_multiple_rows_preserve_order(self):
        path = self._write_manifest([
            {"camera": "A", "datetime": "t1", "film_mode": "m1",
             "raw_path": "r1.RAF", "jpeg_path": "j1.jpg"},
            {"camera": "B", "datetime": "t2", "film_mode": "m2",
             "raw_path": "r2.RAF", "jpeg_path": "j2.jpg"},
        ])
        pairs = load_fuji_pairs(manifest_path=path)
        self.assertEqual([p["camera"] for p in pairs], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_evaluate_darktable_vs_rawpy -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.evaluate_darktable_vs_rawpy'`

- [ ] **Step 3: Write the implementation**

Create `tools/evaluate_darktable_vs_rawpy.py`:

```python
"""rawpy(decode_raw) vs darktable-cli(decode_raw_darktable) RAW 디코드
비교 - 핫셀블라드 13쌍 + Fuji 3쌍(총 16쌍) 실제 raw+jpeg 페어로 확인.
설계 근거: docs/superpowers/specs/2026-07-30-darktable-vs-rawpy-design.md

지난 두 실험(HNCS 구조 실험의 통계적 유의성 문제, Fuji 데모자이크의
멀티스레드 논디터미니즘)에서 배운 교훈으로, 실제 비교를 돌리기 전에
반복-디코드 노이즈 바닥을 ΔE 단위로 먼저 측정한다.

darktable-cli는 시스템 패키지(apt-get install darktable)로 설치돼야
한다 - requirements.txt로 안 잡히는 이 실험 전용 의존성이다.

  python3 -m tools.evaluate_darktable_vs_rawpy
"""
import csv
import glob
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hybrid_engine.utils.evaluate import load_image_linear_for_evaluate, mean_delta_e
from hybrid_engine.utils.io import decode_raw, decode_raw_darktable

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HASSELBLAD_CSV = os.path.join(_ROOT, "datasets", "hasselblad", "hasselblad_raw_jpeg_pairs.csv")
HASSELBLAD_CACHE_DIR = os.path.join(_ROOT, "raw_calib_cache")
FUJI_MANIFEST = os.path.join(_ROOT, "fuji_pairs_manifest.csv")


def _hasselblad_raw_path(jpeg_name):
    matches = [m for m in glob.glob(os.path.join(HASSELBLAD_CACHE_DIR, jpeg_name + ".*"))
               if not m.endswith(".target.jpg")]
    if len(matches) != 1:
        raise FileNotFoundError(f"raw for {jpeg_name}: expected 1 match, got {matches}")
    return matches[0]


def load_hasselblad_pairs():
    """datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv의 jpeg_url
    basename 13개를 raw_calib_cache/의 실제 raw+target 경로로 매핑."""
    pairs = []
    with open(HASSELBLAD_CSV, newline="") as f:
        for row in csv.DictReader(f):
            jpeg_name = os.path.basename(row["jpeg_url"])
            pairs.append({
                "camera": "Hasselblad",
                "name": jpeg_name,
                "raw_path": _hasselblad_raw_path(jpeg_name),
                "jpeg_path": os.path.join(HASSELBLAD_CACHE_DIR, jpeg_name + ".target.jpg"),
            })
    return pairs


def load_fuji_pairs(manifest_path=FUJI_MANIFEST):
    """manifest_path(csv, 컬럼: camera/datetime/film_mode/raw_path/
    jpeg_path)를 dict 리스트로 반환 - raw_path/jpeg_path는 리포 루트
    기준 상대경로를 절대경로로 바꿔서 반환한다."""
    pairs = []
    with open(manifest_path, newline="") as f:
        for row in csv.DictReader(f):
            pairs.append({
                "camera": row["camera"],
                "name": os.path.basename(row["raw_path"]),
                "raw_path": os.path.join(_ROOT, row["raw_path"]),
                "jpeg_path": os.path.join(_ROOT, row["jpeg_path"]),
            })
    return pairs


def load_all_pairs():
    return load_hasselblad_pairs() + load_fuji_pairs()


def check_determinism(pair):
    """같은 파일을 rawpy/darktable 각각 두 번 디코드해서 재현성
    노이즈 바닥을 ΔE(CIEDE2000) 단위로 잰다(두 디코드끼리 직접 비교,
    JPEG 타깃 없이) - 실제 비교(디코더 간 ΔE 차이)와 같은 단위라야
    "노이즈보다 큰가"를 판단할 수 있다."""
    rawpy_1 = decode_raw(pair["raw_path"])
    rawpy_2 = decode_raw(pair["raw_path"])
    rawpy_noise_de = mean_delta_e(rawpy_1, rawpy_2)

    dt_1 = decode_raw_darktable(pair["raw_path"])
    dt_2 = decode_raw_darktable(pair["raw_path"])
    dt_noise_de = mean_delta_e(dt_1, dt_2)

    print(f"  [{pair['name']}] rawpy 반복-디코드 ΔE={rawpy_noise_de:.6f}  "
          f"darktable 반복-디코드 ΔE={dt_noise_de:.6f}", flush=True)
    return rawpy_noise_de, dt_noise_de


def compare_pair(pair):
    """(rawpy ΔE, darktable ΔE) 반환 - 같은 카메라 JPEG 타깃 대비."""
    rawpy_linear = decode_raw(pair["raw_path"])
    dt_linear = decode_raw_darktable(pair["raw_path"])
    target_rawpy = load_image_linear_for_evaluate(pair["jpeg_path"], rawpy_linear.shape)
    target_dt = load_image_linear_for_evaluate(pair["jpeg_path"], dt_linear.shape)
    de_rawpy = mean_delta_e(rawpy_linear, target_rawpy)
    de_dt = mean_delta_e(dt_linear, target_dt)
    return de_rawpy, de_dt


def run_comparison():
    pairs = load_all_pairs()
    results = []
    for pair in pairs:
        de_rawpy, de_dt = compare_pair(pair)
        improved = de_dt < de_rawpy
        results.append((pair["camera"], pair["name"], de_rawpy, de_dt, improved))
        print(f"  [{pair['camera']}/{pair['name']}] rawpy ΔE={de_rawpy:.3f} "
              f"darktable ΔE={de_dt:.3f} "
              f"({'darktable 개선' if improved else 'rawpy가 더 나음'})", flush=True)
    return results


def main():
    print("반복-디코드 노이즈 바닥 측정 (ΔE CIEDE2000 단위, 대표 파일 각 1장):")
    hasselblad_pairs = load_hasselblad_pairs()
    fuji_pairs = load_fuji_pairs()
    noise_pairs = [check_determinism(hasselblad_pairs[0]), check_determinism(fuji_pairs[0])]
    max_noise_de = max(n for pair_noise in noise_pairs for n in pair_noise)
    print(f"측정된 최대 노이즈 바닥: ΔE {max_noise_de:.6f}")
    print()

    print("전체 16쌍 비교:")
    results = run_comparison()
    n_total = len(results)
    n_improved = sum(1 for *_, improved in results if improved)
    de_rawpy_mean = sum(r[2] for r in results) / n_total
    de_dt_mean = sum(r[3] for r in results) / n_total
    de_diff = de_rawpy_mean - de_dt_mean
    print()
    print(f"평균 rawpy ΔE (n={n_total}): {de_rawpy_mean:.3f}")
    print(f"평균 darktable ΔE (n={n_total}): {de_dt_mean:.3f}")
    print(f"평균 차이: {de_diff:.6f} (rawpy - darktable, 양수면 darktable이 더 정확)")
    print(f"darktable가 더 나은 페어: {n_improved}/{n_total}")
    print(f"측정된 노이즈 바닥(ΔE): {max_noise_de:.6f}")
    if abs(de_diff) < max_noise_de:
        print("판정: 평균 차이가 노이즈 바닥보다 작다 - 노이즈와 구분 불가")
    else:
        print("판정: 평균 차이가 노이즈 바닥보다 크다 - 노이즈로는 설명 안 되는 차이")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_evaluate_darktable_vs_rawpy -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (473 from Task 1 + 3 new = 476)

- [ ] **Step 6: Run the real comparison against all 16 pairs**

Run: `python3 -m tools.evaluate_darktable_vs_rawpy`

This will take several minutes (16 pairs × 2 decoders, plus the noise-floor check decodes 2 files × 2 decoders × 2 repeats — darktable-cli alone takes roughly 10-15 seconds per file). Capture the **full stdout output verbatim**: the noise-floor measurement lines, the per-pair comparison lines, and the final summary block (means, difference, win count, and the noise-floor judgment line). Do not paraphrase or round it — copy it exactly into the task report. This output is required input for Step 7.

- [ ] **Step 7: Record the results in `hybrid_engine/EVALUATION.md`**

Using Step 6's actual captured output, append this section to the end of `hybrid_engine/EVALUATION.md` (fill every `<...>` placeholder with the literal values from the real run — none may remain in the committed file):

```markdown

## darktable vs rawpy RAW 디코드 비교 (핫셀블라드 13쌍 + Fuji 3쌍)

**배경**: 직전 Fuji 데모자이크 실험에서 rawpy 안의 알고리즘 선택으로는
X-Trans 데모자이크를 바꿀 수 없다는 게 밝혀졌다(`hybrid_engine/EVALUATION.md`의
"Fuji X-Trans 데모자이크 알고리즘 비교" 절 참고). 이번 실험은 더 넓게,
RAW 디코드 프로그램 자체(rawpy/LibRaw vs darktable)를 바꿔서 비교한다 -
데모자이크뿐 아니라 카메라 매트릭스/화이트밸런스 계산까지 전부 다른
프로그램이 하는 차이. `decode_raw()`는 대체하지 않았다(기존 캘리브레이션
전부가 그 출력에 맞춰 피팅돼 있음) - `decode_raw_darktable()`이라는
별도 함수로만 비교했다. 설계 근거:
`docs/superpowers/specs/2026-07-30-darktable-vs-rawpy-design.md`.

**측정 방법**: darktable-cli를 `--icc-type LIN_REC709` +
`plugins/imageio/format/tiff/bpp=32` + `plugins/darkroom/workflow=none`
조합으로 호출해야 `decode_raw()`와 비교 가능한 순수 선형 출력이
나온다(기본 설정은 filmic 톤매핑이 걸려서 비교 불가 - 직접 확인함).
지난 두 실험에서 사후에야 측정 노이즈 문제를 발견했던 걸 반영해서,
이번엔 **실제 비교 전에 반복-디코드 노이즈 바닥을 ΔE 단위로 먼저
측정**했다.

**노이즈 바닥** (대표 파일 각 1장, 같은 파일 반복 디코드 간 ΔE):

측정된 최대 노이즈 바닥: <max_noise_de 값> ΔE

**결과** (핫셀블라드 13쌍 + Fuji 3쌍 = 16쌍, 같은 카메라 JPEG 타깃 대비
ΔE CIEDE2000):

| 방법 | 평균 ΔE (n=16) |
|---|---|
| `decode_raw()`(rawpy/LibRaw) | <de_rawpy_mean 값> |
| `decode_raw_darktable()`(darktable-cli) | <de_dt_mean 값> |

평균 차이: <de_diff 값> (rawpy - darktable, 양수면 darktable이 더 정확)
darktable가 더 나은 페어: <n_improved>/16

**판정**: <de_diff의 절댓값이 노이즈 바닥보다 작으면 "평균 차이가
노이즈 바닥(ΔE <max_noise_de 값>)보다 작다 - 노이즈와 구분 불가"를,
크면 "평균 차이가 노이즈 바닥보다 크다 - darktable이 [더 낫다/rawpy가
더 낫다] (근거: <de_diff 값>)"를 스크립트 출력 그대로 정직하게 기록>

**알려진 한계**:
- **핫셀블라드 13쌍 + Fuji 3쌍, 두 카메라 시스템뿐이다** - 다른
  브랜드/센서로 일반화되는지는 확인 안 됨.
- **darktable-cli의 `colorin`(카메라->작업색공간 변환) 로직이
  LibRaw의 매트릭스와 정확히 어떻게 다른지는 조사하지 않았다** -
  "각 프로그램의 기본 카메라 인식 로직"을 그대로 비교했을 뿐, 둘 중
  어느 쪽이 더 정확한 카메라 고유 매트릭스를 쓰는지 별도로 검증하지
  않았다.
- **`decode_raw_darktable()`은 subprocess+임시파일 기반이라 훨씬
  느리다**(파일당 10초 이상) - 이 실험이 유의미하게 나와도 그대로
  프로덕션에 쓸 수 있는 형태는 아니다.
- **`hasselblad.json`/DCP 프로파일 등 기존 캘리브레이션은 이 결과로
  재피팅하지 않았다** - darktable이 유의미하게 낫다고 나와도 그
  파이프라인 전환은 완전히 별도의 논의/작업이다.
- **darktable-cli는 시스템 패키지 의존성**(`apt-get install darktable`)
  이라 이 실험을 재현하려면 별도 설치가 필요하다 - `requirements.txt`
  로는 안 잡힌다.
```

- [ ] **Step 8: Add darktable dependency note to README.md**

In `README.md`, find the "## 설치" section (installation instructions, mentions `pip install -r requirements.txt`). Add one paragraph immediately after it:

```markdown

`tools/evaluate_darktable_vs_rawpy.py`(연구용 RAW 디코더 비교 실험)를
재현하려면 `darktable-cli`가 시스템에 설치돼 있어야 한다
(`apt-get install darktable` 또는 배포판에 맞는 방법 - Python
`requirements.txt`로는 안 잡히는 별도 시스템 패키지다). 이 프로젝트의
다른 어떤 기능도 darktable을 요구하지 않는다.
```

- [ ] **Step 9: Run the full test suite one more time**

Run: `python3 -m unittest discover -s tests`
Expected: all tests PASS (no code changed in Steps 7-8, but confirms the branch is still green before the final commit)

- [ ] **Step 10: Commit**

```bash
git add tools/evaluate_darktable_vs_rawpy.py tests/test_evaluate_darktable_vs_rawpy.py hybrid_engine/EVALUATION.md README.md
git commit -m "Add darktable vs rawpy RAW decode comparison (16 real pairs), record results"
```

---
