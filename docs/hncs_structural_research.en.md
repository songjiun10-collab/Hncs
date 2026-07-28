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
clear 10-vs-3 separation gives grounds to try it, but the minority
cluster at only 3 pairs is statistically thin.

Leave-one-out cross-validation (13 runs, each holding out 1 pair and
fitting on the rest) re-measured ΔE (CIEDE2000) for both this
experimental module and `apply_hncs()` (applied to the same raw-derived
baseline, for a fair comparison) on the same 13 pairs.

**Results**: the structural experiment (`apply_hncs_structural`) came in
at a mean ΔE of 10.191, 4.1% below `apply_hncs()`'s 10.629 (winning 6 of
13 folds, losing 7 - the mean improved but a majority of individual folds
did not) - a real but narrow and inconsistent effect.

| Method | Mean ΔE (CIEDE2000) |
|---|---|
| `apply_hncs()` (applied to the raw-derived baseline, re-measured within this experiment) | 10.629 |
| Structural experiment (`apply_hncs_structural`, per-cluster matrix + chroma LUT + shared film curve) | 10.191 |

See the "HNCS Structural Experiment" section of hybrid_engine/EVALUATION.md for full methodology and limitations.

## Limitations

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
