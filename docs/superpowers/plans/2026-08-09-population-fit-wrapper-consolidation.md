# Population-Fit Brand Wrapper Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the byte-for-byte-identical `apply_*_look()` wrapper
function in 12 `brands/*.py` files into one shared factory in
`core/engine.py`, with zero output change, verified byte-for-byte.

**Architecture:** Add `make_population_fit_look(toe_lift, shoulder_start,
white_point, clahe_clip)` to `core/engine.py`, returning a real `def`
closure (not `functools.partial`) so `inspect.signature()` keeps working
identically for the two existing consumers that read these defaults at
runtime. Capture a golden byte-hash safety net against the *current*
(pre-refactor) output of all 12 brands before touching any brand file,
then do the 12-file swap in one commit and confirm the golden hashes are
unchanged.

**Tech Stack:** Python, `unittest`, `numpy`, `inspect`, `hashlib` (stdlib).

## Global Constraints

- This touches shipped `apply_*` functions in `brands/*.py`, which root
  `CLAUDE.md`'s "## Never" section forbids modifying without the user's
  explicit, in-the-moment sign-off. That sign-off was given for exactly
  this change (see
  `docs/superpowers/specs/2026-08-09-population-fit-wrapper-consolidation-design.md`'s
  "Governing exception" section) — do not extend this exception to any
  other shipped function.
- Zero behavior change. Every brand's photo-mode output for a given
  input must be byte-identical before and after.
- `hybrid_engine/core/preset_inverse.py`'s `curve_params()` and
  `tools/video_engine.py`'s `brand_video_params()` both call
  `inspect.signature(func).parameters["toe_lift"].default` (also
  `shoulder_start`, `white_point`) on these exact functions — the
  factory's returned callable must be a real function with those three
  parameter names and correct per-brand defaults, not a generic
  `*args, **kwargs` wrapper.
- `python3 -m unittest discover -s tests` must stay green (excluding the
  pre-existing, unrelated `torch`-import errors already present in this
  sandbox before this plan).
- Do not touch `brands/hasselblad*.py` or any brand file that does not
  already delegate to `core.engine.apply_population_fit_look`.

---

### Task 1: Add `make_population_fit_look()` to `core/engine.py`

**Files:**
- Modify: `core/engine.py` (add new function after `apply_population_fit_look`,
  before `apply_population_fit_look_video_frame`)
- Modify: `tests/test_engine.py` (add new test class)

**Interfaces:**
- Consumes: `apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)`
  (already defined in `core/engine.py`).
- Produces: `make_population_fit_look(toe_lift, shoulder_start, white_point, clahe_clip)`
  — a function that returns a callable `apply(img_bgr, toe_lift=<bound>,
  shoulder_start=<bound>, white_point=<bound>, clahe_clip=<bound>)`. Task 3
  imports and calls this from all 12 brand files.

- [ ] **Step 1: Write the failing tests**

Open `tests/test_engine.py`. Change the import line (currently line 7)
from:

```python
from core.engine import apply_population_fit_look, apply_population_fit_look_video_frame
```

to:

```python
from core.engine import (
    apply_population_fit_look, apply_population_fit_look_video_frame,
    make_population_fit_look,
)
```

Then insert this new test class immediately before the final
`if __name__ == "__main__":` line:

```python
class TestMakePopulationFitLook(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_matches_direct_call_with_same_args(self):
        fn = make_population_fit_look(toe_lift=10 / 255, shoulder_start=0.78,
                                       white_point=230 / 255, clahe_clip=1.25)
        direct = apply_population_fit_look(self.img, toe_lift=10 / 255, shoulder_start=0.78,
                                            white_point=230 / 255, clahe_clip=1.25)
        via_factory = fn(self.img)
        np.testing.assert_array_equal(direct, via_factory)

    def test_signature_exposes_bound_defaults(self):
        import inspect
        fn = make_population_fit_look(toe_lift=10 / 255, shoulder_start=0.78,
                                       white_point=230 / 255, clahe_clip=1.25)
        sig = inspect.signature(fn)
        self.assertAlmostEqual(sig.parameters["toe_lift"].default, 10 / 255)
        self.assertAlmostEqual(sig.parameters["shoulder_start"].default, 0.78)
        self.assertAlmostEqual(sig.parameters["white_point"].default, 230 / 255)
        self.assertAlmostEqual(sig.parameters["clahe_clip"].default, 1.25)

    def test_caller_can_override_bound_defaults(self):
        fn = make_population_fit_look(toe_lift=10 / 255, shoulder_start=0.78,
                                       white_point=230 / 255, clahe_clip=1.25)
        default_out = fn(self.img)
        overridden_out = fn(self.img, toe_lift=20 / 255)
        self.assertFalse(np.array_equal(default_out, overridden_out))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_engine -v`
Expected: FAIL — `ImportError: cannot import name 'make_population_fit_look' from 'core.engine'`

- [ ] **Step 3: Implement `make_population_fit_look()`**

In `core/engine.py`, add this function immediately after
`apply_population_fit_look` and before `apply_population_fit_look_video_frame`:

```python
def make_population_fit_look(toe_lift, shoulder_start, white_point, clahe_clip):
    """apply_population_fit_look()에 브랜드별 상수를 고정한 apply_*_look()
    함수를 만들어 반환한다. functools.partial이 아니라 진짜 def 클로저를
    쓰는 이유: hybrid_engine/core/preset_inverse.py와 tools/video_engine.py가
    inspect.signature(func).parameters["toe_lift"].default 형태로 이
    함수의 기본값을 직접 읽어가므로(브랜드 상수를 이중 기록하지 않기
    위해), 그 두 소비자가 지금과 동일하게 동작하려면 실제 함수
    시그니처(파라미터명+기본값)가 그대로 보존돼야 한다."""
    def apply(img_bgr, toe_lift=toe_lift, shoulder_start=shoulder_start,
              white_point=white_point, clahe_clip=clahe_clip):
        return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
    return apply
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_engine -v`
Expected: all tests PASS, including the 3 new ones.

- [ ] **Step 5: Commit**

```bash
git add core/engine.py tests/test_engine.py
git commit -m "Add make_population_fit_look() factory to core/engine.py"
```

---

### Task 2: Capture golden byte-identical baseline for all 12 brands

**Files:**
- Create: `tests/test_population_fit_look_golden.py`

**Interfaces:**
- Consumes: the 12 brand modules' current `apply_*_look()` functions
  (unchanged in this task — this task only adds a test, no production
  code changes).
- Produces: a passing regression test that Task 3 re-runs unchanged to
  prove the refactor didn't alter any brand's output.

- [ ] **Step 1: Create `tests/test_population_fit_look_golden.py`**

```python
"""population-fit 브랜드 12개의 apply_*_look() 출력이 core/engine.py
리팩토링(docs/superpowers/plans/2026-08-09-population-fit-wrapper-consolidation.md)
전후로 완전히 동일한지 확인하는 골든 회귀 테스트. 해시는 리팩토링 전
실제 코드를 돌려서 뽑은 값 그대로다 - 값 자체가 맞는지는 검증하지
않는다(그건 각 브랜드 docstring의 population 수치가 담당), 오직
"이 리팩토링이 픽셀 출력을 하나도 안 바꿨는지"만 확인한다."""
import hashlib
import importlib
import unittest

import numpy as np

# tests/test_brands.py의 make_test_image()와 동일한 시드/shape
def make_test_image():
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)


# (모듈 경로, 함수명, 리팩토링 전 sha256(출력.tobytes()))
GOLDEN_HASHES = [
    ("brands.canon", "apply_canon_look",
     "a2d38d6afbdae1926632f46c92685845a40d40ed0baa2f05eb3e70eee5b31fa9"),
    ("brands.leica", "apply_leica_look",
     "670068f031446c463196e409d99560b6fd972e56b8049f988b371fe8c9fd9ec0"),
    ("brands.leica_raw", "apply_leica_raw_look",
     "d49fc298c2f78c3631b746c27a3f4f3b981ea144270e17ee2707e95e2bc85fd7"),
    ("brands.nikon", "apply_nikon_look",
     "c47edaf79ecafd047b473ad44375044180475284527dfa0b87a643c604125c95"),
    ("brands.olympus", "apply_olympus_look",
     "249ad1c40a8686430edb3584ce348afe9b73ab8ff9db4b02d8d1e89ae30b0a25"),
    ("brands.panasonic", "apply_panasonic_look",
     "2a727377610358b323216ec632c5b540fb0a2f7b7f961d46dbc02b8b5afb69f3"),
    ("brands.pentax", "apply_pentax_look",
     "37f649f1725fe0e0b8ee58523b200e61314ad07b991aabf08d1dda7f12cd2c3d"),
    ("brands.phaseone", "apply_phaseone_look",
     "bdfbea26b312321e3dcc46ce17529b67da5cdec0430d27a610128087681062c1"),
    ("brands.ricoh_gr", "apply_ricoh_gr_look",
     "9239b981fe5a363d22c091d47bb3a2073bc88c85f341c01ba3b969722ff8e1d0"),
    ("brands.sigma", "apply_sigma_look",
     "2544e61c01ec5c741168bda8506657711eda51a0c616e002f65d5b3a1bc1a5eb"),
    ("brands.sony", "apply_sony_look",
     "49ee7af2612f66aac66433c1e695cd32864b24cae1b542154a9edada379c3be9"),
    ("brands.sony_a7v", "apply_sony_a7v_look",
     "0bb0bb82d4f1636dee43ffb4c64a98e26f639ff0292e2be51687d483c190d104"),
]


class TestPopulationFitLookGoldenHashes(unittest.TestCase):
    def test_all_12_brands_match_pre_refactor_output(self):
        img = make_test_image()
        for mod_name, fn_name, expected_hash in GOLDEN_HASHES:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                actual_hash = hashlib.sha256(out.tobytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash,
                                  f"{mod_name}.{fn_name} output changed - "
                                  f"expected sha256={expected_hash}, got {actual_hash}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify every hash matches *today's*
  (pre-refactor) code**

Run: `python3 -m unittest tests.test_population_fit_look_golden -v`
Expected: PASS — `test_all_12_brands_match_pre_refactor_output ... ok`.
This confirms the hardcoded hashes above are correct for the current
(unmodified) `brands/*.py` before Task 3 touches anything. If any hash
mismatches here, stop — the hash in this plan was transcribed wrong, fix
it before proceeding to Task 3.

- [ ] **Step 3: Commit**

```bash
git add tests/test_population_fit_look_golden.py
git commit -m "Add golden byte-hash regression test for 12 population-fit brand outputs"
```

---

### Task 3: Refactor all 12 brand files to use `make_population_fit_look()`

**Files:**
- Modify: `brands/canon.py`, `brands/leica.py`, `brands/leica_raw.py`,
  `brands/nikon.py`, `brands/olympus.py`, `brands/panasonic.py`,
  `brands/pentax.py`, `brands/phaseone.py`, `brands/ricoh_gr.py`,
  `brands/sigma.py`, `brands/sony.py`, `brands/sony_a7v.py`

**Interfaces:**
- Consumes: `make_population_fit_look(toe_lift, shoulder_start,
  white_point, clahe_clip)` from Task 1 (`core/engine.py`).
- Produces: nothing new consumed by later tasks — this is the last task
  in this plan. The 12 `apply_*_look` names, signatures, and behavior
  must be identical to before (verified by Task 2's golden test and the
  existing `tests/test_brands.py`/`tests/test_video_engine.py` suites).

Each brand file gets the same two-part edit: change the import, and
collapse the 3-line `def` into one assignment. Do all 12 in this single
task/commit (they're mechanically identical and reviewing them
separately would add no value).

- [ ] **Step 1: `brands/canon.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 15.0 / 255
_WHITE_POINT = 239.1 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_canon_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 15.0 / 255
_WHITE_POINT = 239.1 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_canon_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 2: `brands/leica.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 9.2 / 255
_WHITE_POINT = 229.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_leica_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 9.2 / 255
_WHITE_POINT = 229.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_leica_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 3: `brands/leica_raw.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 0.0
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증


def apply_leica_raw_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                          white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 0.0
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증

apply_leica_raw_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 4: `brands/nikon.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 13.7 / 255
_WHITE_POINT = 237.3 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_nikon_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 13.7 / 255
_WHITE_POINT = 237.3 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_nikon_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 5: `brands/olympus.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 14.5 / 255
_WHITE_POINT = 232.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_olympus_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                        white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 14.5 / 255
_WHITE_POINT = 232.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_olympus_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 6: `brands/panasonic.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 13.4 / 255
_WHITE_POINT = 223.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_panasonic_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                          white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 13.4 / 255
_WHITE_POINT = 223.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_panasonic_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 7: `brands/pentax.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 11.2 / 255
_WHITE_POINT = 237.3 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_pentax_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                       white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 11.2 / 255
_WHITE_POINT = 237.3 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_pentax_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 8: `brands/phaseone.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 12.8 / 255
_WHITE_POINT = 226.5 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_phaseone_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 12.8 / 255
_WHITE_POINT = 226.5 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_phaseone_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 9: `brands/ricoh_gr.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 8.4 / 255
_WHITE_POINT = 245.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_ricoh_gr_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 8.4 / 255
_WHITE_POINT = 245.2 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_ricoh_gr_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 10: `brands/sigma.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 9.3 / 255
_WHITE_POINT = 228.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_sigma_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 9.3 / 255
_WHITE_POINT = 228.8 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_sigma_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 11: `brands/sony.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 9.1 / 255
_WHITE_POINT = 228.6 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용


def apply_sony_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                     white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 9.1 / 255
_WHITE_POINT = 228.6 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_sony_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 12: `brands/sony_a7v.py`**

Change:
```python
from core.engine import apply_population_fit_look

_TOE_LIFT = 0.06
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증


def apply_sony_a7v_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                         white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```
to:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 0.06
_SHOULDER_START = 0.82
_WHITE_POINT = 1.0
_CLAHE_CLIP = 1.25  # population-fit 값 차용, 미검증

apply_sony_a7v_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

- [ ] **Step 13: Run the golden regression test**

Run: `python3 -m unittest tests.test_population_fit_look_golden -v`
Expected: PASS — all 12 hashes still match, proving the refactor changed
zero pixels.

- [ ] **Step 14: Run the brand and video-engine suites**

Run: `python3 -m unittest tests.test_brands tests.test_video_engine tests.test_engine -v`
Expected: PASS (same results as before this task — these suites already
covered all 12 functions' shape/dtype and the `inspect.signature()` path).

- [ ] **Step 15: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: same pass/fail counts as before this plan (the sandbox's
pre-existing `torch`-import errors are unrelated and expected).

- [ ] **Step 16: Commit**

```bash
git add brands/canon.py brands/leica.py brands/leica_raw.py brands/nikon.py \
        brands/olympus.py brands/panasonic.py brands/pentax.py brands/phaseone.py \
        brands/ricoh_gr.py brands/sigma.py brands/sony.py brands/sony_a7v.py
git commit -m "Collapse 12 population-fit brand wrappers to make_population_fit_look() calls"
```
