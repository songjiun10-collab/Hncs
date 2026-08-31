# Hasselblad Measurement Conclusions

*[한국어](measurements.md)*

Back to the [main README](../README.md).

As of v12/day-night v3 (see `brands/hasselblad.py`'s docstring).

- **Pixel-level 5-part signature analysis (2026-07, all 124 official samples, genuine originals)**:
  saved to `datasets/hasselblad/{tone,color,texture,gamut}_signature.json` +
  `joint_distribution.npz`. Computed tone/saturation-hue/sharpening-noise-halo/Lab a·b gamut
  pixel-by-pixel against genuine originals (no resize/re-encoding).
  - **Confirmed empirically that you must NOT just pool all pixels and take percentiles**:
    the 124 photos range from 300K to 200M pixels, a 676x spread, so pixel-pooling lets a few
    large photos dominate the statistics (pooled b2 collapses to 1.0, vs. 18.1 for the
    per-photo-equal-weight average - more than a 10x difference). The population target must
    be computed as a "per-photo equal-weight average" - the pooled histogram itself is still
    kept in `joint_distribution.npz`, but it isn't used as the target.
  - **Cross-checked the cache (`downloaded_samples/`, resize + re-encoded) against the genuine
    originals 1:1 for all 124 photos**: over the 94 shadow-valid (dark_pct>5%) photos, black-point
    p2 was 11.27 (cache) vs 10.63 (original) - a 0.6 / 5.7% difference. White-point p99.5 was
    223.85 (cache) vs 225.56 (original) - a 1.7 / 0.8% difference. Both are noise-level
    differences, **confirming the cache did not distort the tone-curve correction target
    (b2/w995)** - the existing target (11.3/223.9) that v9/`apply_hncs` is based on remains valid.
    (Note: during this re-verification, a file-index mapping mistake initially produced a false
    conclusion that "cache vs. original differ by 60%" - this was caught and corrected by
    re-cross-referencing all 124 photos 1:1; the numbers above are the corrected ones.)
  - **Conclusion: no changes needed to `apply_hncs`/day-night parameters.** The tone target was
    already accurate, and saturation/hue/texture/gamut (the color/texture/gamut signatures) are
    channels HNCS was never designed to touch in the first place, so they aren't a "target" -
    they're stored purely as reference data recording what the population actually looks like.
- **Pipeline signature analysis (2026-07, re-downloaded all 124 official samples as genuine
  originals)**: bypassed `downloaded_samples/` (the project's own cache, which distorts noise
  metrics via resize + re-encoding) and freshly `curl`'d all 124 unprocessed originals
  (`/tmp/true_originals/`, 4.5GB) to measure sharpening strength/micro-contrast/noise/edge halo/
  JPEG compression characteristics. The download URL list had 18 overlaps with an earlier
  5-photo pilot sample, which were removed (105 unique). Note, though: the `orig_*.jpg` set
  (124 photos, 1:1 with CSV rows) that was actually used for the population statistics and the
  day/night v3 correction has no internal duplicates at all - the existing recalibration results
  are unaffected.
  - JPEG quality: 77% (81/105) are Q99 · YCbCr 4:4:4 (effectively lossless), with a minority
    (17 photos, filenames suggesting early X1D-series bodies) at Q75 · 4:2:0. The brand filter
    itself doesn't re-encode to JPEG, so this figure is reference metadata only.
  - Sharpening energy (mean absolute high-frequency value, median 2.65) and micro-contrast
    (DoG std, median 6.37) are strongly correlated (r=0.77) - a signal of a consistent local-
    contrast processing style. However, since these values are self-referential statistics
    between finished JPEGs rather than a paired comparison against an unprocessed original,
    there's no baseline to quantify how much stronger they are than a neutral render → judged
    insufficient grounds to add a new sharpening parameter to the curve module, deferred.
  - Edge halo (overshoot): the median is essentially flat across quality tiers (7-8%, Q<=80 /
    81-95 / >95 all similar) - the "lower quality → bigger halo" pattern seen in the 5-photo
    pilot disappears once the sample grows (the mean spikes because of a few extreme outliers,
    irrelevant on a median basis). Correlation with sharpening energy is also weak (r=0.24).
    Outliers (orig_133 at 129.9%, orig_68 at 45.6%, etc.) appear to be genuine specular-highlight
    edges misdetected as halo - reconfirming the existing caveat that this metric can't
    distinguish JPEG ringing / genuine halo / a scene's own bright reflections.
    → halo-based parameters also deferred
  - Noise: per-file variance is extreme (0.001-6.6) and the per-subsampling-group means overlap
    heavily (4:2:0 0.34 / 4:4:4 1.19 / 4:2:2 0.32, n=7-81), so it isn't explained by chroma
    subsampling or JPEG quality - reconfirming the existing conclusion that it's scene-content-
    dependent (ISO, light level, texture). No grounds for a new brand-wide fixed grain/denoise
    parameter.
  - **Conclusion**: even scaling the sample up to the full 124 photos, none of
    sharpening/halo/noise produced a signal clean and confident enough to say "encode this value
    as a new parameter in the code." Per the project's existing overfitting-avoidance principle,
    decided not to change `brands/hasselblad.py` - the real output of this analysis is the
    evidence-backed conclusion that "not changing anything is correct."
- **Re-verification (2026-07, after the brands/core/tools refactor)**: re-ran `apply_hncs`
  (parametric) and `apply_hncs_learned` (learned) through `tools.calibrate grid_search`/
  `learn_curve` and confirmed the RMSE reproduces exactly as before the refactor
  (23.31→16.51 for grid_search, 23.31→15.41 for learn_curve) - there are still only 10 raw+jpeg
  pairs (the rest are dead links), so there's no new data to recalibrate against
- **day/night v3**: built a contact sheet from all 124 official samples and reviewed each one by
  eye, picking out 12 unambiguous night scenes (streetlights/neon/aurora/Milky Way/city night
  views, etc.) and reclassifying the remaining 112 as day (v2 had only 5 day + 4 night samples).
  New targets: day black-p2=11.5/white-p99.5=224.1 (n=112), night black-p2=9.7/white-p99.5=221.3
  (n=12) - a much larger sample than v2, and it converges (even more so) toward the overall
  population target (11.3/223.9). `apply_hasselblad_day` was refit against the new target
  (midtone_gamma 0.95→0.85, contrast_n 1.15→1.35, white_point 0.96→0.92, RMSE 22.01→18.65);
  `apply_hasselblad_night`'s grid search landed back on the existing defaults as optimal, no
  change. The case for keeping day/night as separate presets keeps weakening (not yet merged)

- Over the full pool of 124 official samples: black-p2=11.3, white-p99.5=223.9; the portrait
  subset (43 photos) is 10.2/226.3 - no major shift from v8 (19-20 photos)
- Automated verification on the 43 portrait photos found skin-tone hue is essentially unchanged
  before/after `apply_hncs` (mean |delta|=0.21, max 2.0, on a hue scale of 0-179)
- Grid-searching against genuine raw→JPEG before/after pairs (10 photos) revealed the curve had
  no global exposure/gamma correction step (`exposure_gamma`), so it couldn't close the
  brightness gap between the pre/post-grading images (v10) → added an `exposure_gamma`
  parameter, excluded an extreme high-key sample (an indoor Oculus shot with no shadows) from
  the black-point fit, and re-searched (v11)
- Final adoption (`apply_hncs`, v11): applied `white_point=1.0`, `exposure_gamma=0.7`, kept
  `toe_lift`/`shoulder_start` at their original values (0.001/0.78) - RMSE improved from 36.3 to
  23.3. Lowering the shoulder start point to 0.5 drops RMSE further to 16.5, but with only 8
  shadow-valid samples, changing the curve's shape itself was judged an overfitting risk and
  deferred
- Tried switching the raw-rendering baseline to a linear gamma (1,1), which seemed more
  "accurate" on paper, but RMSE actually got worse (23.3→28.2) - rawpy's own demosaic/color-
  matrix algorithm differs from Hasselblad's actual pipeline, so getting "closer to the sensor"
  didn't help (a negative result, reverted)
- `apply_hncs_learned` (v12): without assuming a toe/shoulder shape, learned the
  neutral_L→target_L mapping directly from raw+jpeg pairs at the pixel level (10.78 million
  pairs) - RMSE 15.4, better than the parametric version's 23.3. The sample-size constraint
  (still only 10 raw+jpeg pairs) remains the same, and the hue error introduced by the round-
  trip through 8-bit conversion is slightly larger than `apply_hncs`'s (mean |delta|~3.0/179,
  still visually negligible)
- Tried regularizing the learned LUT toward the parametric curve out of concern for the small
  sample, but a 10-fold leave-one-out cross-validation showed the pure unregularized empirical
  LUT performs best (LOO RMSE 14.6, getting worse - 20.7→28.0 - as regularization strength
  increases) - because there are enough pixel samples per bin that variance isn't the problem;
  the parametric curve's own shape bias is the bigger source of error. `apply_hncs_learned` is
  kept without regularization
- **Another expansion attempt (2026-07) - all negative results.** Investigated whether any
  usable source exists beyond the 124 photos.
  - Directly parsed `hasselblad.com/learn/sample-images/`'s X/H/V system gallery pages down to
    the Storyblok CMS `page-data.json` and cross-checked against the existing 124 photos
    (139 CSV rows) - zero new files. The official source is already saturated.
  - Hasselblad's official Instagram posts (verified 8 user-supplied screenshots) - EXIF is
    entirely stripped by platform re-encoding, and one of the posts turned out to be
    sponsored/edited content - unusable.
  - explorecams.com (500px-sourced) X1D gallery, all 51 listed photos (1 detail page 404'd,
    50 checked) - full EXIF verification: 44% Lightroom/Photoshop-edited, 36% completely
    stripped EXIF, 14% Instagram re-encoded, and only 6% (3 photos) looked like genuine SOOC -
    and all 3 of those were from the same photographer (Raymond Cheung). Too small and too
    non-diverse a subset to add to the population - excluded.
  - imaging-resource.com's X2D 100C review gallery (the same source already used for the other
    4 population-fit brands) - all 45 non-edited candidates came back corrupted on
    imaging-resource.com's own CDN ("Premature end of JPEG file", reproduced byte-for-byte via
    both curl and urllib) - zero survivors. See "Image trustworthiness policy" in
    `docs/methodology.en.md` for details.
  - dpreview.com's sample galleries (`/samples/album/hasselblad-*`) - the galleries themselves
    exist, but the site is behind a Cloudflare bot challenge (`cf-mitigated: challenge`,
    confirmed to be dpreview.com's own origin response, not a proxy policy block), so automated
    scraping isn't possible - excluded without attempting to bypass it.
  - **Conclusion**: there is no known path to grow the sample beyond 124 photos right now.
    `apply_hncs`/`apply_hncs_learned`/day-night parameters remain unchanged.

## External review incorporated (2026-07, GitHub issue #4)

An X2D II user reviewed the methodology in detail and raised several points. Every one of
them checked out against the actual code and data:

- **The 124-photo sample isn't 100% hasselblad.com official**: 99 of 124 are tagged
  `hasselblad.com (공식)`, 25 are `cameralabs.com (신뢰 서드파티)` - `run_hasselblad()`
  never filters on the `source` column, it just pools everything. Recomputed from the cached
  `csv_stats_result.csv`: full pool black-p2 = 11.27 (matches the number already in the docs)
  vs. official-only = 10.60 - a 0.67 (6%) difference, similar in magnitude to the
  already-documented "noise-level" cache-vs-original gap (0.6, 5.7%), so not a dramatic
  distortion - but the docs' "124 official photos" framing was still inaccurate.
- **`genuine_render_check()` (detects Photoshop/Lightroom/Phocus third-party edits) is wired
  into the 4 imaging-resource.com brand paths but not into `run_hasselblad()`** - confirmed.
  Digging further: all 124 cached files have an empty EXIF Software tag - not because they're
  free of Phocus editing, but because `_hasselblad_download()` strips EXIF entirely via its
  `cv2.imwrite` resize-and-resave step, so this couldn't have been verified either way with the
  current cache. Whether Phocus-rendered/edited exports are actually mixed in remains an open
  question - would need a fresh EXIF-preserving redownload to check. Still unresolved.
- **Per-generation population was never documented**: `run_hasselblad()` already prints a
  per-generation (X1D/X2D/907X·CFV) breakdown to the console, but it never made it into the
  docs. Recomputed from the cache:

  | Generation | n (shadow-valid) | Black p2 | White p99.5 |
  |---|---|---|---|
  | X2D line | 74 (63) | 9.7 | 224.8 |
  | X1D line | 11 (9) | 13.1 | 227.8 |
  | 907X/CFV | 39 (22) | 14.9 | 221.0 |

  Black-p2 spreads from 9.7 to 14.9 across generations - a real spread. The "design judgment"
  that pooling across generations is fine may have been more optimistic than this table
  supports.
- **All 13 raw+jpeg calibration pairs are X1D/X1D II generation - zero from the X2D line** -
  confirmed. `apply_hncs` is applied uniformly across the X system on the premise of "one
  consistent color philosophy across generations," using a curve learned entirely from X1D
  pairs on a population target that's 62% X2D by photo count - and that premise has never
  actually been checked against real X2D raw data.
- **The raw rendering baseline depends on libraw's default demosaic/camera-matrix**
  (never characterized via a least-squares matrix from a color chart) - a fair point. The
  "switching to linear gamma made RMSE worse" experiment (recorded above) was itself evidence
  of this uncertainty, but the cause was never pinned down explicitly as "the raw pipeline
  itself isn't characterized."

### Phocus contamination re-verification results (2026-07)

Range-fetched the first 256KB of all 139 originals (pre-resize) and re-checked the EXIF
Software tag on every one - the existing 124-photo cache couldn't be checked this way at all,
because `_hasselblad_download()`'s `cv2.imwrite` resave strips EXIF entirely (that function
turned out to be the actual root cause). Results:

- **34 photos (24%) carry an Adobe Photoshop/Lightroom/Camera Raw Software tag** - clearly
  third-party edited. Issue #4's concern was correct.
- 6 carry a plain version string (`1.1.6.3`/`3.1.0`/`3.0.0`, Make=Hasselblad,
  Model=X2D/X2D II) - same pattern seen in the earlier explorecams.com verification (recorded
  above), read as the camera's/Phocus's own renderer signature rather than an editing tool, so
  not classified as edited.
- 84 have no Software tag at all (can't tell whether that's genuinely unedited or stripped
  during upload to Hasselblad's CMS - "unverified," not "confirmed clean").
- 3 hit HTTP 403 (likely rate-limiting) - unverified.

**Recomputed the population excluding cameralabs.com and confirmed-Adobe-edited photos**
(n=124 -> n=65, nearly halved):

| | n (shadow-valid) | Black p2 | White p99.5 |
|---|---|---|---|
| Currently shipped (full pool) | 124 (94) | 11.3 | 223.9 |
| Cleaned (official + non-edited only) | 65 (50) | 10.9 | 224.4 |

The gap is 3% for black-p2, 0.2% for white-p99.5 - smaller than the ~5-7% this project has
already treated as "noise level" several times over. **Conclusion: contaminated samples really
were mixed in, but they didn't meaningfully distort the population targets** -
`apply_hncs`/`apply_hncs_learned` parameters are left unchanged (consistent with the
anti-overfitting principle already in place).

Also recomputed the per-generation breakdown on the cleaned 65-photo set:

| Generation | n (shadow-valid) | Black p2 | White p99.5 |
|---|---|---|---|
| X2D line | 48 (38) | 10.2 | 227.0 |
| X1D line | 4 (4) | 11.8 | 229.0 |
| 907X/CFV | 13 (8) | 14.1 | 213.3 |

The X1D subset drops to just 4 photos - too thin to draw a conclusion from. The
cross-generation pooling question (point 3 above) remains open, and its root cause remains
that the raw+jpeg calibration pairs are X1D-only - the offered X2D II pairs are the only
realistic path to closing that gap.

**Code fix**: added an EXIF Software check (`_check_genuine_bytes()`) to
`tools/analyze.py`'s `_hasselblad_download()`, applied to the raw bytes *before* the resize
step, so re-running `python3 -m tools.analyze hasselblad` now automatically excludes
Photoshop/Lightroom-edited photos and prints the exclusion count. cameralabs.com is not
hard-excluded (the table above shows its distorting effect is noise-level, too weak to justify
excluding a whole third-party source) - the `source` column is already in the CSV if anyone
wants to filter on it later.

The X2D II raw+jpeg pair contribution is proceeding separately (see the GitHub issue #4
thread).

## First real cross-generation pooling test via a local contributed dataset (2026-08, local-mixed-2026-07)

The gap left open above - "no way to test the cross-generation pooling premise because every
raw+jpeg pair is X1D" - was finally closed using raw+jpeg pairs from the project owner's own
personal photo library. Unlike the public web-scraping attempts above ("Another expansion
attempt"), these are files the owner already owns, so there's no licensing question standing in
the way.

**Methodology** (`tools/build_local_manifest.py`, new):
- Match raw/jpeg as "same shutter" when EXIF `DateTimeOriginal` agrees within 2 seconds (same
  tolerance `tools/verify_contributed_pairs.py` already uses)
- Found mid-matching: 8 X1D raw files from a 2017 shoot had `DateTimeOriginal` recorded exactly
  **7 hours** ahead of their jpeg siblings (minute and second matched exactly - a pattern that's
  essentially impossible by chance). Likely the camera/firmware stamped raw and jpeg against
  different timezone references. Added an integer ±12-hour offset search so pairs like this
  aren't missed (though these particular 8 turned out to have Lightroom-edited jpegs anyway and
  were excluded regardless, see below)
- Of 104 candidate pairs, `verify_contributed_pairs` **passed 61 (59%) and failed 43 (41%)** -
  every failure was a Photoshop/Lightroom trace in the jpeg's EXIF Software tag (the same order
  of contamination rate as the explorecams.com check above (44%) and the re-verification pass
  (24%)). Without this filter, the calibration would have measured Lightroom's color science
  instead of Hasselblad's

**Generation breakdown of the 61 passing pairs** - the first real X2D/907X·CFV raw+jpeg pairs
this project has ever had:

| Camera | n |
|---|---|
| CFV 100C/907X | 30 |
| X2D 100C | 24 |
| X1D II 50C | 6 |
| X1D | 1 |

Re-ran `python3 -m tools.calibrate learn_curve` on official 13 pairs (all X1D-line) + local 61
pairs = 74 total. RMSE broken down by generation:

| Camera | n | Parametric (v11) RMSE | Learned LUT (v12) RMSE |
|---|---|---|---|
| CFV 100C/907X | 30 | 10.82 | 19.11 |
| X2D 100C | 24 | 19.15 | 19.64 |
| Official samples (X1D line) | 13 | 22.38 | 23.09 |
| X1D II 50C | 6 | 41.89 | 37.17 |
| X1D | 1 | 8.25 | 32.45 |
| **Overall** | **74** | **19.94** | **22.20** |

**Re-check (2026-08, re-run after excluding 9 edit-contaminated pairs
from the official 13)** - the 9 edit-contaminated pairs confirmed in the
correction under "First check against a real Phocus render" above
(irrelevant for the local 61 - `verify_contributed_pairs` already
filtered on the same criterion, rejecting 43 of 104 candidates for
exactly this reason, see "Methodology" above) are now excluded in
`tools/calibrate.py`'s `_resolve_pairs()` (the `_CONTAMINATED_OFFICIAL_PAIRS`
constant). Re-ran `learn_curve` on the resulting 65 pairs (4 clean
official + 61 local):

```
Parametric (v11) RMSE=19.11
Learned LUT RMSE=21.85
```

74 pairs (contaminated included) 19.94 vs 22.20 → 65 pairs
(contaminated excluded) 19.11 vs 21.85 - **the conclusion's direction is
unchanged** (v11 still beats v12), and both improve slightly (read as:
comparing against a cleaner ground truth improves the apparent fit for
either model). Didn't re-run the per-generation breakdown this time
(reproduce with the same command above).

**Conclusion - the cross-generation pooling premise is rejected by measurement.** On the
original 10-pair, X1D-only sample, `apply_hncs_learned` (v12) beat the parametric curve (RMSE
15.4 vs 23.3, recorded above). Once real X2D/CFV data is added, that reverses - on CFV
100C/907X specifically, the parametric curve is almost 2x better (10.82 vs 19.11). A LUT trained
purely on X1D pairs was overfit when applied to other generations - confirming, for the first
time with actual raw data, a concern this project could previously only flag and not test.
**`apply_hncs` (parametric v11) stays the shipped default.** `apply_hncs_learned` isn't adopted
in its current pooled form since its cross-generation premise doesn't hold; per-generation
learned LUTs might still beat the parametric curve within a single generation (untested - each
generation only has on the order of 30 pairs so far, not attempted this round).

Reproduce: `python3 -m tools.build_local_manifest <source dir> datasets/hasselblad/contributed/local-mixed-2026-07`
to add pairs, then `python3 -m tools.calibrate learn_curve` to retrain.

**Hybrid (regularize) re-check (2026-08)** - re-ran `tools/calibrate.py`'s
`regularize` mode (the v11↔v12 ridge hybrid, `lut = (sums + λ·prior)/(counts + λ)`)
on the same 74 pairs as the two re-checks above. Best λ=1e9 (effectively pure
parametric) - LOO RMSE decreased monotonically from 33.61 at λ=0 (this λ=0
arm isn't v12 itself - it's `_build_lut_from_counts`'s mean-based,
prior-backfilled approximation of it; v12 itself is median-based with
`np.interp`) to 22.18 at λ=1e9 (a 34.0% reduction on the overall LOO RMSE),
with no intermediate point ever beating the endpoint. Significance test,
best (=v11) vs v12 (λ=0): 46.4% improvement on a paired per-fold basis, 60
wins/14 losses, sign-test p=0.000, bootstrap 95% CI [+35.5%, +56.4%]
(excludes 0) - same direction as the learned-LUT re-check above (19.94 vs
22.20), though the absolute numbers aren't directly comparable since this
script uses its own percentile-based LOO error, not the same metric.
Per-generation RMSE breakdown (at λ=1e9 - this table also uses this
script's own LOO-percentile error, so it isn't directly comparable to the
v11/v12 table above either. E.g. CFV 100C/907X is 15.37 here vs 10.82 in
the v11 column above, even though λ=1e9 is effectively pure v11):

| Camera | n | Hybrid (λ=1e9) RMSE |
|---|---|---|
| CFV 100C/907X | 30 | 15.37 |
| X2D 100C | 24 | 13.37 |
| Official samples (X1D line) | 13 | 27.40 |
| X1D II 50C | 6 | 48.77 |
| X1D | 1 | 31.48 |

**Conclusion: the hybrid doesn't help.** v11 already beats v12 by a wide
margin, so there's no upside to blending them, and the grid search itself
confirms that quantitatively. Reproduce: `python3 -m tools.calibrate regularize`.

## v11 parameter recalibration - 65-pair grid search + LOO validation, actually adopted (2026-08)

All the re-checks above kept `apply_hncs()`'s **existing parameters**
fixed (toe_lift=0.001, shoulder_start=0.78, white_point=1.0,
exposure_gamma=0.7 - the values adopted back in v10/v11) and only
compared v12/the hybrid against them. This time the parameters of
`apply_hncs` itself were re-searched on the 65 pairs (4 clean official +
61 local-contributed).

**Step 1 - in-sample grid search** (modified `tools/calibrate.py`'s
`run_grid_search()` to use `_resolve_pairs()` (65 pairs) instead of
`collect_pairs()` (13 official only); same parameter grid as before:
7 exposure_gamma values x 3 toe_lift x 7 shoulder_start x 3 white_point =
441 combinations):

| | exposure_gamma | toe_lift | shoulder_start | white_point | RMSE |
|---|---|---|---|---|---|
| Existing defaults | 0.7 | 0.001 | 0.78 | 1.0 | 19.11 |
| Grid search optimum | 0.8 | 0.0 | 0.5 | 1.0 | 13.56 |

**Caveat**: this 13.56 is an in-sample number - parameters fit on the 65
pairs, then measured on the same 65 pairs - so it can't rule out
overfitting. And this particular shoulder_start≈0.5 is exactly the value
v11's original history (`brands/hasselblad.py` docstring) held back on
adopting, over overfitting risk with only 8 shadow-valid samples. So it
went through leave-one-out validation before adoption.

**Step 2 - leave-one-out validation** (new `run_grid_search_loo()` -
computes the 65-pairs x 441-combos error matrix once, then for each fold
picks the combo with the lowest mean error over the other 64 pairs via
subtraction, and evaluates only on the held-out pair -
`TestFoldBestComboMatchesRecompute` confirms the subtraction result
matches full recomputation, the same pattern as
`TestSubtractionLooMatchesRecompute`). The comparison baseline (A) is the
**existing parameters as-is** - never fit on these 65 pairs, so already
out-of-sample:

- Mean error: existing 14.948 -> LOO-optimized 9.960 (**33.4%
  improvement**)
- Fold win/loss: LOO-optimized wins 55, loses 8, ties 2 (ties at zero
  error)
- Sign test (two-sided) p < 0.001
- Bootstrap 95% CI (improvement): [+26.0%, +40.5%] (excludes 0)
- Drop-one sensitivity: improvement stays within 32.5%-35.3% (sign never
  flips)
- **64 of 65 folds converge on the exact same combo**
  (exposure_gamma=0.8, toe_lift=0.0, shoulder_start=0.5, white_point=1.0);
  the remaining fold differs only in exposure_gamma (0.9) - not being
  dragged around by a handful of pairs.

**Conclusion - adopted.** This clears every bar in
`hybrid_engine/CLAUDE.md`'s statistics rules (paired t-test, sign test,
bootstrap CI, drop-one), and the original overfitting concern from v11's
history is judged resolved now that the sample grew from 8 to 65 pairs
across 4 generations. Actually updated `apply_hncs()`/
`apply_hncs_video_frame()`'s defaults in `brands/hasselblad.py`
(exposure_gamma 0.7->0.8, toe_lift 0.001->0.0, shoulder_start 0.78->0.5,
white_point unchanged at 1.0) - see that file's docstring for the full
rationale. Confirmed the full test suite (613 tests) still passes.

Reproduce: `python3 -m tools.calibrate grid_search` (in-sample) /
`python3 -m tools.calibrate grid_search_loo` (LOO validation).

### Independent check - re-confirmed with ΔE00 (real photos + a ColorChecker chart) (2026-08)

The 33.4% above is the b2/w995 percentile error `grid_search_loo` uses (the
grid search's own objective), not this project's standard ΔE00 (CIEDE2000)
metric. So the old and new parameters were run through `apply_hncs()`
directly and measured with ΔE00 two more times.

**1) Against the 65 real-photo target.jpg files** (same method as
`hybrid_engine.utils.evaluate` - sRGB cctf_decoding, then Lab, CIEDE2000):

| | Mean ΔE00 |
|---|---|
| Existing parameters | 7.457 |
| New parameters | 6.861 |
| Improvement | 8.0% |

53 wins/12 losses, sign test p<0.001, bootstrap 95% CI [+3.9%,+12.2%],
drop-one 7.6%-8.8%.

**2) A ColorChecker Classic chart** (kmichels-x2dii-2026-07, 9 X2D II 100C
raws, contributed via GitHub issue #4 - isolates the pure tone-curve effect
with no scene-content/framing variance). Auto-detected the 24 patches via
`hybrid_engine.core.chart_baseline` (detected once on the neutral render
and reused the same coordinates for both old/new, so detection noise
doesn't confound the comparison), compared against the official
spectrophotometric reference values:

| | Mean ΔE00 (24 patches) |
|---|---|
| Existing parameters | 7.927 |
| New parameters | 6.563 |
| Improvement | 17.2% |

9 wins out of 9, sign test p=0.004, bootstrap 95% CI [+12.6%,+21.4%],
drop-one 16.1%-18.0%.

**Per-patch breakdown (chart, pooled across 9 images)** - not a uniform
improvement:

| Patch | Existing | New |
|---|---|---|
| dark skin | 7.778 | 5.192 |
| light skin | 7.646 | 6.224 |
| blue sky | 7.162 | 5.565 |
| foliage | 6.358 | 4.040 |
| blue flower | 8.968 | 8.331 |
| bluish green | 7.994 | 8.517 |
| orange | 5.677 | 2.618 |
| purplish blue | 8.143 | 5.065 |
| moderate red | 10.501 | 7.301 |
| purple | 6.908 | 5.222 |
| yellow green | 4.609 | 3.712 |
| orange yellow | 2.880 | 3.725 |
| blue | 3.267 | 4.032 |
| green | 9.564 | 4.812 |
| red | 9.695 | 6.614 |
| yellow | 3.493 | 3.554 |
| magenta | 9.978 | 7.516 |
| cyan | 14.319 | 9.162 |
| white 9.5 (.05 D) | 11.586 | 10.796 |
| neutral 8 (.23 D) | 11.115 | 11.742 |
| neutral 6.5 (.44 D) | 10.197 | 11.758 |
| neutral 5 (.70 D) | 9.311 | 8.491 |
| neutral 3.5 (1.05 D) | 8.133 | 7.088 |
| **black 2 (1.5 D)** | **4.964** | **6.425** |

**Conclusion**: all three metrics (33.4%/8.0%/17.2%) point the same
direction but at very different scales - the grid search's objective
function overstates the real perceptual improvement. Most patches (dark
skin, foliage, orange, green, cyan, etc.) improved substantially, but
**the darkest patch (black 2) actually got worse** (4.964 -> 6.425), and
neutral 6.5/8, bluish green, blue, and orange yellow also regressed
slightly - exposure_gamma going from 0.7 to 0.8 (less midtone lift) seems
to push some dark or near-neutral patches the wrong way. The adoption
decision stands (it wins consistently and statistically at the
mean/fold level) - but it did not improve every tone/color uniformly.

Reproduce: the chart raws come from
`datasets/hasselblad/contributed/kmichels-x2dii-2026-07/manifest.csv`'s
download_url (Google Drive, via gdown) - both scripts are one-off (not in
the repo).

## First check against a real Phocus render (2026-08)

Until now, `apply_hncs()`'s ground truth has always been the camera's own
embedded JPEG (`raw_calib_cache/*.target.jpg`), never the output of Phocus
itself (Hasselblad's official desktop RAW converter). For the first time,
all 13 `raw_calib_cache` pairs were run through real Phocus 4.1.1
(`brew install --cask phocus`) - Import → (default Standard preset, no
adjustments) → Export - to get genuine HNCS-rendered TIFFs. See
`hncs_external_sources_analysis.en.md` section 6 for how this came about.

**Method**: decode each RAW to a "raw/neutral" baseline using the same
recipe as `tools/calibrate.py`'s `load_neutral_render()`
(`rawpy.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8,
gamma=(2.222, 4.5))`), feed that into `apply_hncs()`, then compare all
three images (camera-JPEG target / real Phocus render / `apply_hncs()`
output) pairwise with `hybrid_engine.utils.evaluate.mean_delta_e`
(CIEDE2000). All three are downsampled to a 512px long edge before
comparing, for memory - the same `DOWNSAMPLE_MAX_DIM` convention the
`evaluate_*.py` scripts already use (global-statistics ΔE isn't distorted
by downsampling).

| Pair | target vs apply_hncs | target vs real Phocus | real Phocus vs apply_hncs |
|---|---|---|---|
| 00378 | 5.195 | 2.573 | 5.395 |
| 02709 | 11.684 | 2.929 | 11.248 |
| B0000994 | 10.333 | 11.437 | 6.230 |
| B0001395 | 16.931 | 21.277 | 12.603 |
| x1d-II-sample-01 | 8.422 | 5.844 | 8.112 |
| x1d-II-sample-02 | 11.566 | 6.707 | 11.419 |
| x1d-II-sample-06 | 9.647 | 3.309 | 11.404 |
| x1d-II-sample-09 | 16.356 | 6.905 | 22.427 |
| x1d-ii-xcd45p-01 | 9.336 | 5.028 | 8.088 |
| x1d-ii-xcd45p-02 | 9.909 | 6.219 | 11.682 |
| x1d-xcd45-01 | 12.047 | 4.115 | 14.885 |
| x1d-xcd45-03 | 4.247 | 3.897 | 3.264 |
| x1d-xcd45-04 | 3.364 | 3.443 | 3.109 |
| **Mean (n=13)** | **9.926** | **6.437** | **9.990** |
| **Median** | **9.909** | **5.028** | **11.248** |

**Reading this**:
- **target vs real-Phocus (mean 6.44) is lower than target vs apply_hncs
  (mean 9.93)** - as expected, the desktop Phocus render sits closer to
  the camera's embedded JPEG (both genuinely HNCS) than our parametric
  approximation does. It isn't a perfect match either (not 0) - there's a
  real difference between the desktop render and the in-camera one
  (firmware/Phocus-version differences, or possibly some of these 13
  `target.jpg` files carrying edit contamination themselves - like the
  "Phocus contamination re-check" case in
  `hncs_external_sources_analysis.en.md`, these 13 pairs have never been
  individually checked for that).
- **real-Phocus vs apply_hncs (mean 9.99) is essentially the same as
  target vs apply_hncs (9.93)** - swapping the ground truth from the
  camera JPEG to an actual Phocus render doesn't change the conclusion
  (there's still a real gap between our approximation and genuine HNCS).
- **B0000994/B0001395 are clear outliers** (target vs real-Phocus is
  11.4/21.3, 2-4x every other pair) - only 2 of 13, but enough to skew the
  overall mean. Without separately confirming whether these two
  `target.jpg` files are genuinely unedited camera renders (the same
  concern as above), the headline averages shouldn't be trusted too
  precisely.
- **Small sample (n=13), and this is a one-off measurement** - no
  bootstrap/sign-test-grade statistics from `hybrid_engine/CLAUDE.md` were
  applied, since this isn't an "A beats B" verdict, just a descriptive
  record of the size of the gap.

Reproduce: Import all 13 `raw_calib_cache/*.3FR`/`*.fff` files into Phocus
(default Standard preset) → Export as TIFF, then combine
`tools/calibrate.py`'s `load_neutral_render()` with
`hybrid_engine.utils.evaluate.mean_delta_e` and
`hybrid_engine.utils.io.load_image_linear` (the one-off script that
produced this table lived in session scratch space, not the repo).

**Housekeeping**: importing `raw_calib_cache/` directly into Phocus leaves
new `*.phos` sidecar files in that folder (Phocus's own adjustment-state
files) - `raw_calib_cache/` is already `.gitignore`d so these never reach
a commit, but noting that they exist locally.

> **Correction (2026-08-03, found by actually checking the "these 13
> pairs have never been individually checked" concern above)**: checked
> the `target.jpg` EXIF `Software` tag on all 13 `raw_calib_cache` pairs -
> **9 of 13 carry a third-party editing software tag**, the first time
> this check has ever been run on `apply_hncs()` (v11)'s own original
> calibration dataset:
>
> | Pair | Software tag |
> |---|---|
> | 00378 | none (presumed clean) |
> | 02709 | none (presumed clean) |
> | B0000994 | Adobe Photoshop CC 2018 (Windows) |
> | B0001395 | Adobe Photoshop CC 2018 (Windows) |
> | x1d-II-sample-01 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-II-sample-02 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-II-sample-06 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-II-sample-09 | Adobe Photoshop CC 2019 (Macintosh) |
> | x1d-ii-xcd45p-01 | none (presumed clean) |
> | x1d-ii-xcd45p-02 | none (presumed clean) |
> | x1d-xcd45-01 | Adobe Photoshop Lightroom Classic 8.0 (Macintosh) |
> | x1d-xcd45-03 | Adobe Photoshop Lightroom Classic 8.0 (Macintosh) |
> | x1d-xcd45-04 | Adobe Photoshop Lightroom Classic 8.0 (Macintosh) |
>
> "No Software tag" is "unconfirmed," not "confirmed unedited," for the
> same reason as the "Phocus contamination re-check" section above -
> though at minimum it means no obvious edit trace, so these 4 are
> treated as "clean" below.
>
> **ΔE00 recomputed on just the 4 clean pairs**
> (00378/02709/x1d-ii-xcd45p-01/02, alongside the n=13 table - n=4 is
> reference only, not a replacement):
>
> | | target vs apply_hncs | target vs real Phocus | real Phocus vs apply_hncs |
> |---|---|---|---|
> | Mean (n=4, clean) | 9.031 | 4.187 | 9.103 |
> | Median (n=4, clean) | 9.623 | 3.978 | 9.668 |
> | Mean (n=13, all) | 9.926 | 6.437 | 9.990 |
>
> The direction doesn't change (target-vs-apply_hncs is still bigger than
> target-vs-real-Phocus even on just the 4 clean pairs) - but n=4 proves
> essentially nothing statistically, so the point of this correction isn't
> "the conclusion changed." It's that **this is the first time it's been
> confirmed that 9 of the 13 pairs `apply_hncs()` v11 was trained on may
> have gone through editing software** - a far more fundamental issue than
> this Phocus comparison itself, and whether v11 needs recalibrating is a
> separate decision outside this document's scope (`apply_hncs()` itself
> was not touched this session).

## White Patch / Shades of Gray auto-white-balance accuracy (2026-08)

Measured how accurate `tools/raw_pipeline.py --auto-wb-mode
{white_patch,shades_of_gray}` (new, in `core/log_pipeline.py`) actually is
against the camera's real AsShotNeutral (DNG spec, treated as ground
truth) across the 13 `raw_calib_cache` RAWs (real-world photos, not color
charts).

**Method**: decode each RAW twice - (a) `use_camera_wb=True` (the
camera's real WB, the reference) and (b) `use_camera_wb=False`
(uncorrected). Apply `estimate_wb_white_patch`/`estimate_wb_shades_of_gray`
to (b) to get the two estimated renders, and compare each against (a) with
ΔE00 (CIEDE2000, in ProPhoto RGB Linear - `hybrid_engine.utils.
evaluate.mean_delta_e` assumes sRGB so doesn't apply to this module; same
logic copied for ProPhoto). Also measured the R/G, B/G channel-ratio
(the white-balance gain itself) relative error against AsShotNeutral as a
secondary metric.

| Pair | ΔE00 (white_patch) | ΔE00 (shades_of_gray) |
|---|---|---|
| 00378 | 14.72 | 5.23 |
| 02709 | 21.06 | 21.67 |
| B0000994 | 13.92 | 18.30 |
| B0001395 | 23.53 | 24.71 |
| x1d-II-sample-01 | 16.75 | 7.19 |
| x1d-II-sample-02 | 6.50 | 7.57 |
| x1d-II-sample-06 | 26.07 | 17.56 |
| x1d-II-sample-09 | 20.14 | 22.00 |
| x1d-ii-xcd45p-01 | 8.15 | 10.42 |
| x1d-ii-xcd45p-02 | 4.28 | 7.67 |
| x1d-xcd45-01 | 14.14 | 11.83 |
| x1d-xcd45-03 | 22.54 | 24.74 |
| x1d-xcd45-04 | 13.56 | 3.66 |
| **Mean (n=13)** | **15.80** | **14.04** |
| **Median** | 14.72 | 11.83 |

R/G+B/G relative error % (secondary metric): white_patch mean 100.1%
(median 78.8%), shades_of_gray mean 95.7% (median 101.6%) - same
direction as ΔE00 (both large, shades_of_gray marginally better).

**Conclusion**: this project treats ΔE00 < 2.0 as "imperceptible to the
human eye" - an average of 14-16 is **an obviously different color
cast**. Both algorithms depend on the assumption that the scene contains
a genuinely neutral (white/gray) surface, which breaks down often on
`raw_calib_cache` since it's real photos, not color charts - white_patch
in particular fully saturates its channel ratio to 1.000/1.000 whenever a
bright colored surface (glass, sky, a light source) dominates the frame
(B0001395, x1d-xcd45-03, x1d-II-sample-09 hit 150-214% relative error on
the R/G,B/G metric for exactly this reason). **Not recommended for real
use** - not a substitute for the camera's own white balance, only useful
for experimenting with a "different feel" in a creative workflow with no
illuminant information available. Reproduce: repeat the method above
across all 13 `raw_calib_cache` files (one-off script, not in the repo).

**Related finding (a different subsystem)**: this failure isn't new -
it's a re-confirmation of a limitation this project already knew about.
`hybrid_engine/EVALUATION.md` ("Protocol 2: Cross-camera generalization"
section, around follow-up measurements 12-19) extensively measured Gray
World (the "the whole scene averages to neutral" assumption) and its
variants (robust/percentile, luma-zoned, strength-tuned) as well as Gray
Edge (spatial-derivative-based, van de Weijer 2007) for `hybrid_engine`'s
own color-cast correction stage, and reached the same conclusion - a
global "the scene is roughly neutral" assumption breaks down structurally
on night scenes and color-dominated real photos (removing Gray World
entirely made ΔE nearly double, 9.687 -> 18.431, so having *some* version
was better than none - but every attempt to refine it further stayed
within a meaningless +0.7%). White Patch/Shades of Gray just tried the
same global neutral-surface assumption with a different algorithm and hit
the same wall. It's the same class of problem as the metamerism
limitation already stated in README.md ("...the sensor's spectral
sensitivity isn't exactly proportional to the CIE standard observer...
the residual can only be reduced via a ΔE loop").

## Trying to lower ΔE00 - both ideas failed (2026-08)

Tested two ways to lower the result above (mean 14-16):

1. **Exclude high-saturation pixels** (`robust_divisor`): drop pixels with
   saturation (`(max-min)/max`) above 0.15 from the set used to estimate
   the white/gray reference, then recompute (falls back to the full set
   if fewer than 100 pixels remain). The idea: stop saturated primary-color
   surfaces from masquerading as a "fake neutral."
2. **Ensemble**: simply average the white_patch and shades_of_gray
   divisors, hoping their different failure modes would cancel out.

Reproduced on the 13 `raw_calib_cache` files (ΔE00 against camera_wb, mean):

| Method | Mean | Median | Min | Max |
|---|---|---|---|---|
| white_patch | 15.80 | 14.72 | 4.28 | 26.07 |
| **shades_of_gray (previous best)** | **14.04** | 11.83 | 3.66 | 24.74 |
| white_patch + saturation exclusion | 15.84 | 14.72 | 4.28 | 26.07 |
| shades_of_gray + saturation exclusion | 14.44 | 11.83 | 3.66 | 27.23 |
| ensemble (original divisors) | 14.33 | 12.86 | 5.68 | 24.06 |
| ensemble (saturation-excluded divisors) | 14.50 | 12.86 | 5.68 | 24.06 |

**Conclusion**: neither helps. Saturation exclusion barely changed the
divisor for most pairs (most scenes already have few pixels above 0.15
saturation), and the one pair where it changed a lot,
x1d-II-sample-09, got worse (22.00 -> 27.23). The ensemble just lands
between white_patch (15.80) and shades_of_gray (14.04) at 14.33 - the
failure modes don't cancel, they just average out. Plain
shades_of_gray (p=6) alone remains the best option, so **no parameter
or algorithm change** - `estimate_wb_white_patch`/
`estimate_wb_shades_of_gray` are left as-is.

## Is noise the cause of the high ΔE00? - No (2026-08)

Measured why the output looks excessively noisy, and how much that noise
actually contributes to the ΔE00 (14-16) measured above.

**Cause of the noise**: shades_of_gray divides each channel by a
different divisor (= a different gain per channel). Comparing the
standard deviation in the same shadow region (camera_wb's bottom 5-30th
luma percentile, the identical mask applied to all three variants) shows
the gain amplifies R by 1.4x, G by 1.9x, B by 1.0x relative to camera_wb
on x1d-II-sample-09.jpg.3FR - a basic signal-processing fact: **a
channel's gain proportionally amplifies that channel's own sensor
noise**. `raw_to_prophoto_linear` applies pure division (gain) with no
noise-suppression step at all (a real camera ISP/Phocus applies WB gain
and noise reduction together), so this amplification shows through
directly.

**Is noise the main driver of the ΔE00 gap?** Checked in two stages.

1. **Single pair** (x1d-II-sample-09, shades_of_gray's worst case at ΔE00
   =22.00): Gaussian-blur both the camera_wb and shades_of_gray images
   (removes noise while preserving color/structure) and recompute ΔE00.
   No blur 22.01 -> 5px 21.96 -> 15px 21.88 -> 31px 21.81 -> 61px (heavy)
   21.76 - even wiping out essentially all the noise only drops it 1.1%.
2. **All 74 pairs** (13 official + 61 local-contributed, via
   `tools/calibrate.py`'s `collect_pairs()` + `collect_local_pairs()` -
   no jpeg target is used here so the EXIF contamination filter is
   irrelevant), comparing the full per-pixel ΔE00 distribution before/after
   a 61px blur (camera_wb vs shades_of_gray):

   | | mean | median | p90 | p99 | max | % pixels ΔE00>20 |
   |---|---|---|---|---|---|---|
   | No blur | 11.37 | 11.29 | 15.93 | 19.28 | 26.50 | 16.74% |
   | 61px blur | 11.77 | 11.66 | 15.70 | 18.38 | 19.78 | 17.35% |

   Per-file mean ΔE00 change: mean **-3.90%** (i.e. blur makes it
   slightly *worse* on average), median -3.32%, range -13.92% to +2.35% -
   73 of 74 files stayed flat or got worse; only 1 improved.

**Conclusion**: on both the single pair and the much larger 74-pair
sample, blurring away the noise does not lower mean/median ΔE00 (on the
74-pair sample it makes the mean slightly worse on average) - **the
"noise causes the high ΔE00" hypothesis is rejected**. p99/max do drop
noticeably with blur (19.28 -> 18.38, 26.50 -> 19.78) - a handful of
extreme noisy pixels are real, but the bulk of the error at the mean
level is pure systematic color-cast (the "global neutral-assumption
breakdown" from the section above), not noise. The noise amplification
itself is a real, separate image-quality issue worth noting, but it's
unrelated to lowering these algorithms' ΔE00. Reproduce: both scripts are
one-off (not in the repo), method exactly as described in the tables
above.

## Does splitting by generation beat pooling? (2026-08)

Actually broke v11's "pool the whole X system into one curve" design (fit
each generation separately) to see whether it does better within that
generation. Based on 74 pairs (CFV 100C/907X 30, X2D 100C 24, X1D II 50C
6, X1D 1, official X1D-series 4 - the last three skipped, below the
minimum-10 sample threshold).

**v11 (parametric) side - `grid_search_loo_per_generation`** (grid search
+ LOO within the generation only; baseline is the existing pooled
defaults, never fit on this generation):

| Generation | n | Existing (pooled) | Generation-only | Improvement | Sign test p | Bootstrap CI | Verdict |
|---|---|---|---|---|---|---|---|
| CFV 100C/907X | 30 | 6.445 | 5.665 | 12.1% | 0.036 | [-3.2%,+27.7%] | Inconclusive |
| X2D 100C | 24 | 9.018 | 7.392 | 18.0% | 0.011 | [+1.3%,+33.2%] | B (generation-only) wins |

X2D 100C's generation-only optimum is exposure_gamma=0.9 (everything else
matches the current defaults: toe_lift=0.0, shoulder_start=0.5,
white_point=1.0) - re-checked with real ΔE00 on just the 24 X2D 100C
pairs (against target.jpg, CIEDE2000):

| | Mean ΔE00 |
|---|---|
| Pooled (current defaults) | 5.341 |
| X2D 100C-only (exposure_gamma=0.9 only) | 5.001 |
| Improvement | 6.4% |

18 wins/6 losses, sign test p=0.023, bootstrap 95% CI [+2.4%,+10.4%]
(excludes 0), drop-one 5.8%-7.4% - smaller than the grid search's own
metric suggested (18.0%), but a real, statistically solid win. That said,
the only parameter difference is exposure_gamma 0.8->0.9, and shipping it
would require camera-generation detection logic `apply_hncs()` doesn't
have today (a real break from the design philosophy) - not adopted this
round, recorded only.

**v12 (learned LUT) side - `regularize_per_generation`** (pure empirical
LUT, lam=0, trained via LOO within the generation only, vs the fixed
parametric v11):

| Generation | n | v11 (fixed) | v12 (generation-only LOO) | Improvement | Win/loss | Sign test p | Bootstrap CI | Verdict |
|---|---|---|---|---|---|---|---|---|
| CFV 100C/907X | 30 | 12.212 | 34.147 | -179.6% | v12 4W/26L | 0.000 | [-339%,-92%] | v11 wins decisively |
| X2D 100C | 24 | 11.855 | 4.682 | +60.5% | v12 15W/9L | **0.307 (not significant)** | [+40.4%,+73.3%] | B (v12) wins (see caveat below) |

**Don't take the X2D 100C result at face value**: the bootstrap CI
excludes 0, but the sign test isn't remotely significant (p=0.307 - 15
wins out of 24 isn't statistically distinguishable from 50/50). The
median improvement (+1.752) being far smaller than the mean (+7.173) is
the same signal - a handful of pairs won by a huge margin and dragged the
mean/CI up, not a consistent edge across most pairs. `summarize()`'s
automatic verdict only looks at the bootstrap CI, so it says "won" - but
factoring in the sign test, this case is too weak to call a clean win.

**Exactly which X2D 100C pairs does v12 win?** (direct per-pair v11/v12
error comparison across the 24 pairs): ISO/scene_type isn't the
explanatory variable here (unlike CFV - both v11 and v12 wins show up
within ISO 64 daylight). Instead there's a clear pattern: **the 11 pairs
v12 won by a large margin (+14 to +26) all had large v11 error to begin
with (11.67-32.06), and the 9 pairs v11 won all had small v11 error to
begin with (0.29-7.89)**. In other words, the fixed curve already fits
X2D 100C's "typical" exposures/scenes well, but is systematically way off
for a specific exposure pattern - and that subset misses in a similar
way, so a LUT learned from the other photos fixes exactly those cases
(while nudging the already-good cases slightly worse as they get folded
into the average). It's not "most pairs improve a little" - it's "a few
get fixed a lot, the rest stay flat or regress slightly" - which explains
why the sign test wasn't significant.

**Why CFV is so bad**: cross-referencing the manifest's ISO column shows
CFV's 30 pairs span ISO 64-25,600 (median 1200, 20 lowlight/10 daylight),
far wider and skewed toward high ISO than X2D 100C's 24 pairs (ISO
64-1,600, median 64, 14 daylight/10 lowlight). v12 (lam=0) uses the
**mean** target_L across pairs for each neutral_L bin - ISO 64 and ISO
25,600 get very different in-camera noise reduction and tone compression,
so folding them into one L->L mapping produces a compromise curve that
fits neither well. High-ISO sensor noise itself also jitters each bin's
mean (the same class of problem as the "channel gain amplifies sensor
noise" finding earlier in this session). X2D 100C is almost entirely
low-ISO, so this problem is far weaker there - the same mechanism running
in opposite directions for the two generations.

**Conclusion**: splitting by generation gives a different answer for each
generation (CFV gets worse if split; X2D 100C improves, but the evidence
is weak) - neither is clean enough to adopt right now. `apply_hncs()`
stays as-is. Reproduce: `python3 -m tools.calibrate
grid_search_loo_per_generation` / `regularize_per_generation`, both
auto-skip generations under min_n=10.

## Chromatic aberration (`chromatic_aberration`) LOO experiment - a clean null result (2026-08)

Tested whether rawpy's `raw.postprocess()` `chromatic_aberration=
(red_scale, blue_scale)` parameter (default (1,1) = no correction) for
lateral chromatic aberration reduces ΔE00. Reproduced the original spec
(`docs/superpowers/specs/2026-07-31-chromatic-aberration-correction-design.md`,
13 pairs, X1D-only) at larger scale using the local dpreview-sourced
clean 95 pairs (4 generations: CFV/X2D/X2D II/X1D II; X1D excluded - only
1 clean sample) via `tools/evaluate_chromatic_aberration.py` (new -
self-contained, since this checkout has no `hybrid_engine`).

**Method**: rawpy decode with `half_size=True` (speed) and `gamma=(1,1)`
pure linear. Grid search over 9×9=81 `(red_scale, blue_scale)` combos
(0.98-1.02, 0.005 step). Each combo is encoded to sRGB and compared
against the camera JPEG via ΔE00 (CIEDE2000, skimage); LOO (pick the
combo with the lowest mean ΔE00 over the other 94 files, evaluate on the
held-out file) gives an out-of-sample estimate. **Sanity check**: verified
`chromatic_aberration` actually changes the image under `half_size=True`
(it could in principle be a no-op internally) - decoding the same file at
(0.98,0.98) vs (1.02,1.02) gave `mean|diff|=1374.6` (vs 1390.0 under
`half_size=False`, essentially the same effect size) - the parameter is
genuinely active.

**Result: a clean null.** Excluding one corrupted file
(`4589763049.3fr`, CFV), the LOO-optimal combo converged to exactly
`(1.0, 1.0)` (no correction) for **all 94** valid pairs - zero exceptions.

| | Value |
|---|---|
| Mean ΔE00, no correction | 9.436 |
| Mean ΔE00, LOO-optimal correction | 9.436 (identical) |
| Win/loss/tie | 0/0/94 |
| Improvement | 0.000% |

Bootstrap CI / sign test are moot here - every per-pair difference is
exactly zero, so the variance is also zero. This is an unambiguous
negative result.

**Conclusion**: within this parameter range (±2%), correcting chromatic
aberration at the raw-decode stage does not reduce ΔE00 against the
camera JPEG at all. The original spec's premise - that lateral chromatic
aberration is a meaningful component of the color error - is rejected on
this dataset (4 generations, 94 pairs). `apply_hncs()` is untouched (same
rationale as the original spec - this experiment is scoped to the raw
decode stage, unrelated to the tone-curve stage).

Reproduce: `python3 -m tools.evaluate_chromatic_aberration` (95 pairs ×
81 combos, ~1 hour).

## v13: 135-pair dpreview revalidation (5 gens incl. X2D II) - candidate (2026-08)

Below is the full history behind the "candidate" side of `apply_hncs()`'s
two competing parameter sets. This narrative used to live only in the
docstring of a separate branch (`claude/hncs-v13-apply-hncs-candidate`)
of `brands/hasselblad.py`; it was ported here before that branch was
cleaned up. The parameter values themselves were already compared against
main in the "exposure_gamma head-to-head" section below - this section is
the record of the **process** that produced them.

Re-validated `apply_hncs` against real raw+jpeg pairs pulled from
dpreview.com's review sample galleries. **Note: an earlier working draft
mislabeled this data as "the owner's own photography" - it was actually
review-site samples (confirmed directly via the download-source URL in
macOS's kMDItemWhereFroms xattr, corrected here)** - v8 through v12 were
all constrained to either official samples (mostly already-graded images)
or a mere 10 raw+jpeg pairs (mostly X1D), and this data largely lifted
that constraint.

**How the data was sourced**: 5 dpreview.com galleries (one camera per
gallery, distinguished by the `sample_galleries/L-<ID>/` URL path) - X1D
(60 photos), X1D II 50C (12), X2D 100C (49), CFV 100C/907X (83), and
**X2D II 100C (83)**. Raw<->jpeg pairing used EXIF `ImageUniqueID` as the
primary match with a `DateTimeOriginal` fallback (raw/jpeg sometimes mix
ISO8601 T-separated and EXIF colon-separated formats like
`2022:09:20 21:47:30`, so format normalization was required - skipping it
silently drops valid pairs, which happened once and was recovered). The
X2D II gallery was missed entirely at first (downloaded but never moved
into the working folder) - 135 pairs total (by camera: CFV 34, X1D 30,
X2D 24, X1D II 6, X2D II 41), one excluded for a raw-decode I/O error,
n=134 used.

**Re-ran grid_search (n=134, all 5 generations)**: optimum at
exposure_gamma=0.7, toe_lift=0.005, shoulder_start=0.5, white_point=1.0
(RMSE 19.87; evaluating the real v11 parameters on the same 134 pairs
gives RMSE 23.00). **shoulder_start=0.5 is the single most confidently
established conclusion here** - it came out optimal with zero exceptions
across every subset tried (88, 94, 134 pairs) - confirming that the value
v11 deferred on ("only 8 shadow-valid samples, overfitting risk") was
right all along. exposure_gamma reverted to v11's original value (0.7),
and toe_lift's 0.001->0.005 move is effectively negligible - so this
revalidation's only real change is shoulder_start 0.78->0.5.

**Splitting the grid search by body (5 generations) to re-test the
pooling assumption itself** - this is where an important counterexample
surfaced:

| Generation | n | Body-only optimum | RMSE (body-only) | RMSE (real v11) |
|---|---|---|---|---|
| CFV 100C/907X | 33 | eg=0.9, tl=0.0, ss=0.5, wp=1.0 | 7.41 | 11.69 |
| X2D 100C | 24 | eg=0.9, tl=0.0, ss=0.5, wp=1.0 | 9.90 | 19.27 |
| X1D | 30 | eg=0.6, tl=0.0, ss=0.5, wp=1.0 | 22.36 | 27.80 |
| X1D II 50C | 6 | eg=0.6, tl=0.0, ss=0.5, wp=1.0 | 30.39 | 41.94 |
| **X2D II 100C** | **41** | **eg=0.3, tl=0.02, ss=0.82, wp=0.95** | 14.15 | 24.06 |

CFV/X2D/X1D/X1D II unanimously agree on shoulder_start=0.5, toe_lift=0.0,
white_point=1.0 (only exposure_gamma varies by generation, 0.6-0.9) -
which looked like it supported design principle 5 ("pooling across body
generations still surfaces a stable, common X-System color science").
**But X2D II - the largest single generation (n=41) - wants a completely
different shape**: shoulder_start=0.82 (closer to v11's original 0.78),
exposure_gamma=0.3 (less than half the other generations'), white_point=0.95.

**Root-cause investigation - 8 hypotheses tested**: using
`docs/hncs_external_sources_analysis.md` sections 1-2 (a Konrad Michels
blog-based reverse-engineering writeup confirming HNCS auto-selects and
blends among at least 4 illuminant-specific 3x3 matrices by white
balance, none of which `apply_hncs` models) as a starting thread, tested
8 hypotheses in order:

1. EXIF `AsShotNeutral` R/B ratio (illuminant bias) - rejected: X2D II
   (0.661) and CFV (0.663) are nearly identical, yet their optimal
   exposure_gamma is opposite (0.3 vs 0.9)
2. Neutral-render-to-target brightness gap - rejected: X2D II (+44.3) and
   X1D (+41.1) are similar, yet optimal exposure_gamma differs (0.3/0.6)
3. Blown-highlight fraction (w995>=254) - rejected: X2D II (4.9%) is
   actually lower than CFV (12.1%)/X2D (20.8%)
4. **Edit contamination (jpeg EXIF Software) - confirmed, decisive**:
   96.7% (29/30) of X1D pairs and 32.4% (11/34) of CFV pairs are
   Lightroom/Camera Raw exports - the same class of contamination
   `docs/measurements.md`'s "Phocus contamination re-verification"
   section above flagged, found here for the first time in this dataset
   too. X2D/X2D II/X1D II were 100% genuine (only firmware version
   strings, no Adobe signature)
5. Lens diversity (EXIF LensModel) - all 41 X2D II photos use **a single
   lens** (XCD 35-100E, zoom position varies only), vs. 2 for CFV and 4
   for X2D - X2D II is far more uniform
6. Shooting period - X2D II's shots span 11 days (mildly at odds with a
   single-session theory)
7. Exposure-compensation (EV) habit - X2D II averages **0.00** (no
   compensation used), while CFV/X2D/X1D run -1.15 to -1.78 (an
   underexposure-for-highlight-protection habit) - X2D II stands out
   distinctly
8. Coefficient of variation of target JPEG saturation within generation
   (a scene-diversity proxy) - X2D II is lowest at 22.0% (CFV 46.4%, X2D
   33.0%, X1D 29.5%) - the most uniform shooting style

**Re-ran the per-body grid search on the clean 95 pairs (excluding the 40
edit-contaminated pairs out of 135, 30%) per finding #4** - X1D's clean
sample collapses to just **1**, statistically meaningless (expected given
96.7% contamination); CFV drops from 34 to 22. X2D/X2D II were
uncontaminated to begin with, so their results are unchanged:

| Generation | n (clean) | Body-only optimum |
|---|---|---|
| X2D 100C | 24 | eg=0.9, ss=0.5 (same as before contamination filter) |
| CFV 100C/907X | 22 (down from 34) | eg=0.9, ss=0.5 (**unchanged even after removing contamination**) |
| X1D II 50C | 6 | eg=0.6, ss=0.5 (had no contamination, unchanged) |
| X1D | 1 (collapsed from 30) | statistically meaningless |
| X2D II 100C | 41 (unchanged) | eg=0.3, ss=0.82 (**still an outlier**) |

So the shoulder_start=0.5 consensus was not an illusion created by
contaminated data - it holds on clean data (X2D/CFV/X1D II) too - and
X2D II remains a solid counterexample. That said, the original framing of
"4-generation consensus vs. X2D II alone" was itself inaccurate (X1D's
sample was down to 1, uncountable to begin with). Weighing findings
5/6/7/8 (single lens, uniform exposure-compensation habit, low scene
diversity) together, the most plausible explanation is **"the 41 X2D II
photos are, in effect, a correlated sample from one reviewer's one
shooting period (a shooting-style artifact, not a camera-generation
difference) - so their true independence is lower than it looks
statistically"** - but a genuine camera-generation difference can't be
fully ruled out either (both possibilities remain open; distinguishing
them needs additional X2D II raw+jpeg pairs from a different reviewer).

**origin (main) already had much deeper related work** - it had already
run essentially the same "does pooling across generations hold up"
experiment on local raw+jpeg pairs (CFV 30/X2D 24/X1D II 6/X1D 1, 61
pairs) and reached the same-direction conclusion (the parametric curve
beats the learned LUT, by almost 2x on CFV - see the "First empirical
test of cross-generation pooling with a local-contributed dataset"
section above). But main had no real X2D II raw+jpeg photo pairs at that
time (`kmichels-x2dii-2026-07/` is only a ColorChecker burst - the same
chart shot 10 times over 94 seconds, no scene diversity) - the 41 X2D II
photos from dpreview (real, diverse scenes) were data main didn't have
either. main had already least-squares fit a camera-to-XYZ 3x3 matrix
from the X2D II ColorChecker chart, getting ΔE00 7.58->2.78 (-63.3%,
`datasets/hasselblad/contributed/kmichels-x2dii-2026-07/colorchecker_matrix_report.json`),
but had never applied that matrix to real, diverse scenes rather than the
chart itself.

**Cross-validated the ColorChecker matrix against the 41 real X2D II
photos**: applied main's chart matrix (`chart_matrix_in_sample`, taken
verbatim from the report above) to a raw pure-linear decode (`rawpy`,
`gamma=(1,1)`, `use_camera_wb=True` - the same color-space definition as
`hybrid_engine/utils/io.py`'s `decode_raw()`, with `half_size=True` only
for speed), then compared against the real camera JPEG via ΔE00 (n=41):

| | Mean ΔE00 |
|---|---|
| No correction (linear->sRGB gamma only) | 13.48 |
| Chart matrix only | 12.76 (-5.3%) |
| apply_hncs tone curve only (no matrix) | 11.23 (-16.7%, best) |
| Chart matrix + apply_hncs tone curve | 12.32 (-8.6%) |

The chart matrix does generalize somewhat to real (non-chart) scenes
(-5.3%, not pure noise). But the apply_hncs tone curve alone does better,
and **simply chaining the two (matrix, then tone curve) is actually worse
than the tone curve alone** (11.23->12.32) - the matrix and the tone
curve were each tuned under different assumptions (the former on
pure-linear input; apply_hncs's tone curve is fit assuming
gamma-2.222/4.5 neutral-render input), so naively chaining them doesn't
work - they'd need to be re-fit together to get any synergy. This session
didn't attempt that joint re-fit; it only confirmed that chaining the two
corrections independently has no support.

**ΔE2000 cross-check (88 pairs, 4 generations, X2D II excluded)**:
re-measured with scikit-image CIEDE2000

| | Mean ΔE00 | Median |
|---|---|---|
| apply_hncs (real v11) | 7.05 | 6.33 |
| apply_hncs (candidate, ss=0.5 applied) | 6.80 | 5.67 |
| apply_hncs_learned (88-pair LUT) | 8.09 | 7.67 |

The direction matches RMSE, but the improvement is much smaller (~19%
RMSE reduction vs. ~3.5% ΔE00 reduction) - apply_hncs only touches the L
channel's tone curve and leaves hue/saturation alone, so the tone curve
can only ever explain a small share of total ΔE00 (an expected result).

## exposure_gamma head-to-head by generation - main vs candidate (2026-08)

`apply_hncs()` currently has two independently re-calibrated candidates
(see the v13 history in `brands/hasselblad.py` and the "v11 parameter
recalibration" section above for full background):

- **main (origin, currently shipped)**: `toe_lift=0.0,
  shoulder_start=0.5, white_point=1.0, exposure_gamma=0.8` - fit on 65
  pairs (4 clean official + 61 local-contributed); X2D II was only
  represented by 9 ColorChecker chart raws, no real photos
- **candidate (local v13, separate branch)**: `toe_lift=0.005,
  shoulder_start=0.5, white_point=1.0, exposure_gamma=0.7` - fit on 135
  dpreview pairs (5 generations), including 41 real X2D II photos

`shoulder_start`/`white_point` already agree, so the only real point of
disagreement is `exposure_gamma` (0.8 vs 0.7). `tools/evaluate_exposure_gamma_x2dii.py`
(new) put both candidates head-to-head on **the 95 clean dpreview pairs
including the 41 X2D II photos** - a combination neither candidate had
seen before. Since both parameter sets are fixed (no fitting), this is a
paired comparison, not LOO - reused `tools/calibrate.py`'s `summarize()`
(sign test, paired t, bootstrap 95% CI, drop-one) as-is.

| Generation | n | Result | Sign test p | Bootstrap 95% CI (improvement) |
|---|---|---|---|---|
| CFV 100C/907X | 22 | **main wins** - candidate 88.8% worse | <0.001 | [-140.4%, -46.7%] |
| X2D 100C | 24 | **main wins** - candidate 93.5% worse | <0.001 | [-157.1%, -55.2%] |
| X1D II 50C | 6 | Inconclusive (candidate +15.1%, small n) | 0.688 | [-3.5%, +23.8%] |
| **X2D II 100C** | **41** | **candidate wins** - 24.8% improvement | <0.001 | [+18.0%, +29.7%] |
| Pooled overall | 94 | Inconclusive (candidate +10.5%) | 0.251 | [-3.7%, +18.4%] |

**Conclusion: exposure_gamma splits in opposite directions by
generation.** `exposure_gamma=0.8` (main) wins decisively for CFV/X2D
(both p<0.001, CI entirely negative, excluding 0), while
`exposure_gamma=0.7` (candidate) wins decisively for X2D II (p<0.001, CI
entirely positive, excluding 0). **The pooled "inconclusive" result comes
from these two opposite signals cancelling out**, not from genuine
uncertainty about which parameter is right - neither main nor candidate
is a "global answer" that covers all 5 generations, and **this experiment
rejects the premise that a single `exposure_gamma` can serve the whole X
System pool**. This is the first time the unresolved suspicion left by the
X2D II grid search in the v13 history above ("can't rule out a real
camera-generation difference") gets confirmed as a statistically
significant, opposite-direction signal against CFV/X2D.

`apply_hncs()` is not changed by this experiment - whether to introduce a
per-generation branch is a separate decision. Reproduce: `python3 -m
tools.evaluate_exposure_gamma_x2dii` (95 pairs, ~5 min - reuses
`tools.calibrate.load_neutral_render`/`gray_stats`).

### X2D II-only parameters, LOO/5-fold - inconclusive (2026-08)

The table above compared **two fixed parameter sets** (main vs.
candidate) against each other. Separately, tested - within the 41 X2D II
pairs alone - whether a generation-only grid-searched parameter set beats
the pooled main default, using the same methodology as
`tools.calibrate.run_grid_search_loo_per_generation`
(`tools/evaluate_x2dii_generation_loo.py`, new - 441-combo grid; all 41
pairs are clean, no contamination filter needed).

**LOO (41 outer folds)**: 36.0% improvement (RMSE 19.88->12.73), 27
wins/14 losses, sign test p=0.060, bootstrap 95% CI [+18.6%,+49.1%], 39/41
folds converge to the same combo (eg=0.3, tl=0.02, ss=0.82, wp=0.95) -
the CI alone says "won," but the sign test falls just short of the
conventional 0.05 threshold.

**Re-checked with 5-fold (5 outer folds, shrinking the training set from
40 to ~33)** - since all 441 candidates are fixed constants (nothing
adaptively fit), adding an inner CV layer wouldn't change the numbers (the
outer LOO is already leak-free), but shrinking the training set gives a
more conservative check of selection stability:

| | LOO (n=41) | 5-fold (n=41) |
|---|---|---|
| Improvement | 36.0% | 34.7% |
| Win/loss | 27/14 | 24/17 |
| **Sign test p** | **0.060** | **0.349** |
| Bootstrap 95% CI | [+18.6%, +49.1%] | [+16.9%, +47.9%] |
| Combo chosen per fold | 39/41 identical | splits 25/41 vs 16/41 (ss=0.82 vs 0.5) |

**LOO's "near-significance" wasn't stable.** Shrinking the training set
from 40 to ~33 was enough for 2 of the 5 folds to pick a different combo
(shoulder_start=0.5), and the sign test p jumps to 0.349, losing
significance entirely. The improvement/CI still point the same direction
(both methods' CIs exclude 0), but with only 41 samples the grid
selection itself is this sensitive to training-set size - the claim that
"an X2D II-only parameter set is statistically a clear win" doesn't
survive the more conservative check.

**Verdict: inconclusive.** The direction (X2D II wants a different curve
than the other generations) shows up consistently across several
independent signals this session (the 8-hypothesis investigation above,
the per-generation main-vs-candidate head-to-head, this LOO/5-fold check)
- but it isn't statistically robust enough to justify adopting an X2D
II-only parameter set. The 41-pair sample size itself is the limiting
factor. **Revisit once more X2D II raw+jpeg pairs from a different
reviewer/shooting session are available.** Reproduce: `python3 -m
tools.evaluate_x2dii_generation_loo`.

#### Verdict resolved after expanding the sample (41->63->70 pairs), shoulder_start corrected (2026-08)

The additional X2D II raw+jpeg pairs this section was waiting on arrived
in two batches - apparently the rest of the same dpreview gallery (same
lens, XCD 35-100E), all with a Software tag that's just a firmware
version string (no Adobe signature), so no edit contamination. The
original 41 photos all used 0.00 exposure compensation (the "distinctly
different habit" from the 8-hypothesis investigation above), but the
new pairs mix in -2/3, -4/3, etc. - so this isn't quite the same single
shooting session either. Expanded the manifest 41->63 (+22, one was a
duplicate file, so +21 net) ->70 (+7) pairs and re-ran
`tools/evaluate_x2dii_generation_loo.py` unchanged:

| n | LOO improvement | LOO sign test p | 5-fold sign test p | Dominant combo |
|---|---|---|---|---|
| 41 | 36.0% | 0.060 | 0.349 (loses significance) | eg=0.3, tl=0.02, **ss=0.82**, wp=0.95 (39/41) |
| 63 | 41.8% | 0.011 | 0.005 | eg=0.3, tl=0.02, **ss=0.5**, wp=0.95 (61/63) |
| 70 | 44.1% | 0.003 | 0.003 (identical to LOO) | eg=0.3, tl=0.02, **ss=0.5**, wp=0.95 (**70/70, unanimous**) |

**`shoulder_start=0.82` was an artifact of the small 41-pair sample** -
as the sample grew, it converged to `0.5`, the same value the other 4
generations (CFV/X2D/X1D/X1D II) already use. At n=70, LOO and 5-fold
results match to the decimal point (44.1% improvement, bootstrap 95% CI
[+31.9%,+53.6%]), and drop-one sensitivity is a stable 42.3-45.7% - the
"selection sensitive to training-set size" problem flagged above is
resolved.

**Verdict: settled.** `exposure_gamma=0.3`/`toe_lift=0.02`/`white_point=0.95`
stay as they were; `brands/hasselblad_x2dii.py`'s `apply_hncs_x2dii()`
had its `shoulder_start` corrected from 0.82 to 0.5. `apply_hncs()`
(main) is unaffected - only the X2D II-only experimental function
changes. Reproduce: same command as above, against the 70-pair manifest.

### Re-fitting a 3x3 color matrix on the X2D II 41 photos - rejected (2026-08)

The "Cross-validated the ColorChecker matrix against the 41 real X2D II
photos" section in the v13 history above only applied a matrix that main
had fit on a **chart** (kmichels-x2dii-2026-07) to the real photos
(chaining the chart matrix + tone curve did worse than the tone curve
alone, 11.23->12.32 ΔE00). This time, re-fit a fresh 3x3 matrix directly
from **the 41 X2D II real photos themselves**, not the chart
(`tools/evaluate_x2dii_color_matrix.py`, new - source is camera-native
linear RGB white-balanced via `AsShotNeutral`, ridge=1.0 least squares),
asking the same question again. LOO (41 folds, refitting the matrix on
the other 40 pairs each time) - the tone curve chained after the matrix
was pinned to `apply_hncs()`'s (main) defaults (toe_lift=0.0,
shoulder_start=0.5, white_point=1.0) so only the matrix stage varied.

| | Mean ΔE00 |
|---|---|
| apply_hncs (main, no matrix) | 10.790 |
| LOO matrix + shared film curve | 12.292 (-13.9%, worse) |

Win/loss=14/27, sign test p=0.060, bootstrap 95% CI (mean diff)=[-2.214,
-0.778] - **entirely negative, excluding 0** (an even clearer win for
apply_hncs than the chart-matrix experiment). **Conclusion: refitting the
matrix on real photos instead of the chart doesn't change the outcome**
- a second, independent experiment confirms X2D II's problem isn't
spatial color distortion (what a matrix corrects) but tone/exposure.
Reproduce: `python3 -m tools.evaluate_x2dii_color_matrix`.

### apply_hncs_x2dii - new X2D II-only experimental function (2026-08)

Combining the three findings above (the direct exposure_gamma comparison
is robust, p<0.001; the 41-pair full-grid optimum is unstable, p=0.349 at
5-fold; the matrix is rejected), added `apply_hncs_x2dii()` in a new file
`brands/hasselblad_x2dii.py` - following the same pattern as
`apply_hncs_learned`/`apply_hasselblad_day`/`night`: `apply_hncs()`
(main) is left untouched, the variant lives in its own file/function,
marked Experimental.

**What this function adopts**: only `exposure_gamma=0.7`, changed from
main's 0.8 - the one signal that held up robustly (p<0.001) in the direct
main-vs-candidate comparison above. **Deliberately not adopted**:
`shoulder_start=0.82`/`toe_lift=0.02`/`white_point=0.95` (the 41-pair
full-grid optimum, which lost significance under 5-fold) -
`shoulder_start`/`toe_lift`/`white_point` stay at main's values. The 3x3
matrix stage isn't included either (rejected above).

Callers must detect X2D II themselves (e.g. via EXIF) and choose this
function instead of `apply_hncs()` - this file has no model-detection
logic of its own. `apply_hncs()` is unchanged by adding this function.

**Update - adopted the full grid optimum (2026-08, explicit user
direction)**: the user explicitly asked to "give the film curve and
exposure their own separate model for X2D II too," so
`shoulder_start=0.82`/`toe_lift=0.02`/`white_point=0.95` - deliberately
left out above for lacking statistical robustness - were adopted as-is.
**The statistics themselves haven't changed** - the verdict above (LOO
sign test p=0.060, losing significance at p=0.349 under 5-fold) still
stands; these values remain the 41-pair in-sample optimum only.
`apply_hncs_x2dii()` defaults are now: `exposure_gamma=0.3,
toe_lift=0.02, shoulder_start=0.82, white_point=0.95`. The 3x3 matrix
remains excluded (rejected above).

### apply_hncs_x2dii final correction - percentile RMSE objective rejected, direct ΔE00 grid search (2026-08)

`shoulder_start` was corrected from 0.82 to 0.5 as the sample grew from
41 to 70 pairs (see "X2D II-only parameters, LOO/5-fold" above), but
every one of those checks still used b2/w995 percentile RMSE as the
objective - `apply_hncs()` (main) had never been put head-to-head
against `apply_hncs_x2dii()` on real ΔE00 until now.

**Direct head-to-head (3000px, minimal downsampling) - result:
essentially a wash** (`tools/evaluate_full_pixel_de00_confirm.py`,
n=70): -5.13% (main slightly ahead), win/loss 34/36, bootstrap 95% CI
[-1.679, +0.292] (includes 0) - **the "44.1% improvement" the percentile
RMSE grid search reported was a defect in the objective itself** - the
exact same pattern hit in Sony a7V (`brands/sony_a7v.py` history) showed
up in X2D II's core parameters (exposure_gamma/shoulder_start) too. This
result also matches, exactly, the visual problem the user flagged after
looking at real renders (exposure_gamma=0.3 output was "too bright,
noisy, and hazy").

**Re-ran the 441-combo grid search with ΔE00 itself as the objective**
(`tools/evaluate_x2dii_de00_grid.py`, new - low-res 200px for per-fold
combo selection, 3000px for the final LOO evaluation): **+12.99%
improvement over `apply_hncs()` (main), 61 wins/9 losses, sign test
p<0.0001, bootstrap 95% CI [+1.421, +2.065]** (excludes 0, genuinely
significant this time) - optimal combo `exposure_gamma=0.6,
toe_lift=0.02, shoulder_start=0.58, white_point=0.95` (dominant in
58/70 folds). exposure_gamma moving from the extreme 0.3 to a much
milder 0.6 lines up exactly with the visual feedback.

**Final adoption**: updated `apply_hncs_x2dii()`'s defaults to
`exposure_gamma=0.6, toe_lift=0.02, shoulder_start=0.58,
white_point=0.95`. `apply_hncs()` (main) is unaffected by this
correction - only this function changes. The lesson that kept repeating
this session: **the bigger the "improvement" a percentile-RMSE grid
search reports, the more suspicious it should be** - Sony a7V
(+52.7% -> actually -1.12%) and X2D II (+44.1% -> actually -5.13%) both
followed the same pattern. Optimizing ΔE00 directly tends to produce
smaller but trustworthy improvements (Sony +0.53%, Leica +0.6-2.8%) -
except when the original objective was pointing in a completely wrong
direction, as with X2D II, where a genuinely large improvement (+12.99%)
was there all along. The size of the number was never the point - the
objective function was. Reproduce: `python3 -m
tools.evaluate_x2dii_de00_grid`.

### Joint shoulder_start x clahe_clip re-verification - already at the optimum (2026-08)

The grid search above only swept exposure_gamma/toe_lift/shoulder_start/
white_point - `clahe_clip` (=1.25) had simply been inherited from
`apply_hncs()` (main)'s default and had never once been treated as a
variable (user flagged this). To check for an interaction between
`shoulder_start` and `clahe_clip`, a joint re-grid-search was run on the
same X2D II 70 pairs (`tools/evaluate_x2dii_clahe_shoulder_grid.py`, new
- exposure_gamma=0.6/toe_lift=0.02/white_point=0.95 held fixed,
shoulder_start x 7 values x clahe_clip x 6 values = 42 combos).

**Data source note**: `~/Documents/raw pair` (which `evaluate_x2dii_de00_grid.py`
used, later recorded as moved to `~/local-work`) wasn't present locally
this session, but all 124 files from the same manifest
(`dpreview_raw_jpeg_pairs_clean.csv`) turned out to already exist under
`datasets/hasselblad/contributed/*/raw|jpeg/` (124/124 matched), so the
re-verification read from there instead.

**Result - no contest, already the optimum**:

| | ΔE00 |
|---|---|
| 42-combo LOO grid search vs apply_hncs(main) | 12.281 -> 10.542 (+14.16%, p<0.0001) |
| 42-combo LOO grid search vs **current** apply_hncs_x2dii(ss=0.58, clip=1.25) | 10.484 -> 10.542 (**-0.56%, wins/losses=0/12, p=0.0005, CI [-0.099,-0.024] excludes 0**) |

**58 of the 70 folds (83%) picked the current values (shoulder_start=0.58,
clahe_clip=1.25) exactly**, and the remaining 12 folds picked a
neighboring value (0.5/0.66) that dragged the LOO average down instead
of up - the current values already win both by majority vote and by
stability. **Conclusion: `clahe_clip=1.25`/`shoulder_start=0.58` weren't
an unverified borrowed default after all - they were the actual joint
optimum of this 2D grid.** No code change (`apply_hncs_x2dii()` left as
is). Reproduce: `python3 -m tools.evaluate_x2dii_clahe_shoulder_grid`.

### apply_hncs_x1d50c added - Hasselblad X1D-50c specific (2026-08)

20 new X1D-50c raw+jpeg pairs were added to the local library (verified
free of Adobe editing contamination). Ran the same ΔE00-native grid
search + LOO as X2D II against `apply_hncs()` (main)
(`tools/evaluate_hasselblad_body_de00_grid.py` - 200px for per-fold combo
selection, 400px to confirm, then `tools/evaluate_native_pixel_confirm.py`
for a native-resolution (max_dim=3000) re-check).

| Stage | Improvement | Wins/Losses | Sign-test p | Bootstrap 95% CI |
|---|---|---|---|---|
| LOO (200px select / 400px eval) | +6.69% | 17/3 | 0.0026 | [+0.301, +0.972] |
| Native pixels (max_dim=3000) | +5.96% | 17/3 | 0.0026 | [+0.309, +0.906] |

Both stages agree with no downsample distortion. All 20/20 folds
unanimously picked the same combo: `exposure_gamma=0.7, toe_lift=0.0,
shoulder_start=0.82, white_point=1.0` - different from X2D II's
(0.6/0.02/0.58/0.95), so this wasn't carried over from X2D II but
re-derived independently from these 20 pairs. Shipped as new file
`brands/hasselblad_x1d50c.py`; `apply_hncs()` (main) is unaffected.

The 20-pair sample is smaller than X2D II's 70, so the statistical
robustness is comparatively weaker - re-validate if more X1D-50c pairs
get added. The same batch also found a distinct optimum for the Sony a7R
VI (toe_lift=0.09, shoulder_start=0.7, white_point=0.85, native-pixel
+0.57%, CI[+0.021,+0.172]), but only X1D-50c was adopted this round.
Canon EOS R6 Mark III's improvement (+0.06%, CI[+0.009,+0.024]) was
statistically significant but practically negligible, so no new function
was created for it.

### apply_leica_raw_look scope extended - SL2/M10 added (2026-08)

55 SL2 and 32 M10 raw+jpeg pairs were newly added to the local library.
Verified against `apply_leica_look()` (brands/leica.py) using the same
methodology as SL3-P/Q3 43 (ΔE00-native grid search + LOO, low-res
selection -> 400px confirm -> native-pixel (max_dim=3000) re-check).

| Body | n | Improvement (LOO) | Improvement (native pixel) | Sign-test p | Bootstrap 95% CI (pixel) |
|---|---|---|---|---|---|
| SL2 | 55 | +2.29% | +1.89% | <0.0001 | [+0.138, +0.274] |
| M10 | 32 | +2.03% | +1.53% | 0.0005 | [+0.079, +0.226] |

Both bodies unanimously converged on the exact same combo as SL3-P/Q3 43
(`toe_lift=0.0, shoulder_start=0.82, white_point=1.0`) - with all 4
bodies landing on identical values, this looks less like coincidence and
more like an actual "Leica house look". Added SL2/M10 to
`apply_leica_raw_look`'s (brands/leica_raw.py) coverage - no code change
needed since the function's defaults already match, just the documented
scope. M11 again had 0 clean pairs in this batch (all 49 contaminated by
Adobe Camera Raw edits) - still unverifiable, still not included.

The same batch also tested Sigma BF (51 pairs, a brand-new body), but its
improvement (+0.53% native-pixel, CI[+0.007, +0.181]) sits right on the
edge of zero - held off this round pending more samples. Hasselblad
X2D 100C (34 pairs, CI[-0.057,+0.433] includes 0), CFV 100C/907X (31
pairs, CI[+0.015,+0.350] close to zero), and Canon EOS R1 (44 pairs,
+0.14% negligible) also weren't adopted this round.

### apply_provia added - Fuji GFX100RF/X-T30 III raw+jpeg pairs found (2026-08)

`brands/fuji.py`'s top docstring long ago noted giving up on raw-based
calibration for lack of genuinely paired raw+jpeg data (only 3 of 97
mirrorlesscomparison.com samples actually shared a shooting timestamp).
Tried again once GFX100RF (.raf) and X-T30 III (.raf) pairs landed in the
local raw+jpeg library. Both bodies' JPEGs all used FilmMode "F0/Standard
(Provia)", for which fuji.py had no matching preset - so instead of
comparing against an existing function, used the unprocessed raw neutral
render itself as the baseline (`tools/evaluate_new_body_de00_grid.py
--baseline-identity`, new flag), ran a ΔE00-native grid search + LOO, then
re-checked at native pixel resolution (max_dim=3000) with
`tools/evaluate_native_pixel_confirm.py`.

| Body | n | Improvement (LOO) | Improvement (native pixel) | Sign-test p | Bootstrap 95% CI (pixel) |
|---|---|---|---|---|---|
| GFX100RF | 38 | +20.16% | +18.82% | <0.0001 | [+2.792, +3.763] |
| X-T30 III | 20 | +27.13% | +23.65% | <0.0001 | [+2.849, +3.927] |

The improvement is naturally larger than other brands' (baseline is raw
untouched, not a marginal step from an existing apply_* function) - but
with all folds unanimous (38/38, 20/20) and CIs well clear of zero, it's
trustworthy. The chosen combos are effectively identical - GFX100RF
`toe_lift=0.0, shoulder_start=0.82, white_point=1.0` vs X-T30 III
`toe_lift=0.02, shoulder_start=0.82, white_point=1.0` - and match exactly
what `apply_leica_raw_look` converged to across all 4 Leica bodies
(brands/leica_raw.py history). Shipped `apply_provia()` with the
larger-sample GFX100RF values as defaults.

### apply_sony_a7rvi_look / apply_sigma_bf_look added - final call on held-back candidates (2026-08)

Per an explicit "ship everything" instruction, adopted Sony a7R VI and
Sigma BF, both previously held back for weak evidence. Both use the
already-confirmed native-pixel numbers as-is - no re-verification was run.

| Function | n | Improvement (native pixel) | Wins/Losses | Sign-test p | Bootstrap 95% CI |
|---|---|---|---|---|---|
| `apply_sony_a7rvi_look` | 40 | +0.57% | 31/9 | 0.0007 | [+0.021, +0.172] |
| `apply_sigma_bf_look` | 51 | +0.53% | 39/12 | 0.0002 | [+0.007, +0.181] |

Both are statistically significant (CI excludes 0) but the lower bound
sits close to zero (Sigma BF especially, at +0.007) - noticeably weaker
evidence than this session's other adoptions (X1D-50c +5.96%, X2D II
+13.38%, Provia +18.8-23.5%), documented explicitly in each file's
docstring. Hasselblad X2D 100C/CFV 100C-907X and Canon EOS R6 Mark III/R1
still weren't adopted - CI includes 0 (X2D 100C) or the improvement is
simply negligible (both Canon bodies, +0.06-0.14%).

### Found and fixed 2 data-integrity bugs - edit-contamination filter (2026-08)

The user asked to "re-verify the data" after seeing a "Leica M11
hue+chroma LUT +16.01%" result (the largest improvement of this session),
which turned up **two independent data-integrity bugs**:

**Bug 1 - Capture One was missing from the edit-keyword list.**
`tools/analyze.py`'s `_check_genuine_bytes()` only screened for
Photoshop/Lightroom/Camera Raw, missing **Capture One** (Phase One's RAW
processing software). Re-checking M11's "clean" 35 pairs showed every
single EXIF `Software` tag was `Capture One 15 Macintosh` - **all
edited.** Both M11 results (grid search +4.82%, hue+chroma LUT +16.01%)
are void - M11 is back to 0 clean pairs (still unverifiable via raw+jpeg
in this batch). Fixed by adding `"capture one"` to `reject_keywords`.

**Bug 2 - a temp-file path race condition (the more serious one).**
`_check_genuine_bytes()` used a fixed temp-file path
(`/tmp/_hasselblad_genuine_check.jpg`) to read back EXIF while checking
for edits. This session ran several brands' `build_flat_manifest.py`
calls in the background concurrently at points, so process A's write
could get overwritten by process B before A's exiftool read it back -
exiftool would then read **the wrong file's EXIF**. Rescanned every
manifest against all 4 edit keywords to confirm:
- Leica: 8 SL3-P pairs were tagged `Adobe Photoshop Camera Raw 18.3.x`
  yet passed - corrected 49 (contaminated) -> 41 (clean)
- Hasselblad: 1 X1D-50c, 4 X1D, and 3 CFV 100C/907X pairs slipped
  through the same way - X1D-50c corrected 21 (contaminated) -> 20
  (clean)
- Sony/Canon/Sigma/Fuji were unaffected by this bug (full rescan, 0 hits)

Fixed with `tempfile.NamedTemporaryFile` so every call gets a unique
path - safe under concurrency.

**Re-verified the affected results** (contamination removed):

| Result | Contaminated value (n) | Corrected value (n) |
|---|---|---|
| `apply_hncs_x1d50c` native-pixel re-check | +5.40% (n=21) | **+5.96% (n=20)** - matches exactly the number from its original adoption, conclusion unchanged |
| X1D-50c +hue+chroma LUT | +4.57% (n=21) | +5.16% (n=20) - same conclusion (still worth adopting) |
| Leica SL3-P +hue+chroma LUT | +3.13% (n=49, contaminated) | +3.87% (n=41, clean) - same conclusion, improvement actually larger |

`apply_hncs_x1d50c` was originally adopted from the clean 20-pair set, so
**the shipped function itself was never affected** - only a later
re-check during this session happened to use the 21-pair contaminated
manifest. Leica M11 was the only case that nearly produced a genuinely
wrong conclusion (a strong-looking improvement), caught here before it
shipped.

**Further correction - CFV 100C/907X's verdict flips entirely**: the
contaminated 31-pair grid search read +3.33% / CI[+0.015, +0.350] ("wins" -
already flagged as weak evidence given how close the CI lower bound sat to
zero); re-checked on the clean 29 pairs (3 contaminated removed) it comes
out to **+2.83% / CI[-0.030, +0.341] - CI now includes 0, flipping to
"inconclusive."** Never adopted (always sat in "weak evidence, held back"
territory), so no real-world impact, but it's a second case - alongside
M11 - of contamination inflating a weak signal into a false win.
Reproduce: `python3 -m tools.evaluate_hasselblad_body_de00_grid --label
"Hasselblad CFV 100C/907X" --manifest
datasets/hasselblad/hasselblad_new_pairs.csv --raw-dir
"/Users/songjiun/local-work" --model "CFV 100C/907X"`.

### apply_leica_raw_look scope extended - SL2-S added (2026-08)

43 new SL2-S raw+jpeg pairs landed in the local library. Verified against
`apply_leica_look()` with the same methodology (ΔE00-native grid search +
LOO): +1.21% improvement, 38 wins/5 losses, sign-test p<0.0001, bootstrap
95% CI [+0.080, +0.173]. All 43/43 folds unanimously converged on the
exact same combo as the existing 4 bodies (SL3-P/Q3 43/SL2/M10):
`toe_lift=0.0, shoulder_start=0.82, white_point=1.0` - now 5 bodies share
the identical value. Checked the 5 losses (diff 0.002-0.041 ΔE00,
rounding-noise scale) for bias - lens/ISO/f-number/shoot-date all matched
the winning group's distribution, no signal found. Added SL2-S to
`apply_leica_raw_look`'s coverage.

### Fuji GFX50S II large batch - Classic Chrome added, Nostalgic Neg replaced (2026-08)

169 new Fujifilm GFX50S II pairs landed in the local raw+jpeg library
(shot across a mix of film modes). Verified per film mode: Provia (9
pairs, too few alone) was merged into the existing GFX100RF/X-T30 III
Provia data; the other 4 modes (Classic Chrome/Classic Negative/
Nostalgic Neg/Eterna) each had at least 25 pairs and were verified
independently.

**Provia re-verified across 3 bodies combined**: GFX100RF(38) +
X-T30 III(20) + GFX50S II(9) = 67-pair grid search - +19.06% improvement,
63 wins/4 losses, sign-test p<0.0001, bootstrap 95% CI [+2.731, +3.556].
65/67 folds converged on the existing adopted values (`toe=0,
shoulder=0.82, wp=1.0`) unchanged - a third body added and nothing moved,
reconfirming the earlier conclusion.

**Directly verified 3 existing presets against raw+jpeg**
(`tools/evaluate_fuji_preset_de00.py`, new - compares the shipped preset
function as-is against untouched raw, not a grid search):

| Preset | n | Improvement | Verdict |
|---|---|---|---|
| Classic Negative | 39 | +4.13% | Preset confirmed working, CI[+0.662,+1.831] |
| Nostalgic Neg | 27 | **-2.13%** | **Raw beats the preset - the preset moves the wrong direction**, CI[-0.936,-0.133] |
| Eterna Cinema | 25 | +1.83% | Inconclusive (CI[-0.234,+1.179] includes 0) |

Nostalgic Neg turned out broken, so it was re-derived the same way as
`apply_provia` (direct toe/shoulder/wp grid search against untouched raw):

**apply_nostalgic_neg_v2 added**: +6.13% improvement, 21 wins/6 losses,
sign-test p=0.0059, bootstrap 95% CI [+0.839, +2.330]. 25/27 folds
converged on `toe_lift=0.036, shoulder_start=0.82, white_point=0.85` -
completely different from the old n=1-comparison-chart hand-tuning
(amber tint boost). The old `apply_nostalgic_neg` code is left untouched
for the historical record with this finding appended to its docstring;
`apply_nostalgic_neg_v2` is the recommended replacement.

**apply_classic_chrome added** (this file had no matching preset at
all): +5.60% improvement, 30 wins/9 losses, sign-test p=0.0011, bootstrap
95% CI [+0.601, +1.556]. toe_lift=0/white_point=1.0 were fold-unanimous
(39/39) but shoulder_start split three ways - 0.66 (15/39), 0.70 (15/39),
0.82 (9/39) - adopted the middle value 0.70 as default; worth
re-checking once more samples land.

Reproduce: `python3 -m tools.evaluate_new_body_de00_grid --label "..."
--manifest /tmp/fuji_<mode>.csv --raw-dir "/Users/songjiun/local-work"
--baseline-identity` (manifest built by filtering
`datasets/fuji/fuji_new_pairs.csv` on the film_mode column).

### apply_sigma_fpl_look added (2026-08)

32 new Sigma fp L raw+jpeg pairs landed in the local library. Ran the
same ΔE00-native grid search + LOO as Sigma BF against `apply_sigma_look()`.

| Stage | Improvement | Wins/Losses | Sign-test p | Bootstrap 95% CI |
|---|---|---|---|---|
| LOO (200px select / 400px eval) | +0.63% | 23/9 | 0.0201 | [+0.044, +0.129] |
| Native pixels (max_dim=3000) | +0.55% | 23/9 | 0.0201 | [+0.038, +0.124] |

All 32/32 folds converged on `toe_lift=0.02, shoulder_start=0.82,
white_point=1.0` - differs from Sigma BF only in toe_lift (0.09). The
improvement is small (Sony a7V / Sigma BF scale) but the CI lower bound
(+0.038) is more comfortable than Sigma BF's (+0.007). Shipped as
`brands/sigma_fpl.py`.

### Directly verified Leica/Fuji tone curves are truly identical (2026-08)

The user asked to double-check whether Leica's and Fuji's tone curves are
"really the same" - re-verified by actually running the functions, not
just comparing parameters: fed `apply_leica_raw_look()` and
`apply_provia()` the same random test image and compared outputs -
**pixel-identical** (`np.array_equal` = True, max difference 0). The
shared value (`toe_lift=0.0, shoulder_start=0.82, white_point=1.0,
clahe_clip=1.25`) was independently arrived at by grid search across 5
Leica bodies (SL3-P/Q3-43/SL2/M10/SL2-S, 215 pairs) and the combined
3-body Fuji Provia set (GFX100RF/X-T30 III/GFX50S II, 67 pairs) - hard to
explain as coincidence.

### Learned LUT vs parametric - 6 new functions (2026-08)

Following the empirical tone-curve study kicked off by the user's "check
whether Leica/Fuji tone curves are really the same" request
(`tools/evaluate_empirical_tone_curve.py`), measured how well the
parametric `toe_lift/shoulder_start/white_point` 3-parameter assumption
actually matches each camera's real curve, via RMSE, across all 10
adopted functions:

| Function | RMSE (0-255) |
|---|---|
| X2D II | 13.57 (best fit) |
| Leica (5 bodies) | 14.59 |
| X1D-50c | 14.69 |
| Sigma fp L | 25.77 |
| Provia (3 bodies) | 26.31 |
| Sony a7V | 26.42 |
| Classic Chrome | 31.82 |
| Sony a7R VI | 34.72 |
| Sigma BF | 45.87 (worst fit) |
| Nostalgic Neg v2 | 46.36 |

Followed up with `tools/evaluate_learned_lut.py` (LOO-cross-validated
256-bin learned LUT instead of the parametric curve) to check whether
this translates into a real ΔE00 win:

| Function | n | Improvement | Verdict |
|---|---|---|---|
| X2D II | 70 | -0.06% | Inconclusive (parametric already near-optimal) |
| X1D-50c | 20 | +3.76% | Inconclusive (CI[-0.115,+0.753]) |
| Sony a7V | 61 | +11.10% | Wins, CI[+1.188,+2.312] |
| Sony a7R VI | 40 | +9.12% | Wins, CI[+0.689,+2.341] |
| Leica (5 bodies) | 216 | +12.56% | Wins, CI[+0.868,+1.333] |
| Sigma BF | 51 | **+38.52%** | **Dominant win**, CI[+5.108,+8.089] |
| Sigma fp L | 32 | +17.01% | Wins, CI[+1.386,+2.813] |
| Provia (3 bodies) | 67 | +20.42% | Wins, CI[+1.959,+3.365] |
| Classic Chrome | 39 | -1.36% | Inconclusive |
| Nostalgic Neg v2 | 27 | +4.69% | Inconclusive (CI[-0.951,+3.227]) |

RMSE and LUT improvement roughly track each other (X2D II lowest
RMSE/lowest gain, Sigma BF highest RMSE/highest gain) but not perfectly -
Leica had low RMSE yet a large gain, while Classic Chrome/Nostalgic Neg v2
had high RMSE yet weak gains. Likely because RMSE weights every L-value
bin equally while ΔE00 is pixel-weighted (dominated by the high-pixel-
count midtone bins), so the two metrics aren't measuring quite the same
thing.

**Shipped the 6 winning cases as new functions**, refit on the full
sample with no holdout (`tools/fit_final_lut.py`); the parametric
`apply_*_look`/`apply_provia` functions are left unchanged and kept
side-by-side, following the `hasselblad_learned.py` precedent:

- `brands/sony_a7v_learned.py` - `apply_sony_a7v_learned`
- `brands/sony_a7rvi_learned.py` - `apply_sony_a7rvi_learned`
- `brands/leica_raw_learned.py` - `apply_leica_raw_learned`
- `brands/sigma_bf_learned.py` - `apply_sigma_bf_learned`
- `brands/sigma_fpl_learned.py` - `apply_sigma_fpl_learned`
- `brands/fuji_provia_learned.py` - `apply_provia_learned`

### Leica/Fuji "identical parameters" was coincidence - real curves differ (2026-08)

Earlier documented that `apply_leica_raw_look()` and `apply_provia()`
produce pixel-identical output. The user pushed back, asking whether that
was just the parameters matching rather than the real curves - overlaid
the actual empirical curves directly: across the shadow-to-midtone range
(input L 18-130), **Provia is consistently 11-24 brighter than Leica**;
the two curves only converge in the highlights (L 150+). The two brands
genuinely have different tone responses, and the parametric grid search
landing on the same value (toe=0/shoulder=0.82/wp=1.0) is now understood
as **the 3-parameter grid being too coarse - two genuinely different real
curves happened to snap to the same grid point**, not a real "house look"
match.

**Not a lens confound**: checked Leica's 4 lens groups (VARIO-ELMARIT /
APO-SUMMICRON 43 / ELMARIT-TL 18 / Summilux-M 35) separately - their
empirical curves were mutually consistent (within ~10-20 units), and the
Fuji X-T30 III lens's curve alone was still consistently brighter than
all of Leica's - the gap is a real brand/body difference, not a lens
artifact.

### 2 improvement attempts - noise-switch hybrid / per-body Leica LUTs, both rejected (2026-08)

**Noise-switch hybrid (rejected)**: Sony a7V/a7R VI showed "the learned
LUT loses to the parametric curve on high-ISO shots" (win/loss groups'
mean ISO: 163 vs 2734, and 1167 vs 3339 respectively). Tried building a
hybrid that switches between parametric and LUT based on noise estimated
directly from the image (Immerkaer 1996 fast noise estimation - EXIF ISO
isn't available inside `apply_*()`'s signature), LOO-validated via
`tools/evaluate_hybrid_switch.py`. Result: slightly *worse* than always
using the LUT (a7V +10.96% vs always-LUT's +11.10%; a7R VI +8.51% vs
+9.12%) - the learned threshold almost never picked parametric (1/61
pairs for a7V, 1.6%). Concluded the image-derived noise estimate doesn't
capture the real ISO signal well enough; rejected.

**Per-body Leica LUTs (rejected)**: Compared the combined 5-body LUT
(`apply_leica_raw_learned`) against individually-fit per-body LUTs
(SL3-P/Q3 43/SL2/M10/SL2-S, via `tools/fit_final_lut.py`) - mean absolute
difference between each body's own LUT and the combined one was only
2.3-6.9 (0-255 scale, much smaller than the 11-24 gap found between Leica
and Fuji's real curves) - the bodies don't differ much from each other.
M10, which had the largest per-body deviation, saw its own LUT beat the
combined one by +3.63% (in-sample, not LOO); SL2, with the smallest
deviation, only +0.56% - essentially negligible. Not enough gain to
justify splitting into 5 separate shipped functions; kept the combined LUT.

### Learned LUT 5-fold re-check - Leica per-lens + Sigma (2026-08)

Per this project's statistical convention that LOO can look more optimistic
as sample size grows (`hybrid_engine/CLAUDE.md`), re-verified some of the
learned-LUT results with 5-fold CV instead (new `--n-folds 5` option on
`tools/evaluate_learned_lut.py`).

**Leica by lens** (VARIO-ELMARIT etc. shared across SL3-P/SL2/SL2-S; sample
counts re-derived fresh from the manifest and confirmed to match exactly:
113/44/28/25):

| Lens | n | Improvement | Verdict |
|---|---|---|---|
| VARIO-ELMARIT-SL | 113 | +19.03% | Wins, CI[+1.295,+2.040] |
| APO-SUMMICRON 43 (Q3) | 44 | +8.12% | Wins, CI[+0.425,+1.203] |
| ELMARIT-TL 18 (CL) | 28 | +9.62% | Wins, CI[+0.540,+1.572] |
| Summilux-M 35 (M10) | 25 | +4.62% | Inconclusive (wins/losses 20/5 lopsided but CI[-0.051,+0.705] includes 0) |

3 of 4 lens groups clearly win under 5-fold too - matches the direction of
the combined 5-body LOO result (+12.56%), confirming robustness. Only the
smallest sample (Summilux-M 35) has a favorable win ratio but too small an
average gain to clear the CI bar.

**Sigma - essentially identical to LOO**:

| | LOO | 5-fold |
|---|---|---|
| Sigma BF | +38.52% | +38.70% |
| Sigma fp L | +17.01% | +17.07% |

The two nearly match - confirms the LOO results weren't overfit.

### ΔE00's kL-weight sensitivity - verdicts stable, magnitudes kL-dependent (2026-08)

The user shared a paper ("CIEDE2000 Optimization for Digital Image Color
Difference Measurement", DBpia) - CIEDE2000's kL/kC/kH default to (1,1,1)
from single-patch experiments, may not be optimal for whole-image color
difference, and even the paper's own optimized parameters only reach
R²=0.61 correlation with visual assessment - prompting a check of how
sensitive this session's ΔE00 (fixed at kL=kC=kH=1 throughout) actually
is to that choice.

`skimage.color.deltaE_ciede2000` accepts kL/kC/kH directly (confirmed via
`inspect.signature`) - re-compared parametric vs learned LUT for 3
representative cases (Sigma BF / Provia GFX100RF / Leica SL3-P, 15-pair
samples each) across kL=1-4:

| kL | Sigma BF | Provia | Leica SL3-P |
|---|---|---|---|
| 1 | +37.2% | +21.4% | +8.5% |
| 2 | +25.9% | +13.8% | +6.7% |
| 3 | +18.6% | +9.5% | +5.2% |
| 4 | +13.9% | +6.9% | +4.1% |

**The winner (LUT) never changes across kL=1-4** - this session's win/loss
verdicts are robust to the kL choice. But **the magnitude shrinks
noticeably as kL grows** - this session's tone-curve calibration only ever
touches the Lab L channel (a/b untouched), and increasing kL reduces the L
component's relative weight in ΔE00. So specific numbers like "+38%" are
tied to the kL=1 choice used throughout this session - the paper's concern
was legitimate. Doesn't change any verdict, but numbers should be quoted
with the "kL=kC=kH=1" caveat attached.

### Full codebase review - found and fixed a non-monotonic shadow artifact in the Sony a7R VI/a7V learned LUTs (2026-08)

A full codebase review (6 areas - brands/core/hybrid_engine/gui/tools/tests
- checked in parallel) found that `apply_sony_a7rvi_learned`'s and
`apply_sony_a7v_learned`'s `_LEARNED_LUT` jumps to mid-gray (93/99) at the
shadow start (index 0-2), then drops sharply at index 3 (20/24) - a
non-monotonic cliff where L=0 renders brighter than L=3. Root cause:
`tools/fit_final_lut.py` only takes a per-bin weighted mean with no
monotonicity guarantee, so a handful of mismatched pixels (registration/
noise) in a given bin get reflected as-is.

Fix: added weighted PAVA (pool adjacent violators, isotonic regression) to
both `tools/fit_final_lut.py` and `tools/evaluate_learned_lut.py` - pins
more strongly where sample weight is higher, while forcing
non-decreasing output. Re-validated both bodies (same raw+jpeg pairs, LOO):

| | Before (non-monotonic) | After PAVA fix |
|---|---|---|
| Sony a7R VI | +9.12%, 26W14L, p=0.0807, CI[+0.689,+2.341] (n=40) | +7.24%, 25W15L, p=0.1539, CI[+0.363,+2.049] (n=40) |
| Sony a7V | +11.10%, 45W16L, p=0.0003, CI[+1.188,+2.312] (n=61) | +7.93%, 42W19L, p=0.0044, CI[+0.672,+1.821] (n=61) |

The improvement shrank slightly (interpreted as removing some of the
noise-overfitting that happened to line up at the cliff), but both CIs
still clear zero, so the "learned LUT wins" verdict itself is unchanged.
Per `brands/CLAUDE.md`, the existing `apply_sony_a7rvi_learned`/
`apply_sony_a7v_learned` are left untouched and new
`apply_sony_a7rvi_learned_v2`/`apply_sony_a7v_learned_v2` functions were
added instead (a changed LUT array is more than a dated-comment
correction) - not yet wired into the
`hybrid_engine/core/preset_inverse.py`/`tools/video_engine.py` registries
(adopting them is a separate decision).

Other items from the same review: `hybrid_engine/calibrate_profile.py`
was silently overwriting `hasselblad.json` with no cross-validation when
run without `--mode` (a `hybrid_engine/CLAUDE.md` "Never touch"
violation) - removed the write path, left a pointer to the gated
`recalibrate.py --write` instead. `tools/iso_noise.py` had the same
fixed-temp-file-path race condition as `tools/analyze.py` - fixed the
same way. `core/engine.py` was missing the `ensure_uint8()` guard (a path
15+ population-fit brands go through) - added. Added golden-hash tests
for the `apply_hncs` family (5 functions) and all 13 Fuji presets
(previously only shape/dtype were checked, so a regression could pass the
full suite silently). Measured whether `apply_reala_ace` repeats the same
saturation bug documented in 5 sibling presets (n=2, X-T30 III) - no
meaningful difference in ΔE00 or saturation delta, so left unchanged
(sample is also under the 8-pair threshold for a real verdict anyway).

### Pair-matching bug had corrupted half the Fuji dataset - found and fixed (2026-08)

After fixing `tools/build_local_manifest.py`'s pair matcher (separate
commit - it processed raws in chronological order and grabbed the "first
candidate encountered" in the jpeg pool, never comparing delta size),
checked how much this actually affected the brand-specific
`*_new_pairs.csv` files built by `tools/build_flat_manifest.py`, which
reuses that same function - re-ran the fixed matcher over the entire
`~/local-work` pool.

**Fuji was badly affected**: **130 of 234 pairs (55.6%) in
`datasets/fuji/fuji_new_pairs.csv` got a different jpeg assignment**
under the fixed matcher. Checked against the camera's own file numbering
(the only available ground truth without labels - same shutter press
means same number) - **the new matching agrees with camera numbering on
128/130 (98.5%), the old matching agrees on 0/130 (0%)**. During GFX50S
II burst shooting (several frames within one second), raws and jpegs
were systematically scrambled, and not a single one of the old matches
happened to be right by luck. Other brands were affected far less (Canon
11 of 143, Sigma 3 of 83, Sony 3-4 of 300, Leica/Nikon/Hasselblad 2 each)
- likely because burst shooting was rarer in those sets.

**Regenerated and committed all brand CSVs with the fixed matcher** (pair
assignment only - `model`/`film_mode` columns were also re-derived from
the correctly-matched jpeg's actual EXIF). Fuji grew to 246 pairs (12
raws that the old matcher couldn't find any candidate for now match
correctly).

**Implication**: this session's Fuji results (Classic Chrome, Nostalgic
Neg v2, the Provia GFX50S II merge, `fuji_provia_learned.py`, etc.) were
computed against this corrupted dataset - more than half the sample was
compared to the wrong target, so **re-verification is needed**. Canon has
no shipped `apply_*` yet (still research-stage) so it's not urgent. The
other brands are only off by 2-4 pairs, likely not enough to flip any
already-published win/loss verdict, but will be re-checked separately.

## clahe_clip - joint shoulder_start re-verification across all brands (2026-08)

As found for X2D II (see "Joint shoulder_start x clahe_clip
re-verification" above), most raw+jpeg-calibrated body-specific
`apply_*` functions had simply inherited `clahe_clip=1.25` from the
population-fit default without ever treating it as a grid-search
variable. On the user's instruction ("all brands"), the remaining 9
bodies with local raw+jpeg data were re-verified the same way
(`tools/evaluate_all_brands_clahe_shoulder_grid.py`, new -
exposure_gamma/toe_lift/white_point held at each body's already-adopted
values, shoulder_start x 7 values x clahe_clip x 6 values = 42 combos,
200px selection / 400px LOO confirm). Data was read from
`datasets/<brand>/contributed/*/` (neither `~/local-work` nor
`~/Documents/raw pair` existed locally this session - the same files
turned out to already be present under the contributed sets instead).

| Body | n | Improvement vs. current shipped | Sign-test p | CI | Verdict |
|---|---|---|---|---|---|
| Hasselblad X1D-50c | 20 | -3.32% | 0.5034 | [-0.617,+0.011] | Hold |
| Sony a7V | 58* | +1.26% | 0.2370 | [+0.067,+0.345] | Hold (CI excludes 0 alone, sign test not significant - weak) |
| Sony a7R VI | 40 | +0.77% | 0.1539 | [-0.041,+0.300] | Hold |
| Leica SL3-P | 41 | +0.67% | 0.2110 | [-0.193,+0.294] | Hold |
| Leica Q3 43 | 44 | +0.00% | - | - | Already optimal (44/44 unanimous) |
| Leica SL2 | 54 | +0.00% | - | - | Already optimal (54/54 unanimous) |
| Leica M10 | 32 | **-4.48%** | 0.0078 | [-0.580,-0.142] | **Current is better - do not touch** |
| Fuji GFX100RF | 38 | **+6.96%** | 0.0139 | [+0.520,+1.366] | **Adopted** |
| Fuji X-T30 III | 20 | +3.32% | 0.2632 | [-0.480,+1.076] | Hold (same direction as GFX100RF, but too small alone) |
| Sigma BF | 82 | **+7.04%** | 0.0012 | [+0.670,+1.551] | **Adopted** |

*Sony a7V: 17 of 75 manifest `.arw` files failed to decode
("Unsupported file format or not RAW file"), leaving 58 usable - cause
uninvestigated, needs a separate check.

**Two adoptions**:
- **`apply_provia()` in `brands/fuji.py`**: `clahe_clip` 1.25 -> 3.0
  (`shoulder_start`=0.82 unchanged). GFX100RF: 38/38 folds unanimous.
  X-T30 III (n=20) isn't significant on its own but points the same
  direction (14/20 land on the clip=3.0 family) - not a contradiction -
  so the larger-sample GFX100RF value was carried into the shared
  function, the same way `shoulder_start=0.82` was originally adopted.
- **`apply_sigma_bf_look` in `brands/sigma_bf.py`**: `_CLAHE_CLIP`
  1.25 -> 3.0 (`toe_lift`/`shoulder_start`/`white_point` unchanged).
  82/82 folds unanimous - a far more robust signal than this body's
  original full-pixel confirmation (+0.53%, CI lower bound +0.007, the
  weakest evidence in that whole batch).

**Everything else left untouched**: X1D-50c, both Sony bodies, and Leica
SL3-P all have a CI that includes 0 - held. Leica Q3 43 and SL2 were
already sitting exactly at the optimum (same pattern as X2D II - an
"unverified borrowed default" turning out to already be optimal isn't
rare). **Leica M10 is the one reverse signal** - the grid search actually
picks a combo significantly worse than the current values (p=0.0078, CI
entirely negative and excluding 0) - for this body the original adoption
process (which included a native-pixel confirmation) was evidently more
trustworthy than this grid search, and this result must never be used to
overwrite it.

Reproduce: `python3 -m tools.evaluate_all_brands_clahe_shoulder_grid`
(~450 pairs, ~25 minutes).

## /goal "other brands' average ΔE00 -> under 10" - missed, ruled a structural limit (2026-08)

This covers the user's `/goal` target: "average ΔE00 across all brands
other than Hasselblad, under 10." **Bottom line up front: missed - and,
after an opus escalation (below), judged structurally unreachable with
current techniques.** Everything tried, and the reasoning, is recorded
here.

**1) Current-state survey** (`tools/measure_all_brand_baselines.py`,
800px, each body's current shipped function as-is):

| Group | ΔE00 |
|---|---|
| Canon (generic) | 23.012 |
| Sony a7R VI (dedicated) | 17.318 |
| Sony a7V (dedicated) | 16.652 |
| Sigma (generic) | 16.250 |
| Sigma BF (dedicated) | 15.990 |
| Sony (generic) | 14.378 |
| Fuji GFX100RF (dedicated) | 13.917 |
| Fuji (generic) | 13.074 |
| Leica Q3 43 (dedicated) | 11.144 |
| Leica (generic) | 10.398 |
| Leica SL2 (dedicated) | 9.731 |
| Leica SL3-P (dedicated) | 8.975 |
| Leica M10 (dedicated) | 8.509 |

10 of 13 groups are at or above 10. Olympus/Panasonic/Pentax/PhaseOne/
Ricoh GR have zero local raw+jpeg calibration data - their ΔE00 can't
even be measured.

**2) A 4-parameter tone-curve grid alone falls far short** - on Canon
(the worst group, with no prior dedicated tuning at all), a ΔE00-direct
grid search + LOO (`tools/fit_population_body_de00_grid.py`, toe_lift x
shoulder_start x white_point x clahe_clip, 252 combos): 23.109 -> 22.041,
**only +4.62%** (the statistics are solid, p<0.0001, but the size isn't
enough).

**3) Adding a color matrix helps, but nowhere near enough**: fit a fresh
3x3 color matrix by least squares on raw native-white-balanced linear RGB
(same method as the `hncs_structural` work), then apply the tone curve
on top (`tools/fit_body_matrix_plus_tone_de00.py`): Canon 19.964
(tone-only) -> 17.478 (matrix+tone), **+12.45%** (p=0.0006) - adding a
saturation/hue LUT on top of that (`--chroma`) only gets to 17.242, a
further +1.3 points - matrix+tone+chroma combined **plateaus in the
17.2 range**.

**Running the identical experiment on "Leica (generic, 244 pairs - 77%
of which are actually the already-dedicated-tuned SL3-P/SL2/Q3-43/M10)"
gives the opposite result**: the matrix actively hurts (12.558 ->
13.684, **-8.97%**, p<0.0001, CI entirely negative) - the same pattern
already found in the Hasselblad `hncs_structural` revalidation ("fitting
a global matrix on pooled, diverse data can actively hurt") repeats here.

**4) Slicing by ISO/exposure/portrait doesn't close the gap either**
(`tools/breakdown_by_exposure_iso.py`, Canon's fixed matrix+tone+chroma
pipeline): ISO buckets (low/mid/high/very-high) run 14.6-19.0, exposure-
compensation buckets (under/neutral/over) run 14.4-19.7 - **no bucket
comes anywhere near 10**. Portraits alone (OpenCV Haar-cascade face
detection on the target JPEGs, 27 of 143 photos) give matrix+tone+chroma
16.626 (the improvement itself has a CI including 0, held) - also
nowhere near 10. **The error isn't concentrated in any particular
condition - it's spread evenly, which means it's a structural floor,
not a "bias" any parameter can shave off.**

**5) Confirmed again that low-resolution grid search runs optimistic**:
Leica generic's tone-only grid search (400px) reported 9.966 -> 9.634 -
**already under 10**, and looked promising. But re-checking SL2-S (43
pairs) alone - whose same 400px grid gave 10.587 -> 10.277 - at native
pixel resolution (max_dim=3000) instead: it slipped to **11.935 ->
11.824** (the same phenomenon as the X2D II CLAHE resolution-bias
section above - CLAHE's fixed `tileGridSize=(8,8)` is biased in its own
favor at low resolution). **Every low-resolution (200-400px) grid-search
result from this session should be assumed to carry an optimistic bias
and should not be cited without a native-pixel re-confirmation.**

**6) Opus escalation - final verdict**: per this project's convention of
escalating `/goal` ambiguity/difficulty to the strongest model tier
rather than stalling, the full evidence trail was handed to opus for a
call. Verdict: **structurally unreachable**.
- This project's single most carefully tuned artifact
  (`apply_hncs_x2dii()` - a 441-combo grid + LOO + 70 pairs + native-
  pixel confirmation) still sits around ~11.7 at native pixel resolution
  - it doesn't clear the 10 bar either. Expecting brand-new brands to
  beat that on average is unrealistic.
- The required drop is **-27.5%** on the 13-group average, while the
  best technique found this session (matrix+tone+chroma) only manages
  **+12.45%** on Canon (the group with the most headroom) and goes
  negative on Leica - there is no available technique that produces
  -27.5% on average.
- Whatever residual survives matrix (color) + tone (brightness/contrast)
  + saturation/hue is almost certainly demosaic/sharpening/noise-
  reduction mismatch, missing lens correction, and scene-adaptive JPEG
  processing (DRO/ALO and the like) - territory a static, global
  function class cannot reach by construction. The only lever this
  project has ever found that works there (per-generation/per-body
  branching, conditional parameters) took Hasselblad alone several
  sessions and hundreds of pairs.
- Collecting data for Olympus/Panasonic/Pentax/PhaseOne/Ricoh GR would
  be **counterproductive** - every "first measurement" baseline in this
  project has started at 13-23, so adding five more groups near that
  range would only pull the average up, not down.

**What was executed on opus's recommendation**: re-checked SL2/SL3-P/M10
(the three groups the survey called "already under 10") at native pixel
resolution (`tools/confirm_leica_raw_look_extension.py --already10`,
time-boxed to ~30 min - all 143 pairs actually finished in about 10):

| Body | n | apply_leica_look (main) | apply_leica_raw_look (dedicated) | Verdict |
|---|---|---|---|---|
| SL3-P | 41 | 9.821 | **9.590** | still under 10 |
| M10 | 32 | 9.562 | **9.415** | still under 10 |
| SL2 | 55 | 10.714 | **10.511** | **misses** (the survey's 800px 9.731 was optimistic bias) |

Only 2 of the 3 (SL3-P/M10) are genuinely under 10 at native pixel
resolution - SL2 just misses (10.5). Counting SL2-S (11.824, "independent
re-confirmation" above) too, only **3 of the 5** dedicated-tuned Leica
bodies are actually under 10 - the rest (SL2/SL2-S) are close, not there.
SL2-S stays adopted (it had already been adopted in an earlier session
and remains statistically solid - see `brands/leica_raw.py`'s docstring,
though it should be noted this does not put it under 10). CL was rejected
for lack of evidence.

**Conclusion**: the miss isn't from insufficient effort - it's a genuine
methodological ceiling. The recommendation back to the user is to
re-target (e.g. "each dedicated function beats its own generic baseline
by >=5% at native pixel resolution," or "close the gap toward
Hasselblad's ~11.7 floor") or to authorize a multi-session, per-body/
per-scene conditional-branching project.

Reproduce: `python3 -m tools.fit_population_body_de00_grid canon`,
`... fit_body_matrix_plus_tone_de00 canon --chroma`,
`... breakdown_by_exposure_iso canon`,
`... confirm_leica_raw_look_extension`.
