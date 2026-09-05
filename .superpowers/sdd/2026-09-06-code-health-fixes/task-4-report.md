# Task 4 report — Cross-platform golden verification

## Status

DONE_WITH_CONCERNS

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

## Concern

The exact cross-platform maximum pixel difference is still unknown because
the historical CI output images were not retained. The test intentionally does
not invent a non-zero tolerance; obtaining a CI pixel fixture is required for
a future cross-platform magnitude assertion.
