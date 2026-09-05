# Task 3 report: empty Fuji datasets and file handles

## Status

DONE_WITH_CONCERNS

## Changes

- Added a shared integration regression: an empty `manifest.csv` makes all four
  Fuji recalibration tools raise `ValueError` containing `usable pairs`, before
  bootstrap statistics, `min()`, or report output. The tracked manifest handle
  is closed in every case.
- Updated the four Fuji tools to context-manage `manifest.csv` and reject zero
  usable JPEG/RAW pairs before statistics.
- Context-managed JSON and text reads touched in `tools/audit_repo_integrity.py`.
  Added a regression proving profile JSON handles close after parsing.

## Verification

- RED: `python3 -m unittest tests.test_fuji_classic_negative_recalibration.TestEmptyFujiManifest -v`
  failed in `evaluate_fuji_classic_negative_v2_grid.main()` with
  `TypeError: 'NoneType' object is not iterable`; the profile JSON handle test
  failed with `was_closed == False`.
- GREEN/focused: `python3 -m unittest tests.test_fuji_classic_negative_recalibration tests.test_audit_repo_integrity -v`
  passed: 43 tests, 0 failures.
- Full: `python3 -m unittest discover -s tests` ran 905 tests and has 7 existing
  golden-hash failures in `test_population_fit_look_golden`:
  six Fuji functions (`apply_pro_neg_std`, `apply_pro_neg_hi`,
  `apply_eterna_cinema`, `apply_eterna_bleach_bypass`, `apply_reala_ace`, and
  `apply_classic_negative`) plus `apply_hasselblad_night`. Task 3 did not edit
  any shipped look function.
- `python3 -m tools.audit_repo_integrity` reports 2 unrelated registration
  failures for untracked `tools/refit_borrowed_population_fit_params.py`.

## Concerns

- Full suite remains non-green because of the 7 pre-existing golden hashes.
- The integrity audit is non-green because another concurrent task added an
  unregistered tool.
