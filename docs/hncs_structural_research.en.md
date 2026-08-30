# HNCS Structural Research: the real pipeline vs. `apply_hncs()`

*[한국어](hncs_structural_research.md)*

Back to the [main README](../README.md).

`brands/hasselblad.py`'s `apply_hncs()` (⭐ Stable, in production) is a
3-stage simplification of the real HNCS pipeline. This document lays out
the real structure with sources, and records whether a separate
**research-only** experimental module
(`hybrid_engine/research/hncs_structural.py`) that mirrors that structure
actually improves accuracy. `apply_hncs()` itself is not modified by this
research - design rationale:
[2026-07-28-hncs-structural-research-design.md](superpowers/specs/2026-07-28-hncs-structural-research-design.md).

## Sources

- Hasselblad's official site: hasselblad.com/learn/hasselblad-natural-colour-solution
  - Publishes 5 design principles: film-curve tonality, perceptual
    contrast, no rich-saturation manipulation, no skin-tone hue/saturation
    manipulation, consistent application across the X System.
    **Does not disclose the exact pipeline stage count or implementation.**

> **Correction (2026-08-05, verified against the full page text the
> owner pasted directly)**: "no rich-saturation manipulation" and "no
> skin-tone hue/saturation manipulation" above don't match the actual
> page. Verbatim: *"The colour data undergoes a series of
> transformations that remap the captured values. This ensures true
> contrast, **rich saturation**, and tricky subtle tones – like skin
> tones – are kept smooth, even between highlights and shadows."* -
> rich saturation isn't a product of leaving the channel alone, it's
> stated as the **result of the transformation**. The skin-tone
> protection claim appears twice: once in that same passage ("kept
> smooth" during initial rendering), and again in the Phocus
> post-editing section: *"The data is also optimised to keep skin tones
> as unaffected as possible even after applying curves and contrast
> changes."* - that second one means skin tones move **less than the
> rest of the image when you edit curves/contrast afterward**, not that
> initial rendering never touches hue/saturation at all. "No
> manipulation" was an overread.
>
> What the page actually discloses as the pipeline's makeup: **"an
> independently developed Hasselblad look-up-table (LUT), Hasselblad
> Film Curve, and unique colour processing that together adapts to any
> illumination."** The three named pieces (LUT / film curve / other
> processing) line up with this project's 3-stage approximation, but
> the exact algorithm per stage and the illuminant-matrix-selection
> logic remain undisclosed - the "exact stage count/implementation not
> disclosed" conclusion still stands. Newly confirmed facts: (1) the
> camera's own pixel-level sensor calibration is a manufacturing-stage
> correction separate from the colour pipeline ("stringent pixel-level
> calibration"); (2) Phocus offers two working spaces - Hasselblad RGB
> (linear gamma) and Hasselblad L\*RGB (perceptual lightness, covers
> nearly the whole Lab gamut) - plus a "colour calibration tool" for
> user-made custom calibrations; (3) the project started in 2004 during
> medium-format digital camera development.
>
> **`brands/hasselblad.py`'s docstring cites the same "no manipulation"
> phrasing** (the `문서화된 HNCS 설계 원칙 (hasselblad.com):` block,
> items 3-4) - `apply_hncs()` is out of scope for this research document,
> so it wasn't changed here. The near-zero measured hue/saturation
> change is this project's own independent finding (the v8/v9 skin-tone
> hue verification), so it stands on its own regardless - but citing it
> as "because that's the official design principle" is inaccurate and
> needs separate attention.
- blog.tonalphoto.com, "How HNCS Actually Works" - an independent
  technical analysis based on a byte-level diff of Phocus `.phos`
  sidecars. The author explicitly states in the post that this is
  "personal research and testing, not official support or guidance."
  **No official whitepaper exists** - confirmed by search.
- The specific "at least 4 illuminants (Tungsten/Low Tungsten/Flash/
  Flash-Daylight)" figure is itself cited by that blog post from a
  Luminous Landscape forum community technical analysis - not a number
  Hasselblad has published.

The three sources carry different confidence levels: the official site
(design principles, official) > tonalphoto.com (byte-level `.phos` diff,
unofficial but directly measured) > the Luminous Landscape forum citation
(unofficial, second-hand).

## Structural comparison

| Stage | `apply_hncs()` (Stable, in production) | Real HNCS (research findings) |
|---|---|---|
| Input | RAW already decoded to an 8-bit BGR camera JPEG | Raw sensor data (16-bit) |
| 1 | Global exposure lift (`exposure_gamma` LUT, added in v10) | Illuminant-specific 3x3 color matrix - one of at least 4, selected by white balance |
| 2 | CLAHE (perceptual contrast, photo mode only - skipped for video) | Chroma LUT paired with that matrix (hue/saturation correction tuned to that light source) |
| 3 | `film_curve` LUT (toe/mid/shoulder tone curve) | Hasselblad Film Curve (highlight rolloff + shadow transition) |
| On white-balance change | No effect (JPEG input already has WB baked in) | Stages 2 onward fully re-run (matrix + LUT depend on the illuminant) |
| Hue/saturation manipulation | None (the stated principle, applied as-is) | Present - but **not between presets** (see below) |

**The core of the simplification**: the "no skin-tone hue/saturation
manipulation" principle `apply_hncs()` relies on is true *between
presets* - a direct byte comparison of `.phos` sidecars found
Brightness/Contrast/Saturation identical (0/0/0) across all 5 presets
(Standard/Nature/Portrait/Product/Square Crop). But that means presets
don't change the color science relative to each other, not that the
pipeline has no saturation correction anywhere - stage 2 (the
illuminant-specific chroma LUT) is a separate stage that exists
regardless of preset.

## Experiment: does a more accurate structure actually improve ΔE?

`hybrid_engine/research/hncs_structural.py` mirrors the 4 stages above
(RAW-based, WB applied -> cluster-specific 3x3 matrix -> cluster-specific
chroma LUT -> shared film curve). The sample (13 raw+jpeg pairs,
`datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv`) can't support "at
least 4 illuminants," so this was reduced to a 2-cluster split by the
`AsShotNeutral` R/B ratio (`cluster_a`/`cluster_b`, threshold 0.9) - a
10-vs-3 gap gives grounds to try it, but the minority cluster at only 3
pairs is statistically thin, and at n=13 a single gap is not evidence
that two distinct illuminant populations actually exist (all we verified
is that it is *not* a camera-generation artifact - both clusters contain
a mix of X1D and X1D II bodies).

Note that **the film curve, one of the 4 stages, is not fitted**: it is
pinned to `film_curve()`'s defaults (the same values `apply_hncs()` uses)
so that both pipelines share one tone curve. Only three things are
actually determined from data: the matrix, the chroma LUT, and the
cluster assignment.

Leave-one-out cross-validation (13 runs, each holding out 1 pair and
fitting on the rest) re-measured ΔE (CIEDE2000) for both this
experimental module and `apply_hncs()` (applied to the same raw-derived
baseline) on the same 13 pairs.

**Result: a draw (inconclusive).** The structural experiment
(`apply_hncs_structural`) came in at a mean ΔE of 10.191, 4.1% below
`apply_hncs()`'s 10.629 - but **that difference is not distinguishable
from zero.**

| Method | Mean ΔE (CIEDE2000) |
|---|---|
| `apply_hncs()` (applied to the raw-derived baseline, re-measured within this experiment) | 10.629 |
| Structural experiment (`apply_hncs_structural`, per-cluster matrix + chroma LUT + shared film curve) | 10.191 |

- It wins only 6 of 13 folds and loses 7 - two-sided sign test p = 1.000
- The **median** paired difference is −0.078 ΔE, i.e. the opposite sign
  from the mean
- Fold-to-fold standard deviation is 3.978 ΔE; paired t(df=12) = 0.40
- Bootstrap 95% CI on the mean difference: [−1.572, +2.548]; on the
  improvement: [−15.8%, +22.9%] - both straddle zero
- Dropping the single pair `x1d-II-sample-09.jpg` **flips the improvement
  to −2.0%**

So this experiment supports neither "mirroring the structure more closely
improves ΔE" nor the opposite. **The "4.1% improvement" figure must not
be cited as this experiment's conclusion.**

See the "HNCS Structural Experiment" section of hybrid_engine/EVALUATION.md for full methodology and limitations.

## Limitations

- **The experiment cannot isolate the effect of "structure"** - the two
  arms differ in more than stage count: the structural arm decodes
  differently (camera-native + `AsShotNeutral` WB vs. libraw sRGB) and
  **fits** both a 3x3 matrix and the chroma parameters to the targets,
  while `apply_hncs()` learns nothing at all inside this experiment.
  Without a 1-cluster (global matrix) control, any difference cannot be
  attributed to "illuminant-specific structure" rather than simply to
  "a matrix was fitted to the data."
- **The ground truth is not HNCS output** - the targets are JPEGs
  produced by the X1D / X1D II **camera bodies**, whereas the HNCS
  pipeline this document describes is Phocus's desktop RAW rendering.
  Nothing here verifies that the in-camera JPEG engine runs the same 4
  stages. "Mirrors HNCS's structure" and "is closer to real HNCS output"
  are **different claims**; this experiment measures only closeness to
  the camera JPEG.
- **The comparison is not symmetric** - `apply_hncs()`'s
  `exposure_gamma=0.7` and friends were grid-searched against these very
  pairs (10 of them at the time), so it is partly in-sample on every
  fold, which biases against the structural arm. Conversely the
  structural arm inherits its film-curve constants from those same
  hand-tuned values, and the 2-cluster split and its 0.9 threshold were
  chosen after looking at all 13 R/B values - so it is not strictly
  out-of-sample either. Neither bias was quantified.
- **`MATRIX_RIDGE=1.0` is close to a no-op** - fitting on all 3
  `cluster_b` pairs at once (589,824 px), ridge/trace(XᵀX) = 1.2e-5 and
  coefficients move by at most 0.16% (max|ΔM|/max|M| on that pooled fit)
  versus ridge=0.0. The numbers actually recorded come from LOOCV,
  though, where some folds train on only 2 pairs - there the per-
  coefficient change is larger (up to ~9.6% on the `x1d-II-sample-09`
  holdout fold, moving that fold's matrix-stage ΔE by -0.065, from 6.458
  to 6.393) - still negligible next to the 3.978 ΔE fold-to-fold
  standard deviation. The recorded numbers are close to an unregularized
  least-squares fit, and the ridge value does not meaningfully change
  the final result (so no claim of "regularization prevented
  overfitting" is supportable).
- **Differs from Phocus's actual matrix/LUT values** - this is a new fit
  from our own 13 raw+jpeg pairs, not a reproduction of Hasselblad's
  proprietary asset.
- **Research sources are unofficial** - see "Sources" above; information
  of differing confidence levels is mixed together.
- **The 2-cluster model is a reduction of the real structure (4+)** - a
  compromise forced by sample size, not a claim that 2 is correct.
- **13 pairs total, 3-10 per cluster (minority cluster: 3)** -
  statistically thin. Whether the cross-validation result is positive or
  negative, it needs re-checking as the sample grows.
- **Does not replace `apply_hncs()`** - even if this experiment wins, it
  is not promoted to Stable within this plan's scope (that's a separate
  discussion).

## Revalidation (2026-08, 94 local pairs + blending variant + 1024-combo grid)

Re-checked the 13-pair result above ("a draw - 4.1% improvement but the
CI includes 0") at much larger scale. `tools/evaluate_hncs_structural.py`
(new - self-contained reimplementation of
`hybrid_engine/research/hncs_structural.py` +
`tools/evaluate_hncs_structural.py`, since this checkout has no
`hybrid_engine`) expanded two things at once, using the local
dpreview-sourced clean 95 pairs minus one corrupted file
(`4589763049.3fr`) - **94 pairs**:

1. In addition to the existing **hard cluster** split (`AsShotNeutral`
   R/B ratio, threshold 0.9, `cluster_a`/`cluster_b`), a new **continuous
   blending variant** (`compute_blend_weight_rb`, normalizing the R/B
   ratio itself into a blend weight between the two cluster
   matrices/chroma LUTs)
2. The chroma LUT grid was expanded from the original 49 combos
   (`sat_mult`/`hue_shift`, 7 values each) to **1024 combos** (32 values
   each)
3. Switched from LOO (13 runs) to **5-fold CV** (compute cost - LOO over
   94 pairs × 1024 combos is impractical)

The film curve stayed pinned to `apply_hncs()`'s v13 defaults
(`toe_lift=0.005, shoulder_start=0.5, white_point=1.0`), as before.
Cluster split: 88 (`cluster_a`) vs. 6 (`cluster_b`).

**Result: same direction, still inconclusive.**

| Comparison | Improvement | Win/loss | Sign test p | Bootstrap 95% CI | Verdict |
|---|---|---|---|---|---|
| Hard cluster vs `apply_hncs()` | +3.81% (10.355→9.960) | 54/40 | 0.180 | [-0.306, +1.075] | Inconclusive |
| Blend vs `apply_hncs()` | +2.62% (10.355→10.083) | 53/41 | 0.256 | [-0.408, +0.936] | Inconclusive |
| Hard cluster vs blend (direct) | Blend is 1.24% worse (9.960→10.083) | 27/67 | <0.0001 | [-0.187, -0.059] | **Hard cluster wins, significantly** |

Comparing 13 pairs (+4.1%, CI [-15.8%,+22.9%]) against 94 pairs (+3.81%,
CI [-0.306,+1.075]) side by side, both the point estimate and the CI
width tightened (expected with 7x the sample) - but **the sign stayed
consistently positive and the CI still includes 0**, meaning the "weak
but directionally consistent" signal has stabilized just short of
significance rather than resolving either way. The 13-pair warning
("don't cite the 4.1% figure as a conclusion") still holds at 94 pairs.

**New finding - continuous blending is clearly worse than hard
clustering.** This was tested for the first time here, on the hypothesis
that softly blending across the illuminant boundary instead of a hard cut
would be more accurate - the result is the opposite: blending is 1.24%
worse than hard clustering, and this time the CI excludes 0
(statistically significant). If the minority cluster (`cluster_b`, 6
pairs) really does represent a distinct illuminant condition, this
suggests a clean split beats a smooth blend across it - though as
repeatedly noted elsewhere in this document ("Limitations" above), whether
`cluster_b` is genuinely a separate illuminant population has never
actually been verified.

**What this revalidation does not change** in the "Limitations" section
above: the ground truth is still the camera JPEG (not real HNCS output),
the comparison is still asymmetric (`apply_hncs()`'s own parameters were
grid-searched against these same pairs), and this remains a fresh fit
unrelated to Phocus's actual matrix/LUT values - all of that still
applies.

Reproduce: `python3 -m tools.evaluate_hncs_structural` (94 pairs × 1024
combos × 5-fold, ~1 hour).

## Revalidation 2 (2026-08, local pool of 364 pairs, 6 generations) - finally settled, direction reversed

On the user's instruction ("the sample got bigger too, should be
feasible now"), this was re-verified against the full local Hasselblad
raw+jpeg pool gathered via `tools.calibrate.collect_local_pairs()`
(post-dedup-fix) this session - almost 4x the previous 94 pairs (6
generations: X1D 121, X2D 100C 82, X2D II 100C 74, X1D II 50C 38, CFV
100C/907X 29, X1D-50c 20) (`tools/evaluate_hncs_structural_full_pool.py`,
new - `/Users/songjiun/Documents/raw pair` wasn't present locally this
session, so only the loader was swapped for one reading from
`datasets/hasselblad/contributed/*/`; everything else is the same
methodology. The chroma grid was reduced 1024 -> 256 to keep total
compute roughly constant against the larger sample, and since decode was
the bottleneck, all pairs were pre-decoded with a 3-worker
multiprocessing pool before the fold loop ran). Cluster split: cluster_a
354 vs. cluster_b 10.

**Result: this time the CI clears 0 entirely - and the direction
reversed.**

| Comparison | Improvement | Wins/losses | Sign-test p | Bootstrap 95% CI | Verdict |
|---|---|---|---|---|---|
| Hard cluster vs. `apply_hncs()` | **-10.91%** (10.004 -> 11.095) | 128/236 | <0.0001 | [-1.349,-0.849] | **apply_hncs wins** |
| Blend vs. `apply_hncs()` | **-11.46%** (10.004 -> 11.150) | 127/237 | <0.0001 | [-1.404,-0.904] | **apply_hncs wins** |
| Blend vs. hard cluster | -0.50% (11.095 -> 11.150) | 124/240 | <0.0001 | [-0.077,-0.033] | Hard cluster narrowly wins |

13 pairs (+4.1%, CI [-15.8%,+22.9%]) -> 94 pairs (+3.81%, CI
[-0.306,+1.075], direction stayed positive) -> **364 pairs (-10.91%, CI
[-1.349,-0.849], direction flipped negative)**. The CI narrowing as the
sample grew was expected; the sign flipping partway through that
narrowing was not - **the "weak but positive" signal at 13/94 pairs
wasn't a real effect, it was small-sample noise.** The likely
explanation: as diversity grew to 6 generations, the per-cluster
matrix/chroma LUT became easier to overfit to a specific generation/
lighting combination rather than a trait shared across a generation
(cluster_b still being only 10 pairs is part of this too - a matrix
fit to a "handful" cluster doesn't generalize to the majority cluster).

**Settled**: even mirroring HNCS's real "per-illuminant matrix + chroma
LUT" structure (approximated here as a 2-cluster split on the
AsShotNeutral R/B ratio) fails to beat `apply_hncs()`'s simple 3-stage
approximation (global exposure / CLAHE / film curve) - it loses to it,
significantly. This revalidation doesn't change `apply_hncs()` either
(it was always the protected baseline here). This experiment lineage
(`hybrid_engine/research/hncs_structural.py` +
`tools/evaluate_hncs_structural*.py`) is effectively closed by this
result - there's now enough margin (sign test p<0.0001, CI far from 0)
that a still-larger sample flipping the sign back is not a live concern.

**What still doesn't change** in the "Limitations" section above: the
ground truth is still the camera JPEG (not real HNCS output), this is
still a fresh fit unrelated to Phocus's actual matrix/LUT values, and
the 2-cluster split is still a reduction of the real 4-or-more-illuminant
structure - none of that changes just because the sample grew.

Reproduce: `python3 -m tools.evaluate_hncs_structural_full_pool` (364
pairs × 256 combos × 5-fold, ~15 minutes with 3-worker parallel decode).

> **Correction (2026-08, user flagged "hey that's weird, verify it" ->
> checked resolution)**: the result above was produced with decode
> resolution lowered from 512/160 to 256/100 for speed.
> `apply_hncs()` uses CLAHE (`tileGridSize=(8,8)`, fixed), and the actual
> pixel count per tile changes with resolution - lower resolution biases
> the result in `apply_hncs()`'s favor. The structural experiment (matrix
> + chroma LUT + film curve, no CLAHE) has no such bias. Measured
> directly on a 25-pair sample: `apply_hncs()`'s mean ΔE00 is 9.394 at
> 256px vs. 9.646 at 512px (256px favors it by +2.6%) - this doesn't
> account for the whole sign flip (-10.91%), but it's part of it.
>
> Clean numbers, re-verified at the original resolution (512/160):
>
> | Comparison | Improvement | Wins/losses | Sign-test p | Bootstrap 95% CI | Verdict |
> |---|---|---|---|---|---|
> | Hard cluster vs. `apply_hncs()` | **-7.42%** (10.485 -> 11.263) | 148/216 | 0.0004 | [-1.050,-0.526] | **apply_hncs wins** |
> | Blend vs. `apply_hncs()` | **-7.97%** (10.485 -> 11.320) | 151/213 | 0.0014 | [-1.106,-0.583] | **apply_hncs wins** |
> | Blend vs. hard cluster | -0.50% (11.263 -> 11.320) | 126/238 | <0.0001 | [-0.078,-0.036] | Hard cluster narrowly wins |
>
> The margin is narrower than the 256px numbers (-10.91%/-11.46% -
> roughly 3.5 points of that was the resolution bias), but **the
> direction and statistical significance (p<0.005, CI clearly away from
> 0) hold** - "apply_hncs wins significantly at n=364" stands as the
> conclusion. Treat this corrected (512/160) run as the final numbers and
> the 256px ones as a biased draft. Reproduce: `python3 -m
> tools.evaluate_hncs_structural_full_pool` (with DOWNSAMPLE_MAX_DIM=512,
> GRID_DOWNSAMPLE_MAX_DIM=160, ~25 minutes with 3 workers).

## Revalidation 3 (2026-08, KMeans 4-cluster) - still holds even closer to the real structure

The "Limitations" section kept flagging the 2-cluster hard cut (R/B
threshold 0.9) as a reduction of the real HNCS structure ("at least 4
illuminants - Tungsten/Low Tungsten/Flash/Flash-Daylight, matrix
selected by WB"). On the user's instruction ("make it match the real
Hasselblad structure"), the cluster count was raised to 4
(`tools/evaluate_hncs_structural_4cluster.py`, new) - instead of a
manual threshold, AsShotNeutral's (log(R/G), log(B/G)) was standardized
and clustered data-drivenly with KMeans(k=4) (fit once over all pairs,
not per-fold - the same out-of-sample caveat as the 2-cluster version
carries over). "Matrix selected by WB" reads as hard assignment, so the
blend variant was dropped this round. Resolution: 512/160 (per the
correction above). Cluster split: 157/140/57/10.

**Result**:

| Comparison | Improvement | Wins/losses | Sign-test p | Bootstrap 95% CI | Verdict |
|---|---|---|---|---|---|
| 2-cluster hard | -7.42% | 148/216 | 0.0004 | [-1.050,-0.526] | apply_hncs wins (solid) |
| **4-cluster (KMeans)** | **-5.26%** | 163/201 | **0.0523** | [-0.823,-0.302] | apply_hncs wins (CI excludes 0, sign test just misses the conventional 0.05 threshold) |

Going from 2 to 4 clusters narrowed the gap (-7.42% -> -5.26%) - moving
closer to the real structure consistently closes the distance to
`apply_hncs()`, but **the sign never flips**. The 4-cluster CI still
clears 0 (lower bound -0.823) and only the sign test (p=0.0523) just
misses the conventional 0.05 cutoff, making this a somewhat weaker case
than the 2-cluster one - but the 163/201 win/loss split still leans the
same way, so the direction hasn't changed.

**Conclusion**: mirroring more of the real HNCS structure by adding more
clusters still doesn't beat `apply_hncs()` - the gap shrinks, it doesn't
close. A minority cluster (cluster_2, 10 pairs) is still present even at
k=4, so fully closing it might take a larger sample still, but two
independent re-verifications (2-cluster and 4-cluster) both landing on
`apply_hncs()` winning is already a consistent enough signal.
`apply_hncs()` is unchanged by this experiment too.

Reproduce: `python3 -m tools.evaluate_hncs_structural_4cluster` (364
pairs × 256 combos × 5-fold × 4 clusters, ~27 minutes with 3-worker
parallel decode).
