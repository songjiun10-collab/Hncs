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
