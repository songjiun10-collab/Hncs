# Task 4 report — Cross-platform golden verification

## Status

DONE

## Changed

- `tests/test_population_fit_look_golden.py`
  - Kept CI SHA-256 equality for every stable function.
  - Moved the seven documented OpenCV BGR→HSV→BGR functions into a separate
    behavior test: expected `uint8` 128×128×3 output and a bounded same-
    environment pixel difference of `max |Δ| == 0` across repeat invocations.
  - Recorded why no non-zero cross-platform tolerance is asserted: the
    repository preserves only the CI SHA-256 values, not the corresponding
    pixel arrays, so that bound cannot be measured honestly.

## TDD evidence

- RED: `.venv/bin/python -m unittest tests.test_population_fit_look_golden -v`
  failed only the seven known HSV-round-trip hashes; stable functions passed.
  The failing local SHA-256 values matched the historical macOS values in
  `e439f55`, confirming documented platform variance rather than a behavior
  change.
- GREEN: the same command passed 5 tests after the test split.

## Verification

- `.venv/bin/python -m unittest tests.test_population_fit_look_golden -v`
  — 5 tests, OK.
- `.venv/bin/python -m unittest discover -s tests`
  — 906 tests, OK (13.789 s).
- `git diff --check` — clean.

## Review P1 correction

The first version's same-environment repeat check could accept a deterministic
all-zero implementation. It was replaced with seven independent output
fingerprints: BGR channel means, standard deviations, and q01/q25/q50/q75/q99
quantiles. Each statistic allows an absolute difference of at most `1.0`.
That bound follows from the documented one-least-significant-bit OpenCV
round-trip variation: a per-pixel difference no larger than one bounds each
mean, standard deviation, and quantile difference by one.

- RED: monkeypatching `brands.fuji.apply_pro_neg_std` to an all-zero image made
  the previous repeat-only test pass, proving the review finding. After adding
  the fingerprint assertion, the same replacement failed with 19/21 anchor
  values outside the `1.0` bound.
- GREEN: the all-zero rejection test and all golden tests passed (6 tests).

## Re-review tolerance correction

`atol=1.0` rejected a valid clipped uniform `+1` LSB variation for three
functions because NumPy reported a statistic difference of
`1.000000000000014`. The bound is now `1.001`: the extra `0.001` covers only
floating-point aggregation error beyond the documented one-LSB variation.

- RED: `test_reference_check_accepts_clipped_one_lsb_variation` failed for
  Pro Neg Std, Eterna Cinema, and Eterna Bleach Bypass at `atol=1.0`.
- GREEN: with `atol=1.001`, the clipped `+1` LSB test and all-zero rejection
  test pass alongside the exact-hash checks (7 golden tests).
- Final verification: `.venv/bin/python -m unittest discover -s tests` — 908
  tests, OK (43.144 s).
