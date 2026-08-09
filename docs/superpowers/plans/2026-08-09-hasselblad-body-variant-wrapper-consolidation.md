# Hasselblad Single-Body Variant Wrapper Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the byte-for-byte-identical bodies of
`apply_hncs_x1d50c()` (`brands/hasselblad_x1d50c.py`) and
`apply_hncs_x2dii()` (`brands/hasselblad_x2dii.py`) into calls to one new
shared factory in `core/engine.py`, with zero output change, verified
byte-for-byte. `brands/hasselblad.py` itself is not touched by any task
in this plan.

**Architecture:** Add `make_hasselblad_body_look(toe_lift, shoulder_start,
white_point, clahe_clip, exposure_gamma)` to `core/engine.py`, returning
a real `def` closure (same style as sub-project 2's
`make_population_fit_look`, though no `inspect.signature()` consumer
currently reads these two functions — confirmed by repo-wide grep during
design). Extend the existing golden byte-hash test with 2 more entries,
captured against the *current* (pre-refactor) code, before touching
either brand file.

**Tech Stack:** Python, `unittest`, `numpy`, `cv2`, `hashlib` (stdlib for
the hash).

## Global Constraints

- This touches shipped `apply_*` functions, which root `CLAUDE.md`
  forbids modifying without the user's explicit, in-the-moment sign-off.
  That sign-off was given for exactly this change (see
  `docs/superpowers/specs/2026-08-09-hasselblad-body-variant-wrapper-consolidation-design.md`'s
  "Governing exception" section). Do not extend this exception to
  `brands/hasselblad.py`'s `apply_hncs()`/`apply_hncs_video_frame()`, or
  to any brand file not named in this plan.
- **`brands/hasselblad.py` is not modified by this plan at all** — not
  even a docstring touch. Verify this explicitly at the end (Task 3).
- Zero behavior change: both functions' output for a given input must be
  byte-identical before and after.
- `python3 -m unittest discover -s tests` must stay green (excluding the
  pre-existing, unrelated `torch`/`tkinter`-import errors already present
  in this sandbox before this plan).

---

### Task 1: Add `make_hasselblad_body_look()` to `core/engine.py`

**Files:**
- Modify: `core/engine.py` (add new function after `make_population_fit_look`,
  before `apply_population_fit_look_video_frame`)
- Modify: `tests/test_engine.py` (add new test class)

**Interfaces:**
- Consumes: `cv2`, `numpy as np`, `film_curve` (all already imported at
  the top of `core/engine.py` — no new imports needed).
- Produces: `make_hasselblad_body_look(toe_lift, shoulder_start,
  white_point, clahe_clip, exposure_gamma)` — a function that returns a
  callable `apply(img_bgr, toe_lift=<bound>, shoulder_start=<bound>,
  white_point=<bound>, clahe_clip=<bound>, exposure_gamma=<bound>)`.
  Task 3 imports and calls this from both Hasselblad body-variant files.

- [ ] **Step 1: Write the failing tests**

Append this new test class to `tests/test_engine.py`, immediately before
the final `if __name__ == "__main__":` line:

```python
class TestMakeHasselbladBodyLook(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_matches_hand_written_reference_implementation(self):
        from core.engine import make_hasselblad_body_look
        fn = make_hasselblad_body_look(toe_lift=0.02, shoulder_start=0.58,
                                        white_point=0.95, clahe_clip=1.25,
                                        exposure_gamma=0.6)
        out = fn(self.img)

        # 팩토리와 별개로 직접 구현한 참조 버전 - hasselblad_x2dii.py의
        # 리팩토링 전 실제 본문을 그대로 복사한 것(팩토리 자체를 다시
        # 안 쓰고 있어 순환 검증이 아니다).
        lab = cv2.cvtColor(self.img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** 0.6) * 255, 0, 255).astype(np.uint8)
        l_expected = cv2.LUT(l, exp_lut)
        clahe = cv2.createCLAHE(clipLimit=1.25, tileGridSize=(8, 8))
        l_expected = clahe.apply(l_expected)
        lut = np.clip(film_curve(x, 0.02, 0.58, 0.95) * 255, 0, 255).astype(np.uint8)
        l_expected = cv2.LUT(l_expected, lut)
        expected = cv2.cvtColor(cv2.merge((l_expected, a, b)), cv2.COLOR_LAB2BGR)

        np.testing.assert_array_equal(out, expected)

    def test_signature_exposes_bound_defaults(self):
        import inspect
        from core.engine import make_hasselblad_body_look
        fn = make_hasselblad_body_look(toe_lift=0.02, shoulder_start=0.58,
                                        white_point=0.95, clahe_clip=1.25,
                                        exposure_gamma=0.6)
        sig = inspect.signature(fn)
        self.assertAlmostEqual(sig.parameters["toe_lift"].default, 0.02)
        self.assertAlmostEqual(sig.parameters["shoulder_start"].default, 0.58)
        self.assertAlmostEqual(sig.parameters["white_point"].default, 0.95)
        self.assertAlmostEqual(sig.parameters["clahe_clip"].default, 1.25)
        self.assertAlmostEqual(sig.parameters["exposure_gamma"].default, 0.6)

    def test_exposure_gamma_of_one_skips_exposure_lut(self):
        from core.engine import make_hasselblad_body_look
        fn = make_hasselblad_body_look(toe_lift=0.0, shoulder_start=0.82,
                                        white_point=1.0, clahe_clip=1.25,
                                        exposure_gamma=1.0)
        out = fn(self.img)

        # exposure_gamma=1.0이면 `if exposure_gamma != 1.0` 분기 전체를
        # 건너뛰어야 한다 - 노출 LUT 단계 없이 CLAHE -> 필름커브만 적용한
        # 참조 버전과 정확히 일치해야 그 분기가 실제로 스킵됐다고 말할 수
        # 있다(부동소수점 근사 비교가 아니라 정확히 같은 코드 경로인지
        # 확인하는 테스트).
        lab = cv2.cvtColor(self.img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.25, tileGridSize=(8, 8))
        l_expected = clahe.apply(l)
        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x, 0.0, 0.82, 1.0) * 255, 0, 255).astype(np.uint8)
        l_expected = cv2.LUT(l_expected, lut)
        expected = cv2.cvtColor(cv2.merge((l_expected, a, b)), cv2.COLOR_LAB2BGR)

        np.testing.assert_array_equal(out, expected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_engine -v`
Expected: FAIL — `ImportError: cannot import name 'make_hasselblad_body_look' from 'core.engine'`

- [ ] **Step 3: Implement `make_hasselblad_body_look()`**

In `core/engine.py`, add this function immediately after
`make_population_fit_look` and before `apply_population_fit_look_video_frame`:

```python
def make_hasselblad_body_look(toe_lift, shoulder_start, white_point, clahe_clip, exposure_gamma):
    """Hasselblad 단독바디 apply_hncs_* 변형(hasselblad_x1d50c.py/
    hasselblad_x2dii.py)이 공유하는 본문(노출감마 LUT -> CLAHE ->
    필름커브 LUT)을 브랜드별 5개 파라미터로 고정해 반환한다.
    population-fit 브랜드의 make_population_fit_look()과는 별개 팩토리 -
    이쪽은 raw+jpeg 페어로 직접 캘리브레이션된 Hasselblad 바디 변형
    전용이라 exposure_gamma 단계가 있고 컬러 매트릭스 단계가 없다.
    brands/hasselblad.py 자체는 이 팩토리와 무관하게 그대로 둔다."""
    def apply(img_bgr, toe_lift=toe_lift, shoulder_start=shoulder_start,
              white_point=white_point, clahe_clip=clahe_clip, exposure_gamma=exposure_gamma):
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        if exposure_gamma != 1.0:
            x = np.arange(256, dtype=np.float32) / 255.0
            exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
            l = cv2.LUT(l, exp_lut)

        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
        l = clahe.apply(l)

        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                      0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)

        return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    return apply
```

Also add `import cv2` to `tests/test_engine.py`'s imports if not already
present — check first: `tests/test_engine.py` already imports `cv2` at
the top (used by `TestApplyPopulationFitLookVideoFrame.test_matches_tone_curve_only_no_clahe`),
so no import change is needed there.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_engine -v`
Expected: all tests PASS, including the 3 new ones.

- [ ] **Step 5: Commit**

```bash
git add core/engine.py tests/test_engine.py
git commit -m "Add make_hasselblad_body_look() factory to core/engine.py"
```

---

### Task 2: Extend golden byte-hash test with the 2 Hasselblad body variants

**Files:**
- Modify: `tests/test_population_fit_look_golden.py`

**Interfaces:**
- Consumes: `brands.hasselblad_x1d50c.apply_hncs_x1d50c` and
  `brands.hasselblad_x2dii.apply_hncs_x2dii` (unchanged in this task —
  this task only adds test assertions, no production code changes).
- Produces: a passing regression test that Task 3 re-runs unchanged to
  prove the refactor didn't alter either function's output.

- [ ] **Step 1: Add a second hash list and test class**

Append this to `tests/test_population_fit_look_golden.py`, after the
existing `TestPopulationFitLookGoldenHashes` class and before the final
`if __name__ == "__main__":` line:

```python
# (모듈 경로, 함수명, 리팩토링 전 sha256(출력.tobytes())) - Hasselblad
# 단독바디 apply_hncs_* 변형 2개
# (docs/superpowers/plans/2026-08-09-hasselblad-body-variant-wrapper-consolidation.md)
HASSELBLAD_BODY_GOLDEN_HASHES = [
    ("brands.hasselblad_x1d50c", "apply_hncs_x1d50c",
     "a2f56608aab5a6c06f69f9e041467edbcfa37a605576df0e5e7d4eb2ea8f9267"),
    ("brands.hasselblad_x2dii", "apply_hncs_x2dii",
     "e56aae33aeb387ea18efc03371567c1e0da55a3e4e6fca3c77fa54e2790058fa"),
]


class TestHasselbladBodyVariantGoldenHashes(unittest.TestCase):
    def test_both_body_variants_match_pre_refactor_output(self):
        img = make_test_image()
        for mod_name, fn_name, expected_hash in HASSELBLAD_BODY_GOLDEN_HASHES:
            with self.subTest(brand=mod_name, fn=fn_name):
                mod = importlib.import_module(mod_name)
                fn = getattr(mod, fn_name)
                out = fn(img)
                actual_hash = hashlib.sha256(out.tobytes()).hexdigest()
                self.assertEqual(actual_hash, expected_hash,
                                  f"{mod_name}.{fn_name} output changed - "
                                  f"expected sha256={expected_hash}, got {actual_hash}")
```

- [ ] **Step 2: Run the test to verify both hashes match *today's*
  (pre-refactor) code**

Run: `python3 -m unittest tests.test_population_fit_look_golden -v`
Expected: PASS — both
`test_all_12_brands_match_pre_refactor_output` and
`test_both_body_variants_match_pre_refactor_output` show `ok`. If the
new test fails here, the hash in this plan was transcribed wrong — stop
and fix it before proceeding to Task 3.

- [ ] **Step 3: Commit**

```bash
git add tests/test_population_fit_look_golden.py
git commit -m "Extend golden byte-hash test with 2 Hasselblad body-variant outputs"
```

---

### Task 3: Refactor both Hasselblad body-variant files

**Files:**
- Modify: `brands/hasselblad_x1d50c.py`
- Modify: `brands/hasselblad_x2dii.py`

**Interfaces:**
- Consumes: `make_hasselblad_body_look(toe_lift, shoulder_start,
  white_point, clahe_clip, exposure_gamma)` from Task 1 (`core/engine.py`).
- Produces: nothing new consumed by later tasks — this is the last task
  in this plan. `apply_hncs_x1d50c` and `apply_hncs_x2dii`'s names,
  signatures, and behavior must be identical to before (verified by Task
  2's golden test and the existing `tests/test_brands.py` suite).

- [ ] **Step 1: `brands/hasselblad_x1d50c.py`**

Change the import block (currently):
```python
import cv2
import numpy as np

from core.curve import film_curve
```
to:
```python
from core.engine import make_hasselblad_body_look
```

Change the function definition (currently):
```python
def apply_hncs_x1d50c(img_bgr, toe_lift=0.0, shoulder_start=0.82,
                       white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
```
to:
```python
apply_hncs_x1d50c = make_hasselblad_body_look(
    toe_lift=0.0, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7)
```

Everything above the import line (the module docstring with the full
measurement history) stays untouched.

- [ ] **Step 2: `brands/hasselblad_x2dii.py`**

Change the import block (currently):
```python
import cv2
import numpy as np

from core.curve import film_curve
```
to:
```python
from core.engine import make_hasselblad_body_look
```

Change the function definition (currently):
```python
def apply_hncs_x2dii(img_bgr, toe_lift=0.02, shoulder_start=0.58,
                      white_point=0.95, clahe_clip=1.25, exposure_gamma=0.6):
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
    l = clahe.apply(l)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
```
to:
```python
apply_hncs_x2dii = make_hasselblad_body_look(
    toe_lift=0.02, shoulder_start=0.58, white_point=0.95, clahe_clip=1.25, exposure_gamma=0.6)
```

Everything above the import line (the module docstring with the full
measurement history) stays untouched.

- [ ] **Step 3: Confirm `brands/hasselblad.py` was not touched**

Run: `git diff --stat -- brands/hasselblad.py`
Expected: empty output (no changes).

- [ ] **Step 4: Run the golden regression test**

Run: `python3 -m unittest tests.test_population_fit_look_golden -v`
Expected: PASS — all 12 population-fit hashes AND both Hasselblad
body-variant hashes still match, proving this refactor changed zero
pixels.

- [ ] **Step 5: Run the brand and engine suites**

Run: `python3 -m unittest tests.test_brands tests.test_engine -v`
Expected: PASS (same results as before this task).

- [ ] **Step 6: Run the full suite**

Run: `python3 -m unittest discover -s tests`
Expected: same pass/fail counts as before this plan (the sandbox's
pre-existing `torch`/`tkinter`-import errors are unrelated and expected).

- [ ] **Step 7: Commit**

```bash
git add brands/hasselblad_x1d50c.py brands/hasselblad_x2dii.py
git commit -m "Collapse 2 Hasselblad body-variant wrappers to make_hasselblad_body_look() calls"
```
