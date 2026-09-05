# Task 2 report — research-tool colour domain

Status: DONE_WITH_CONCERNS

## Root cause

`mean_delta_e()` requires linear RGB, but both Fuji research tools supplied
OpenCV BGR uint8 output and JPEG target arrays directly.  The L-channel
research verifier also imported the unavailable private
`intermediate_attributes_CIE2000` symbol from `colour-science`.

## TDD evidence

RED (before implementation):

```text
$ python3 -m unittest tests.test_fuji_classic_negative_recalibration.TestDeltaEColorDomain.test_grid_converts_bgr_uint8_inputs_before_delta_e
FAIL: dtype('uint8') != <class 'numpy.float64'>
```

The verifier import also reproduced the compatibility failure:

```text
ImportError: cannot import name 'intermediate_attributes_CIE2000'
```

GREEN verification:

```text
$ python3 -m unittest tests.test_fuji_classic_negative_recalibration
Ran 28 tests in 0.845s
OK

$ python3 -m py_compile hybrid_engine/utils/evaluate.py tools/evaluate_fuji_classic_negative_v2_grid.py tools/diagnose_fuji_autobright_vs_look.py hybrid_engine/verify_l_channel_residual.py
```

`rg -n "mean_delta_e\\(" tools/evaluate_fuji_classic_negative_v2_grid.py
tools/diagnose_fuji_autobright_vs_look.py -C 2` confirms every five affected
metric call receives `bgr_u8_to_linear_rgb(...)` output.  The residual verifier
imports successfully with the installed colour-science 0.4.4.

## Changes

- Added `hybrid_engine.utils.evaluate.bgr_u8_to_linear_rgb`: explicit OpenCV
  BGR uint8 → sRGB-decoded linear RGB float64 conversion.
- Applied it at all grid-fit, holdout, and auto-bright ΔE call sites.
- Replaced the private colour import in `verify_l_channel_residual.py` with a
  local public NumPy/colour-domain implementation of the required CIEDE2000
  L/C/H terms.
- Added regression coverage that intercepts the actual grid ΔE boundary and
  asserts float64 linear input plus hand-derived target values; added a
  regression import test for the verifier.

## Concern

Existing committed Fuji JSON reports retain values produced before this domain
fix. They are preserved per scope, but must not be treated as recomputed output
of the corrected tools until their expensive RAW evaluations are rerun.

## Review follow-up — shared CIEDE2000 terms

Review found the residual verifier had copied the CIEDE2000 intermediate
calculation without the achromatic signed-zero hue guard.  Added
`TestDeltaEColorDomain.test_l_channel_terms_treat_signed_zero_as_achromatic`.
It failed before the repair because the verifier helper returned six values
instead of the shared seven-value intermediate contract (including `R_T`).

Moved the only intermediate formula to
`hybrid_engine.utils.evaluate._cie2000_intermediate_terms`; the existing
weighted ΔE function and residual verifier both consume it.  The shared helper
retains the `np.where((a_p == 0) & (b == 0), 0, atan2(...))` guard, so signed
zero cannot create a spurious achromatic hue.

```text
$ python3 -m unittest tests.test_fuji_classic_negative_recalibration.TestDeltaEColorDomain tests.test_hybrid_engine.TestDeltaE2000Weighted
Ran 8 tests
OK

$ python3 -m unittest tests.test_fuji_classic_negative_recalibration
Ran 29 tests
OK
```

## Boundary probe follow-up

`tools/probe_fuji_classic_negative_v2_boundary.py` also evaluates OpenCV BGR
uint8 candidate and JPEG arrays.  Its pending change was reviewed and retained:
targets are converted once with `bgr_u8_to_linear_rgb`, and every candidate is
converted at the `mean_delta_e` boundary.  No raw BGR metric path remains in
that probe.

## Corrected auto-bright recorded assertion

The full suite exposed a stale pre-fix assertion that auto-bright improvement
was below 15%.  The current corrected-domain
`autobright_vs_look_classic_negative.json` records 15.2787 → 11.4546 ΔE00,
or 25.02899516425401% improvement.  The test now asserts that recorded value
directly; the previous comment/threshold described pre-fix output and was not
a valid invariant after BGR uint8 inputs were corrected to linear RGB.

```text
$ python3 -m unittest tests.test_fuji_classic_negative_recalibration
Ran 30 tests
OK
```
