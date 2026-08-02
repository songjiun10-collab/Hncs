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
parametric) - LOO RMSE decreased monotonically from 33.61 at λ=0 (pure learned
LUT) to 22.18 at λ=1e9, with no intermediate point ever beating the endpoint.
Significance test, best (=v11) vs v12 (λ=0): 46.4% improvement, 60 wins/14
losses, sign-test p=0.000, bootstrap 95% CI [+35.5%, +56.4%] (excludes 0) -
same direction as the learned-LUT re-check above (19.94 vs 22.20), though the
absolute numbers aren't directly comparable since this script uses its own
percentile-based LOO error, not the same metric. Per-generation RMSE
breakdown (at λ=1e9):

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
