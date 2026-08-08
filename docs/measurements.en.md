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
