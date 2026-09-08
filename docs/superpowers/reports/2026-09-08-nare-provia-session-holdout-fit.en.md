# NARE Provia Session-Holdout Fit (2026-09-08)

This is a research-only fit on the 37 GFX100RF Provia scenes that passed the
NARE translation-only registration gate. The fit uses 11 capture-date sessions
as the grouping unit. Every complete session is held out in turn; no frame from
the held-out session contributes to parameter selection.

The grid varies `shoulder_start` in `{0.66, 0.70, 0.74, 0.78, 0.82}` and
`clahe_clip` in `{1.25, 2.0, 3.0}`. The shipped `apply_provia` implementation is
unchanged. The current shipped values are `shoulder_start=0.82` and
`clahe_clip=3.0`.

The scene-level holdout result is:

| quantity | value |
|---|---:|
| scenes / sessions | 37 / 11 |
| current mean CIEDE2000 | 11.989706008913075 |
| holdout candidate mean CIEDE2000 | 11.997309940688302 |
| relative improvement | -0.06342050230067402% |
| paired bootstrap 95% CI | [-0.02051282700178119, +0.00462789732822533] |
| scene wins / losses | 7 / 10 |
| exact sign-test p | 0.629058837890625 |

The confidence interval contains zero and the candidate is slightly worse on
average. This is an inconclusive-to-negative fit result, not evidence to change
the shipped look. The run is recorded in
`datasets/fuji/contributed/dpreview-gfx100rf-preprod-2026-08/nare_provia_session_holdout_fit_512px_2026-09.json`.

Reproduce it with:

```bash
~/.hncs-hybrid-venv312/bin/python3 -m tools.fuji.fit_nare_provia_session_holdout \
  --manifest datasets/fuji/contributed/dpreview-gfx100rf-preprod-2026-08/nare_provia_registered_manifest_2026-09.json \
  --max-dim 512 \
  --out nare_provia_session_holdout_fit_512px_2026-09.json
```
