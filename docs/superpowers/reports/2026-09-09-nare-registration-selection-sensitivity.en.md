# NARE registration selection sensitivity — GFX100RF Provia

[한국어](2026-09-09-nare-registration-selection-sensitivity.md)

After the 2026-09-09 registration-method change, I re-split the existing
GFX100RF Provia 51-frame exploratory result by the current registration gate.
The goal is to measure not only whether geometry errors are removed, but also
**how much the registration gate itself changes the reported effect size**.

No candidate is fitted here. The analysis only reads the frozen artifacts:

- `nare_provia_exploratory_metrics_512px_2026-09.json`
- `nare_provia_exploratory_registration_512px_2026-09.json`
- `nare_provia_registered_report_512px_2026-09.json`
- `nare_provia_registered_report_1024px_2026-09.json`

The analysis revision is `860abb164b7001c80fe67b44c39d5383f14d150d`.
A machine-readable copy is stored in
`nare_provia_registration_selection_sensitivity_2026-09.json`.

## Result 1 — the current gate accepts 32 of 51 frames

The current 512px registration preflight gives **32 pass / 19 fail** from 51
inputs. The 19 failures are 9 aspect-ratio mismatches and 10 ECC
correlation/translation/overlap geometry failures.

This is stricter than the older `37/51` value still present in historical
notes. The old 37-scene and current 32-scene results must therefore not be
interpreted as the same experiment.

## Result 2 — registration eligibility is strongly associated with the pre-registration effect

I took the **same unregistered 51-frame exploratory metrics** and split them
only by the current registration pass/fail IDs.

| subset | n | B0 mean ΔE00 | Provia mean ΔE00 | mean ΔE gain | aggregate gain | wins/losses |
|---|---:|---:|---:|---:|---:|---:|
| all intake | 51 | 20.7150 | 17.6103 | +3.1047 | +14.99% | 42/9 |
| registration pass | 32 | 18.5950 | 14.7033 | +3.8917 | **+20.93%** | 28/4 |
| registration fail | 19 | 24.2855 | 22.5064 | +1.7791 | **+7.33%** | 14/5 |
| └ aspect-ratio fail | 9 | 23.4781 | 20.8777 | +2.6004 | +11.08% | 8/1 |
| └ geometry fail | 10 | 25.0122 | 23.9722 | +1.0399 | **+4.16%** | 6/4 |

The current pass subset is therefore **+5.94 percentage points** above the full
51-frame aggregate and **+13.60 percentage points** above the fail subset.

For per-scene absolute improvement `(B0 ΔE - candidate ΔE)`, the pass-minus-fail
mean difference is **+2.1126 ΔE**. An independent-group bootstrap with 200,000
draws (seed 0) gives a 95% CI of **[+0.6194, +3.5669]**; a two-sided label
permutation test with 200,000 draws gives **p=0.01218**.

Using per-scene relative improvement gives pass **20.87%**, fail **6.15%**,
for a difference of **+14.72 percentage points**. The bootstrap 95% CI is
**[+7.51, +21.75] percentage points**, with permutation **p=0.00099**.

### Interpretation limit

This must not be read as “registration causes Provia to perform better.” The
old exploratory ΔE values for registration-failed scenes are geometry-contaminated
by definition and are not valid performance targets.

What the result does establish is that **the gate is not independent of the
observed effect-size distribution**. Reporting only the accepted subset without
intake/exclusion accounting can therefore make a methodology change look like a
candidate improvement.

## Result 3 — geometric correction changes the effect again

The current registered reports for the accepted 32 scenes are:

| scale | n | B0 mean ΔE00 | Provia mean ΔE00 | gain | absolute-improvement 95% CI |
|---|---:|---:|---:|---:|---:|
| 512px | 32 | 15.9318 | 11.0512 | **+30.63%** | [+3.9864, +5.7387] |
| 1024px | 32 | 16.0787 | 11.4645 | **+28.70%** | [+3.7250, +5.4636] |

The 512→1024 difference is only **−1.94 percentage points**, so the registered
effect is comparatively stable to this scale change. But the same 32 accepted
scenes had a +20.93% effect in their *unregistered* exploratory metrics, meaning
geometry correction plus valid-overlap evaluation changes the measured effect
by another roughly **+9.71 percentage points**.

Therefore the old 51-frame unregistered `+14.99%` and the current 32-frame
registered `+30.63%` cannot be compared as if the candidate alone improved.
At least two methodology effects are mixed into the change:

1. registration eligibility selection: `+14.99% → +20.93%`
2. geometry correction / valid-overlap evaluation on accepted scenes:
   `+20.93% → +30.63%`

## Methodology conclusion

Future registered NARE reports should record, at minimum:

- original intake scene count,
- registration pass/fail counts and failure categories,
- pass/fail pre-registration sensitivity when available,
- registered effect and scale sensitivity.

This is **methodology-sensitivity evidence**, not ship evidence. The GFX100RF
pool still does not satisfy the lighting/scene taxonomy and independent
contributor requirements, so this analysis must not raise its NARE
classification.
