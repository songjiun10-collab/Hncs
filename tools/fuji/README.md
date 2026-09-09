# Fujifilm research tools

These scripts are measurement and fitting tools. They do not modify shipped
`brands/fuji` look implementations or profile assets unless a separate command
explicitly requests an approved deployment.

For the NARE workflow, run strict RAW/JPEG intake first, then run
`hybrid_engine.evaluation.nare_registration_cli` to create a registration
preflight report and a passed-only frozen manifest. Generate per-scene metrics
with `hybrid_engine.evaluation.nare_runner_cli`. Only after the manifest is
frozen should a fitting experiment be run.

`fit_nare_provia_session_holdout.py` fits a small Provia tone/CLAHE grid with
capture-session holdout. Sessions, rather than individual burst frames, are
held out to prevent scene leakage. Its output is research evidence; a candidate
is not promoted when its paired confidence interval contains zero.

The current registered GFX100RF replay and its English report are linked from
`hybrid_engine/EVALUATION.md` and
`docs/superpowers/reports/2026-09-08-nare-provia-session-holdout-fit.en.md`.
