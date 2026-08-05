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
