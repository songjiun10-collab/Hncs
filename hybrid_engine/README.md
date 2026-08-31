# hybrid_engine/ - EXIF-driven cross-camera color conversion (V0.1)

A third, independent module with yet another purpose from `brands/*.py`
and `tools/raw_pipeline.py`: "re-render a finished JPEG shot on camera A
as if camera B had shot it." There are two entry points - one for RAW
input (`HybridCameraEngine`: Phase 0 color unification + Gray World
normalization + LAB tone/saturation curves) and one for JPEG-only input
(`preset_inverse`: detects the source brand from EXIF, inverts that
brand's population-fit tone curve from `brands/*.py`, then re-applies
the real target brand's existing `apply_*` function).

Run these from the repo root, not from inside `hybrid_engine/`, so the
`core`/`brands`/`hybrid_engine` import paths resolve correctly.

```
# JPEG only - auto-detects the source camera from EXIF
python3 -m hybrid_engine.convert photo.jpg out.jpg --target hasselblad

# RAW available - full pipeline (matrix + WB unification + Gray World +
# tone/color curves), also auto-detects the camera from EXIF and picks the
# matching profile; --profile only needed to override that
python3 -m hybrid_engine.main photo.3FR out.jpg
python3 -m hybrid_engine.main photo.3FR out.tiff --profile hasselblad  # 16-bit for further editing
```

![hybrid_engine demo - Fuji RAW rendered through the Hasselblad profile](../docs/images/hybrid_engine_demo.jpg)

*A Fuji GFX50S II RAW (`DSCF9556.RAF`, from the same `999_FUJI` raw+jpeg
library as the other demos on this page) rendered two ways: the camera's
own JPEG (left) vs `hybrid_engine.main --profile hasselblad` (right) -
the RAW pipeline (color matrix + Gray World + LAB tone/color curves),
not `hybrid_engine.convert`, since Fuji's film-simulation presets don't
have the closed-form invertible tone curve `preset_inverse` needs
(`core/preset_inverse.py` - only the population-fit brands in
`BRAND_FUNCS` are invertible).*

![hybrid_engine demo, 4 more photos - library/architecture/palace/street](../docs/images/hybrid_engine_demo_more.jpg)

*Four more `999_FUJI` RAW+JPEG pairs (Starfield Library at COEX, a
sculpture outside Seoul City Hall, Gyeongbokgung Palace's main gate, a
Myeongdong street) run through the same `hybrid_engine.main --profile
hasselblad` RAW pipeline as above. People appearing at a distance in the
library/palace/street shots are not identifiable close-ups.*

**Known limitations** (also documented in each module's docstring):
- `core/color_matrix.py`: even with camera-specific color-matrix normalization, sensor spectral sensitivities are never exactly proportional to the CIE standard observer (metamerism), so a physically perfect camera-agnostic colorspace isn't possible - the residual can only be reduced via the ΔE loop, not eliminated
- `core/preset_inverse.py`: only the L-channel tone curve of population-fit brands can be inverted (it has a closed-form inverse) - CLAHE (perceptual contrast compensation) is an adaptive operation and isn't inverted, and brands without a raw+jpeg pair (e.g. Fuji) simply aren't this kind of curve to begin with, so they're out of scope by design
- `calibrate_profile.py` runs the CIEDE2000 ΔE loop against the 13 real Hasselblad raw+jpeg pairs. Every experiment below is judged by cross-validated ΔE, not in-sample - several looked good in-sample and then failed (or reversed sign) once properly validated, which is itself a recurring finding worth reading the table with in mind. `recalibrate.py` wraps the actual "matrix + retrain, nested CV, only update if the cross-validated ΔE genuinely improves" procedure used to ship v1.2 into one command (`python3 -m hybrid_engine.recalibrate --write`, dry-run by default, `--cache-dir` to point at a different raw+jpeg pair directory) - useful once a larger dataset (e.g. issue #4's real-scene X2D pairs) arrives:

  | Experiment | Method | In-sample | Cross-validated | Verdict |
  |---|---|---|---|---|
  | v1.1 baseline | coordinate descent over `tone_core`/`color_core` params | ΔE00 15.01 | - | starting point |
  | Learned tone LUT | 1D LUT, 256 bins, on L | +4.9% | not run (added CV after this) | rejected, below bar |
  | Learned hue LUT (v1.1) | 1D circular LUT, 36 bins | +2.1% | not run | rejected, below bar |
  | 3D residual LUT | joint L/a/b grid, 729 cells | +11.1% | **-5.7%** | rejected, pure overfitting |
  | 2D residual LUT | joint a/b grid, 81 cells | +1.4% | -2.7% | rejected |
  | Spatial/local contrast (v1.1) | unsharp-mask L-channel clarity | +0.0% | +2.0% (noise) | rejected, null result |
  | **Raw-baseline 3x3 matrix (standalone)** | global least-squares color matrix, no color chart (GitHub issue #4) | +42.4% | **+32.6%** | first real win |
  | Matrix wired into the pipeline (1st attempt) | matrix + existing Phase 0/1/2 | - | +0.0% | bug: forced exposure normalization was erasing the matrix's gain |
  | Matrix + retrained tone/color (fixed) | `--mode raw_baseline_pipeline`, nested CV | +34.8% | **+29.7%** | **shipped as v1.2** |
  | Hue LUT retried on v1.2 | same 1D circular LUT, new baseline | +4.6% | +1.4% | rejected, below bar |
  | Spatial retried on v1.2 | same local-contrast stage, new baseline | +0.3% | -1.6% | rejected |
  | Robust (percentile) Gray World | exclude high-saturation pixels from the neutral-cast estimate | +0.0% (best candidate = off) | -3.4% | rejected, targeted night-scene sky over-correction but didn't help |
  | Hue-conditional chroma LUT | 36-bin circular chroma gain, orthogonal to the hue-rotation LUT | **-2.0%** | -4.0% | rejected - first LUT experiment negative even in-sample |
  | Gray World removed entirely | rely only on camera as-shot WB (`unify_to_d65`), no pixel-content neutral-cast estimate | - | **-90.3%** (ΔE00 9.69 → 18.43) | rejected hard - Gray World is load-bearing on all 13 pairs, not just noise |
  | Zoned Gray World (2-5 luma zones) | independent neutral-cast estimate per brightness zone, Gaussian-blended | +0.0% (best = 1 zone) | +0.0%, monotonically worse past 1 zone, all 13 LOO folds picked the baseline | rejected - more degrees of freedom just adds noise at this sample size |
  | Gray World strength (fine-tune) | single blend-strength knob interpolating identity ↔ full correction, fine grid 0.6-1.4 | +0.7% (best=0.95) | **-0.0%** (essentially a wash) | rejected - even the most conservative possible adjustment (1 free parameter) finds no real signal |
  | X2D II chart pairs pooled into calibration | 13 X1D + 2 curated X2D II ColorChecker pairs (9-frame burst deduped to 2, all-9 diluted the gain) | -2.5% | **+3.7%** (true LOO, held-out X1D pair never in training) | first pooling attempt that helped rather than hurt |
  | Gray Edge color-cast algorithm | swap Gray World for spatial-derivative-based neutral-cast estimation (van de Weijer 2007), matrix/tone/color otherwise unchanged | - | **+2.1%** | adopted (White Patch was -18.5%, Shades of Gray a weak +1.9%) |
  | **Gray Edge + chart pooling, retrained together** | matrix + tone/color refit from scratch with `color_cast_algorithm=gray_edge` and 15 pairs | +9.9% | **+11.1%** | **shipped as v1.3** - first result to clear the 5% bar since v1.2 |

  The shipped v1.3 profile refits the matrix and tone/color curves from 15 pairs (13 X1D + 2 curated X2D II ColorChecker pairs) with Gray Edge instead of Gray World for Phase 0's color-cast correction - `EVALUATION.md` follow-up 17/18 has the full comparison table and the reasoning for why the combination beats either change alone. A non-linear RBF color-matching prototype (`scipy.interpolate.RBFInterpolator`, inspired by [ethan-ou/camera-match](https://github.com/ethan-ou/camera-match)) and a pixel-level gradient-boosting regressor were also tried as full matrix replacements - both showed the same failure pattern (big gains on already-hard scenes, but net losses on already-easy ones) and neither cleared the bar, so neither is in the shipped pipeline.

  The shipped v1.2 profile (superseded by v1.3 above) measured ΔE00 15.01 → **9.82** on the official evaluation harness (-34.6%, a CIE 2000 tier upgrade from "completely different colors" to "different at a glance"). Full methodology, the failed-then-diagnosed-then-fixed integration story, and remaining limitations (midtone residual, hue barely moved) are in `EVALUATION.md`; the rejected LUT experiments have their own detailed writeup in `assets/luts/README.md`. Pixel-level diagnosis (`EVALUATION.md` follow-up 10) pinned the worst remaining failure mode to a specific mechanism: Gray World's single global scale factor can't satisfy a night scene's sky and street-light-dominated foreground at the same time - four different fixes for that (above), spanning from "more degrees of freedom" to "fewer," were all tried and rejected on cross-validation, so it stays a documented, unresolved limitation rather than a shipped workaround.

## Further reading

- `EVALUATION.md` - the full measurement record for this module (every
  numbered follow-up experiment, not just the table above)
- `assets/luts/README.md` - the rejected LUT experiments in detail
- `CLAUDE.md` (this directory) - rules for changes here
