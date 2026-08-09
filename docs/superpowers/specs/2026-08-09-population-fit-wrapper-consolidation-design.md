# Population-Fit Brand Wrapper Consolidation — Design

> Sub-project 2 of 4 in the "레포 전체 대규모 리팩토링" initiative
> (maintainability + readability). Sub-project 1 (onboarding docs) is
> done. This one, sub-project 3 (`tools/` adopted-vs-rejected index), and
> sub-project 4 (splitting `tools/calibrate.py`) get their own specs.

## Governing exception

Root `CLAUDE.md`'s "## Never" section forbids modifying any shipped
`apply_*` function without the user's explicit, in-the-moment sign-off.
The user gave that sign-off explicitly for this sub-project (2026-08-09),
and `CLAUDE.md` was updated in the same conversation to record that an
explicit, discussed exception (like this one) is a sanctioned path,
distinct from a silent/automatic change. This spec is that record: what
was approved (collapsing 12 identical wrapper-function bodies into a
shared factory) and why (net removal of duplicated code, zero behavior
change, verified byte-for-byte — see Verification below).

## Problem

`brands/canon.py`, `leica.py`, `leica_raw.py`, `nikon.py`, `olympus.py`,
`panasonic.py`, `pentax.py`, `phaseone.py`, `ricoh_gr.py`, `sigma.py`,
`sony.py`, `sony_a7v.py` (12 files) each define an `apply_*_look()`
function whose body is byte-for-byte identical across all 12 — only the
function name and four constant values differ:

```python
def apply_canon_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
                      white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP):
    return apply_population_fit_look(img_bgr, toe_lift, shoulder_start, white_point, clahe_clip)
```

A reader has to open several of these files before noticing the pattern;
each new population-fit brand copies the same 3-line boilerplate again.

## Goals

- Each brand file states only its calibrated constants; the wrapper
  boilerplate exists in exactly one place (`core/engine.py`).
- Zero behavioral change: every call site (photo-mode `apply_*_look()`
  calls, and the two `inspect.signature()` consumers below) produces
  identical output to before, verified, not assumed.

## Non-goals

- Not touching `brands/hasselblad*.py` (protected, out of scope
  regardless) or any brand that does **not** already delegate to
  `core.engine.apply_population_fit_look` (e.g. `brands/fuji.py`'s
  preset functions have real per-preset logic, not this pattern).
- Not changing any constant's value. This is pure code motion.

## Critical constraint found during investigation

Two consumers read these wrapper functions' defaults via
`inspect.signature()`, not by importing the brand's private constants
directly — specifically so they always see the brand file's current
values without duplicating them:

- `hybrid_engine/core/preset_inverse.py:80`, `curve_params()`:
  `inspect.signature(BRAND_FUNCS[brand]).parameters["toe_lift"].default`
  (also reads `shoulder_start`, `white_point`).
- `tools/video_engine.py:116`, `brand_video_params()`: same pattern,
  reading `toe_lift`, `shoulder_start`, `white_point`.

`functools.partial` also satisfies `inspect.signature()` correctly
(verified interactively: `inspect.signature(functools.partial(f,
toe_lift=0.5)).parameters["toe_lift"].default == 0.5`), but a factory
that returns a real `def`-based closure is safer and simpler — it stays
a genuine function (passes `isinstance(x, types.FunctionType)` if
anything ever checks that, though nothing currently does — confirmed via
repo-wide grep for `.__name__` and `isinstance` on these functions,
finding none), and `inspect.signature()` behaves identically to today
with zero special-casing. The design below uses a closure, not
`functools.partial`.

## Design

### `core/engine.py`: add one factory function

Append this function to `core/engine.py`, after `apply_population_fit_look`
and before `apply_population_fit_look_video_frame`:

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

### Each of the 12 brand files: replace import + wrapper with one line

Pattern (shown for `brands/canon.py`, lines 88-98 today):

Before:
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

After:
```python
from core.engine import make_population_fit_look

_TOE_LIFT = 15.0 / 255
_WHITE_POINT = 239.1 / 255
_SHOULDER_START = 0.78  # 미검증 - 핫셀블라드 기본값 차용
_CLAHE_CLIP = 1.25  # 미검증 - 핫셀블라드 기본값 차용

apply_canon_look = make_population_fit_look(_TOE_LIFT, _SHOULDER_START, _WHITE_POINT, _CLAHE_CLIP)
```

Every other file follows the identical pattern: swap the import, delete
the 3-line `def`, replace with one `apply_<brand>_look = make_population_fit_look(...)`
line, positional args always in `(toe_lift, shoulder_start, white_point,
clahe_clip)` order regardless of the order the file declares its
constants in. Docstrings and constant declarations are untouched.

All 12 target functions and their current constant values (for the
implementation plan to reference directly — no need to re-derive them):

| File | Function | `_TOE_LIFT` | `_SHOULDER_START` | `_WHITE_POINT` | `_CLAHE_CLIP` |
|---|---|---|---|---|---|
| `brands/canon.py` | `apply_canon_look` | `15.0 / 255` | `0.78` | `239.1 / 255` | `1.25` |
| `brands/leica.py` | `apply_leica_look` | `9.2 / 255` | `0.78` | `229.8 / 255` | `1.25` |
| `brands/leica_raw.py` | `apply_leica_raw_look` | `0.0` | `0.82` | `1.0` | `1.25` |
| `brands/nikon.py` | `apply_nikon_look` | `13.7 / 255` | `0.78` | `237.3 / 255` | `1.25` |
| `brands/olympus.py` | `apply_olympus_look` | `14.5 / 255` | `0.78` | `232.2 / 255` | `1.25` |
| `brands/panasonic.py` | `apply_panasonic_look` | `13.4 / 255` | `0.78` | `223.2 / 255` | `1.25` |
| `brands/pentax.py` | `apply_pentax_look` | `11.2 / 255` | `0.78` | `237.3 / 255` | `1.25` |
| `brands/phaseone.py` | `apply_phaseone_look` | `12.8 / 255` | `0.78` | `226.5 / 255` | `1.25` |
| `brands/ricoh_gr.py` | `apply_ricoh_gr_look` | `8.4 / 255` | `0.78` | `245.2 / 255` | `1.25` |
| `brands/sigma.py` | `apply_sigma_look` | `9.3 / 255` | `0.78` | `228.8 / 255` | `1.25` |
| `brands/sony.py` | `apply_sony_look` | `9.1 / 255` | `0.78` | `228.6 / 255` | `1.25` |
| `brands/sony_a7v.py` | `apply_sony_a7v_look` | `0.06` | `0.82` | `1.0` | `1.25` |

(Values are read directly from each file's current `_TOE_LIFT`/etc.
constants, unchanged by this refactor — the table exists so the
implementation plan doesn't have to re-grep the repo.)

## Verification

Behavior-preservation is the whole point of this refactor, so it gets
more scrutiny than a typical docs-only change:

1. **Golden byte-identical regression test** (new): for each of the 12
   brands, generate one fixed random BGR image (same seed as
   `tests/test_brands.py`'s `make_test_image()`), call the **current**
   (pre-refactor) `apply_*_look()` and save the output array; after the
   refactor, call the **same function name** again and assert
   `np.array_equal` against the saved output. Concretely: capture
   baseline outputs in the implementation plan's first task (before any
   `core/engine.py`/brand file edit), diff against post-refactor outputs
   in the last task.
2. **Existing suites stay green**: `tests/test_brands.py` (all 12
   `BRAND_LOOKS` entries already call these exact functions and check
   shape/dtype), `tests/test_video_engine.py` (exercises
   `brand_video_params()`, i.e. the `inspect.signature()` path in
   `tools/video_engine.py`), and any `preset_inverse` tests exercising
   `curve_params()`.
3. `python3 -m unittest discover -s tests` full suite green (excluding
   the pre-existing, unrelated `torch` import errors in this sandbox).

## Files touched

- Modify: `core/engine.py` (add `make_population_fit_look`)
- Modify: all 12 files in the table above (swap import, collapse wrapper
  to one line)
- Create: a new test file or an addition to an existing one for the
  golden byte-identical check (exact location decided in the
  implementation plan)
