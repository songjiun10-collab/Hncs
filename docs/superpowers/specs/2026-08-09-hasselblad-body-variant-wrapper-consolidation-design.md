# Hasselblad Single-Body Variant Wrapper Consolidation — Design

> Extension of sub-project 2 ("레포 전체 대규모 리팩토링" initiative),
> requested after sub-project 2 shipped. Same motivation (maintainability
> + readability), narrower scope: the two Hasselblad single-body
> `apply_hncs_*` variants, not the 12 population-fit brands (already
> done).

## Governing exception

Root `CLAUDE.md`'s "## Never" section forbids modifying any shipped
`apply_*` function without the user's explicit, in-the-moment sign-off;
`brands/CLAUDE.md` calls `apply_hncs()` specifically "the hardest version
of this rule." The user gave explicit sign-off for this change
(2026-08-09), after being told: (a) only 2 files currently share this
exact duplicated pattern, below the usual "rule of three" bar for
introducing an abstraction, and (b) the plan is to add a shared factory
now anyway, on the stated expectation that more single-body Hasselblad
variants will be added as more raw+jpeg pairs get collected (same growth
pattern the population-fit brands went through). Design choice made to
minimize risk regardless: **`brands/hasselblad.py` itself is not touched
at all** — the factory lives in `core/engine.py`, and neither
`apply_hncs()` nor `apply_hncs_video_frame()` changes in any way.

## Problem

`brands/hasselblad_x1d50c.py`'s `apply_hncs_x1d50c()` and
`brands/hasselblad_x2dii.py`'s `apply_hncs_x2dii()` have byte-for-byte
identical bodies (exposure-gamma LUT -> CLAHE -> film-curve LUT), differing
only in their five default parameter values:

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

This is a different pattern from the 12 population-fit brands (no CLAHE
step ordering with exposure gamma, no color matrix — and critically, no
delegation to `core.engine.apply_population_fit_look`), so sub-project
2's `make_population_fit_look()` factory does not apply here; a new,
separate factory is needed.

## Investigation findings

- Neither `apply_hncs_x1d50c` nor `apply_hncs_x2dii` is registered in any
  `inspect.signature()`-reading registry — confirmed via repo-wide grep
  for `x1d50c`/`x2dii` in `tools/video_engine.py`,
  `hybrid_engine/core/preset_inverse.py`, `core/lut_export.py`,
  `tools/classify_brand.py`, `core/brand_classifier.py`,
  `tests/test_video_engine.py`: zero matches in all of them. So, unlike
  sub-project 2, there is no constraint forcing the factory's returned
  callable to be introspectable via `inspect.signature()` — but the
  design still uses a real `def` closure anyway, for consistency with
  `make_population_fit_look()` and because it costs nothing.
- Both files currently declare their defaults **inline in the function
  signature** — no module-level `_TOE_LIFT`-style constants exist in
  either file (unlike the 12 population-fit brands). The refactor
  preserves this: the one-line factory call uses keyword arguments
  directly, no new constants are introduced (YAGNI — nothing else in
  either file needs those values as named constants).
- Other files reference `apply_hncs_x2dii`/`apply_hncs_x1d50c` by name in
  docstrings only (`brands/sony_a7v.py`, several `tools/evaluate_x2dii_*.py`
  research scripts) — none import or call them, so nothing else needs
  updating.

## Design

### `core/engine.py`: add a second factory function

Append this function to `core/engine.py`, after `make_population_fit_look`
and before `apply_population_fit_look_video_frame` (i.e., the file ends
up with: `apply_population_fit_look`, `make_population_fit_look`,
`make_hasselblad_body_look`, `apply_population_fit_look_video_frame`, in
that order):

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

### `brands/hasselblad_x1d50c.py` and `brands/hasselblad_x2dii.py`

Replace the full function body with one line each, keeping every
docstring untouched:

`brands/hasselblad_x1d50c.py` after:
```python
import cv2
import numpy as np

from core.curve import film_curve
```
becomes:
```python
from core.engine import make_hasselblad_body_look
```
(the `cv2`/`numpy`/`film_curve` imports move into `core/engine.py`,
which already imports `cv2`/`numpy`/`film_curve` for
`apply_population_fit_look` — no new dependency), and the function
becomes:
```python
apply_hncs_x1d50c = make_hasselblad_body_look(
    toe_lift=0.0, shoulder_start=0.82, white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7)
```

`brands/hasselblad_x2dii.py`'s function becomes:
```python
apply_hncs_x2dii = make_hasselblad_body_look(
    toe_lift=0.02, shoulder_start=0.58, white_point=0.95, clahe_clip=1.25, exposure_gamma=0.6)
```
with the same import change.

## Verification

Same discipline as sub-project 2, scaled down to 2 functions:

1. **Golden byte-identical regression test**: extend
   `tests/test_population_fit_look_golden.py` with 2 more entries (or add
   a new small test class in the same file — implementation plan
   decides), using the same `make_test_image()` fixture. Real hashes,
   captured from the current (pre-refactor) code:
   - `brands.hasselblad_x1d50c.apply_hncs_x1d50c`:
     `a2f56608aab5a6c06f69f9e041467edbcfa37a605576df0e5e7d4eb2ea8f9267`
   - `brands.hasselblad_x2dii.apply_hncs_x2dii`:
     `e56aae33aeb387ea18efc03371567c1e0da55a3e4e6fca3c77fa54e2790058fa`
2. `tests/test_brands.py`'s existing `BRAND_LOOKS` entries for both
   functions must keep passing unmodified (shape/dtype check).
3. `python3 -m unittest discover -s tests` green (excluding the
   pre-existing, unrelated sandbox `torch`/`tkinter` import errors).
4. Confirm `brands/hasselblad.py` does not appear in the diff at all.

## Files touched

- Modify: `core/engine.py` (add `make_hasselblad_body_look`)
- Modify: `brands/hasselblad_x1d50c.py`, `brands/hasselblad_x2dii.py`
- Modify: `tests/test_population_fit_look_golden.py` (add 2 hash entries)
