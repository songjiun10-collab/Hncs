# hybrid_engine/

Cross-camera color conversion + the calibration/evaluation machinery.
`EVALUATION.md` here is the project's measurement record.

## Local environment: use the Python 3.12 venv

`requirements.txt` pins `colour-science==0.4.7`, which requires
Python>=3.11. The machine's default `python3` is 3.9, which can only
install colour-science 0.4.4 — missing
`colour.difference.delta_e.intermediate_attributes_CIE2000`, which
`utils/evaluate.py` imports at module level. Any `hybrid_engine.*` module
(including every `calibrate_profile_<brand>.py`) fails immediately under
the default interpreter. Run these with
`~/.hncs-hybrid-venv312/bin/python3 -m hybrid_engine.<module>` instead
(create via `/opt/homebrew/bin/python3.12 -m venv ~/.hncs-hybrid-venv312`
+ `pip install -r requirements.txt` if it doesn't exist yet). Scoped to
this directory only — the rest of the repo runs fine under the default
3.9.

## Per-brand calibration scripts

`calibrate_profile.py` (Hasselblad) is the template: its fitting
functions (`_find_matrix_and_recalibrate`, `coordinate_descent`,
`learn_hue_lut`) are already brand-agnostic — only `_find_pairs()`/
`_load_calib_set()` and the output paths are Hasselblad-specific.
`calibrate_profile_leica.py`, `_fuji.py`, `_canon.py`, `_sony.py`,
`_nikon.py`, `_sigma.py` (2026-08) are per-brand copies of the loader
(matches the `evaluate_*.py` "copy the loader, don't import a sibling"
convention) that swap in a `datasets/<brand>/contributed/*/manifest.csv`
loader and a brand-specific scratch LUT path
(`assets/luts/<brand>_hue_learned_scratch.npy` — never reuses
`hasselblad_hue_learned.npy`). None of them write to any
`assets/profiles/*.json` — measurement only, same as the original.

**Everything downstream of the loader is shared, not copied.**
`summarize()`, `_paired_cv_losses()`, `_hue_lut_paired_cv_losses()`, and
the driver `run_per_brand_calibration()` live in `calibrate_profile.py`
and are imported by all 6 brand files — a 2026-08 code review found these
had been copy-pasted byte-for-byte into all 6 (only 3 print strings and a
scratch-LUT-path constant actually varied per brand), which had already
caused one real bug (a leftover `datasets/leica/...` path hardcoded in 5
of the 6 files' "no pairs found" diagnostic message, from copying leica
first and never updating it). The "copy, don't couple" convention is
specifically about the *loader* (`_find_pairs`/`_load_calib_set` —
genuinely different per brand, and independent research experiments that
should be free to diverge); it was never meant to cover pure,
brand-agnostic orchestration/statistics code that has zero reason to
diverge between brands. Adding a 7th brand: copy `_find_pairs()`/
`_load_calib_set()`/the two path constants from an existing brand file,
then call `run_per_brand_calibration(brand_label_ko=..., dataset_glob_hint=...,
load_calib_set=_load_calib_set, hue_lut_scratch_path=...)` from
`if __name__ == "__main__":` — do not re-copy `summarize`/`_paired_cv_losses`/
`_hue_lut_paired_cv_losses`/`run`.

## Never touch

`assets/profiles/hasselblad.json`, `assets/profiles/*.dcp`. These are
shipped calibration artifacts. A research script that writes to them is a
bug, no matter what it measured.

## Investigation volume isn't the same as progress

A real user tested `hasselblad_x2dii_chart.dcp` and reported Lightroom
didn't recognize it. Reinstalling `exiftool` to re-verify the file's TIFF
structure was genuinely useful (ruled out corruption — `Validate: OK`),
but the hypotheses generated afterward (folder location, restart
requirement, `UniqueCameraModel` string mismatch) never got confirmed —
the user's actual problem was still open when the session ended. The
amount of investigation made it read like the problem was nearly solved
when it wasn't. Report "ruled out X" and "still unresolved" as separate
facts — don't let volume of activity imply progress it didn't make.

## Statistics — non-negotiable

Three "decisive wins" in this repo turned out to be noise, thread
non-determinism, and an env-var leak that blacked out 75% of every render.

- **Never call a winner from a mean difference.** `summarize()` ships
  paired t-test + sign test (`math.comb`, no scipy) + bootstrap 95% CI
  (20000 draws, fixed seed) + drop-one sensitivity.
- CI straddles zero → **inconclusive** ("판정 보류"). A nice-looking
  percentage doesn't override this.
- **Null result → run a positive control.** Prove the knob actually does
  something before concluding it doesn't help. Nearly got this wrong twice
  (X-Trans demosaic path collapse, darktable OMP leak).
- Copy an existing implementation from `tools/evaluate_*.py` rather than
  writing a new one.

## EVALUATION.md

- Every experiment lands here — win, loss, or inconclusive. **The failures
  are the asset.** ~20 rejected approaches are recorded; that's what stops
  the next session from re-running them.
- Publish the per-pair table so the statistics can be audited without
  re-running the experiment (hours, sometimes). Add a regression test
  feeding that exact table back through `summarize()`
  (`TestSummarizeRecordedRun`).
- Numbers come verbatim from the run log. No hand-rounding.
- A finding later shown wrong gets a dated correction blockquote **in
  place**: `> **정정(YYYY-MM-DD, how it was caught)**: ...`. Never silently
  rewrite — the original stays as history. Applied four times so far.
- Relative links resolve from this directory:
  `../docs/superpowers/specs/...`.

## research/

Mirrors of real pipelines for experiments only. Old approaches stay as
baselines — `hncs_structural.py`'s hard-cluster functions remain untouched
now that the blend variant exists, because the blend experiment measures
itself against them.
