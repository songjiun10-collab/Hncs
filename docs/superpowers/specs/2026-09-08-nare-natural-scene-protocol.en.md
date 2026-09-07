# NARE Protocol

**Natural-scene Appearance Reconstruction Evaluation**

NARE is EAGER's primary real-photo validation protocol. ColorChecker is
supporting colorimetric calibration, while Protocol 2R is the same-physical-scene
cross-camera extension. NARE tests whether manufacturer SOOC JPEG appearance is
reconstructed from RAW under real photographic color, tone, exposure, and texture.

## Data contract and claim boundary

The basic unit is a same-capture `(R_i, J_i)` RAW/SOOC JPEG pair. The manifest
freezes pairing, no-edit status, Picture Style/Film Simulation/Creative Look, WB,
exposure, ISO, lens metadata, and source hashes. NARE supports only the claim that
the observed JPEG appearance was reproduced within the recorded scope; internal
manufacturer algorithm recovery and unobserved-scene generalization need separate
evidence.

## Independence and scene taxonomy

The statistical unit is normally `scene`, not pixels or images:

```text
pixel → ROI → image → scene → session → contributor
```

Record lighting, time, scene type, dynamic range, dominant chroma, exposure, ISO,
skin, foliage, sky, and artificial-light strata, including coverage and untested
conditions.

## Three measurement layers

Global appearance reports mean/median/p90 ΔE00, ΔL*, ΔC*, hue error, and luminance
SSIM. Semantic masks separately report skin, sky, foliage, neutral, saturated
objects, shadow, and highlight. Spatial appearance reports local contrast,
highlight rolloff, shadow compression, edge/local tone, texture/grain, and local
saturation separately from color accuracy.

Register geometry first, build a valid-overlap mask, then evaluate color. Record
crop, distortion/CA/lens correction, rescaling, and threshold failures. Keep
specular highlights and deep shadows as subgroups rather than deleting them.

## Baselines, statistics, and splits

Compare `B0` identity/RAW decoder, `B1` colorimetric foundation, and `C` HNCS
appearance candidate. Compute scene-level `d_s = E_baseline,s - E_candidate,s`,
then use scene-only paired bootstrap and exact sign testing; pixel bootstrap is
forbidden. Evaluate native-ish and 1024px (or 50%) scales.

Use unseen-image, unseen-scene, unseen-session, unseen-contributor, unseen-body,
and unseen-camera-model levels in increasing strength. Keep all derivatives of one
scene in one split. Check lighting, scene, DR, ISO, skin, and saturation strata for
catastrophic regression.

## Ship gate, failures, and role

The minimum gate is sufficient independent scenes, at least 5% mean improvement,
scene bootstrap CI lower bound above zero, paired sign test, no major subgroup
regression, controls, and provenance/accounting. Appearance claims require at
least three lighting conditions and three scene categories. Use the EAGER accounting
reasons `decode_failure`, `pair_mismatch`, `registration_failure`, `edited_jpeg`,
`wrong_picture_style`, `metadata_missing`, `duplicate_scene`, `motion_mismatch`,
`insufficient_overlap`, `clipping_excess`, and `unsupported_raw`.

EAGER supplies claim, evidence, and ship rules; NARE is HNCS's primary validation
path; ColorChecker supplies colorimetric evidence; Protocol 2R extends it to
cross-camera target references. Synthetic smoke results never become photographic
performance claims.
