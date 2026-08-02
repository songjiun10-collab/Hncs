# hybrid_engine/

Cross-camera color conversion + the calibration/evaluation machinery.
`EVALUATION.md` here is the project's measurement record.

## Never touch

`assets/profiles/hasselblad.json`, `assets/profiles/*.dcp`. These are
shipped calibration artifacts. A research script that writes to them is a
bug, no matter what it measured.

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
