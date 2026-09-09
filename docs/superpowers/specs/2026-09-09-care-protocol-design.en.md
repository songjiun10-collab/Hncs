# CARE: Counterfactual Appearance Response Evaluation

[한국어](2026-09-09-care-protocol-design.md)

Status: proposed HNCS research methodology, with no runner or experimental results
yet. This name and contract are a project proposal, not an established academic standard.

## Purpose and experimental unit

Measure how an appearance implementation responds to controlled changes of the
same input and where discontinuities, information loss or excessive sensitivity
occur. CARE diagnoses response behavior; NARE measures manufacturer-target
reconstruction. CARE replaces neither NARE nor chart colorimetric validation.

Local RAWs without SOOC targets are usable. Applying twelve brand functions to a
common input tests twelve implementations, not twelve manufacturers' sensors or
cameras. Report input camera coverage separately from output look coverage.

Identify captures by original hashes and review physical scene groups. Keep all
derivatives in the original split. A hundred derivatives are not a hundred
independent samples. Until grouping is reviewed, report capture descriptions only.

Create linear float RGB X with a fixed decoder and automatic exposure/WB disabled.
Record demosaic, WB, color space, black/white levels, orientation, out-of-range and
clipping policies. Post-demosaic linear exposure changes do not simulate physical
capture exposure or sensor noise changes. Record the conversion point and
quantization when a look requires uint8 input.

## Prespecified perturbations

Version one requires exposure and WB gain; spatial tests follow separately.

| Perturbation | Proposed defaults | Purpose |
|---|---|---|
| Exposure | -2,-1,-0.5,0,+0.5,+1,+2 EV | Tone response, reversals, clipping |
| WB gains | R/B each 0.9,1.0,1.1; G=1 | Channel-gain sensitivity, not Kelvin changes |
| Fine exposure | ±0.01 EV around each anchor | Candidate local jumps |
| Repetition | Three identical runs | Determinism and environment variation |
| Spatial, later | 50% downsample and central 75% crop | Scale/crop dependence |

Freeze the grid before execution; do not select favorable ranges after results.
Start with individual axes, then separately test EV {-1,0,+1} crossed with R/B
gains {0.9,1.0,1.1}. Preserve inputs, masks and clipping denominators per combination.

## Measurements

Let f be the registered look, B an identity control using the same conversions and
quantization, T a linear-space perturbation and P the fixed look-input conversion.
Y0=f(P(X)); Yt=f(P(T(X))). Report mean/median/p90 ΔE00(Yt,Y0) as response magnitude,
not accuracy. A smaller response is not inherently better: legitimate exposure
and WB changes should affect outputs. Freeze the common color-space/Lab contract;
treat hue near zero chroma as undefined.

Also report ΔE00(B(P(T(X))),B(P(X))). Differences or ratios of these magnitudes are
sensitivity summaries, not manufacturer accuracy or perceptual quality scores.
Use null ratios when control response is near zero.

Report luminance, ΔL*, ΔC*, clipping fractions and response curves in shadow,
midtone and highlight regions fixed from the original. Do not redefine masks from
each candidate output. Report the complete valid region and a common unsaturated
mask across perturbations; never silently discard increased saturation.

Recheck fine-EV jumps using two-sided differences and denser grids. Quantization
steps also present in uint8 identity controls are not automatically look defects.
Luminance reversals and jumps are reproducible diagnostic candidates, not automatic
failures: intended tone/local processing can produce them.

For spatial tests compare f(P(S(X))) with S(f(P(X))) at matched coordinates and
resolution. The noncommuting residual diagnoses spatial dependence. Nonlinear
global looks may also fail to commute with resampling; zero residual is not a pass
criterion. Include identity and fixed global-curve controls.

## Target boundary

Without SOOC targets, report response, determinism, clipping and execution
contracts only. When original target J exists, keep original NARE error
ΔE00(f(P(X)),J) in a separate table. Without the actual SOOC for T(X), do not use
ΔE00(f(P(T(X))),J) as perturbed manufacturer fidelity. Mathematically transformed
versions of J remain synthetic controls.

## Failures, statistics and falsification

Separate decode failures, unsupported input/candidate, nonfinite output,
shape/channel/dtype violations, missing metadata and metric failures. Declare
monochrome contracts separately; do not apply color-look hue/chroma comparisons.

Only after scene review, aggregate scene summaries equally and use 20,000 scene
bootstrap draws, seed=0. Add session-cluster analysis when needed. Prespecify
primary perturbations and metrics; label the rest exploratory. An extreme found
among many tests is not confirmed by an interval on the same discovery data.
Use separate discovery and confirmation scenes. Without externally justified
response targets, do not declare numerical winners or invent composite scores.

Validate the apparatus with identity, fixed global curve, constant output,
intentional threshold jump, nonfinite-output and repeat-variation controls.
Constant output must reveal information loss even though response ΔE00 is low.
A system that universally rewards low sensitivity fails this control.

## Deliverables and acceptance

Report the twelve-look registry separately from input-camera distribution. For
each look preserve execution/failure counts, exposure/WB curves, clipping,
controls and unsupported combinations. Persist original/derivative hashes,
manifests, decoder/look commit/config, perturbations, environment, per-capture and
per-scene metrics, failure logs and executable commands in a run bundle.

Acceptance tests cover zero-perturbation identity, linear exposure scaling,
derivative split leakage, constant-output detection, threshold jumps, uint8-control
quantization, null zero-denominator ratios, rejection of fidelity claims without
perturbed targets, no CI for unreviewed scenes, separate input/look coverage,
nonfinite-output failures and repeat-result preservation. CARE alone never permits
NARE Supported/Verified or shipping.
