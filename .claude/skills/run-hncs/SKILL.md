---
name: run-hncs
description: Run, build, test, smoke-test or screenshot the Hncs camera color-science project - apply a brand look to a photo, render a contact sheet of all 24 shipped looks, run the CLI tools (LUT export, RAW→Log, video, brand classifier), or check which entry points work in this checkout. Use when asked to run Hncs, render/preview a brand look, verify apply_* output, or reproduce a research experiment.
---

# Running Hncs

Python image-in/image-out library (`brands/*.py` `apply_*` functions) plus
~24 CLI tools. No server, no GUI — so the equivalent of a screenshot here
is **a rendered output image you actually open and look at**.

Driven by `.claude/skills/run-hncs/driver.py`. All paths below are
relative to the repo root, and everything must run from the repo root
(the `core`/`brands`/`tools` imports are path-relative).

## Prerequisites

Already present in the standard container. On a bare machine:

```bash
pip install -r requirements.txt
apt-get install -y libimage-exiftool-perl   # hybrid_engine + contributed-data verification
```

`darktable-cli` (`apt-get install -y darktable`, ~180 packages) is needed
**only** to reproduce `tools/evaluate_darktable_vs_rawpy.py`. Nothing else
uses it.

## Check what this checkout can actually run

Most interesting entry points need image corpora that are **git-ignored**,
so a fresh clone can run far less than the README implies. Start here:

```bash
python3 .claude/skills/run-hncs/driver.py env
```

Prints dependency status, external binaries, and dataset presence:

```
== 데이터셋 (전부 .gitignore - 신선한 클론엔 없음) ==
  OK    raw_calib_cache/           30개  - 핫셀블라드 raw+jpeg 13쌍 - calibrate / evaluate_* / hybrid_engine.main
  OK    downloaded_samples/       123개  - population 샘플 - tools.analyze (없으면 네트워크에서 받음)
  OK    raw_calib_cache_fuji/      10개  - 후지 raw+jpeg 3쌍 - evaluate_fuji_demosaic
```

## Run (agent path)

### Smoke — everything that works with no external data

```bash
python3 .claude/skills/run-hncs/driver.py smoke
```

Exercises the library entry point plus 5 CLIs, exits non-zero on any
failure. Takes ~1 min (the `denoise` step dominates). Verified output:

```
  PASS  라이브러리: apply_hncs 직접 호출
  PASS  CLI: tools.export_lut --list
  PASS  CLI: tools.export_lut (17격자 .cube 생성)
  PASS  CLI: tools.classify_brand predict
  PASS  CLI: tools.denoise
  PASS  CLI: hybrid_engine.convert (--source 필수)

6 pass / 0 fail
```

### Contact sheet — the visual verification

```bash
python3 .claude/skills/run-hncs/driver.py sheet
# -> /tmp/hncs_run/contact_sheet.png   (25 tiles: original + 24 looks)
```

**Then open the PNG and look at it.** Distinct looks should be obvious:
`eterna_cinema` teal, `nostalgic_neg` magenta-shifted, `acros`/
`monochrome` black-and-white, `hncs` brightened warm, the ten
population-fit brands subtler. Uniform tiles = the pipeline is broken.

This is the one command that proves the whole rendering path end-to-end.

### One look at full resolution

```bash
python3 .claude/skills/run-hncs/driver.py look hasselblad
python3 .claude/skills/run-hncs/driver.py look astia --src photo.jpg --out /tmp/out.png
```

Accepts a bare brand (`hasselblad`), a preset (`astia`), or the full
function name (`apply_canon_look`). Unknown name prints the full list.
With no `--src` it crops a clean frame out of a committed demo image, so
it works with no data at all.

Output dir defaults to `/tmp/hncs_run`; override with `HNCS_DRIVER_OUT`.

### Direct invocation (what most PRs touch)

Changes here are usually to a single `apply_*` or a `core/` helper. Skip
the CLI entirely:

```bash
python3 -c "
import cv2
from brands.hasselblad import apply_hncs
src = cv2.imread('docs/images/before_after_hncs.jpg')[60:, :903]
cv2.imwrite('/tmp/out.png', apply_hncs(src))
"
```

### Tests

```bash
python3 -m unittest discover -s tests     # 534 tests, ~30s, no external data needed
```

## Run (CLI tools individually)

All verified working in this container:

```bash
python3 -m tools.export_lut --list
python3 -m tools.export_lut hasselblad /tmp/hb.cube --size 17
python3 -m tools.classify_brand predict /tmp/hncs_run/_smoke_src.jpg
python3 -m tools.denoise in.jpg out.jpg --strength 5
python3 -m tools.video_engine in.mp4 out.mp4 --brand hasselblad
python3 -m hybrid_engine.convert in.jpg out.jpg --source nikon --target hasselblad
python3 -m tools.raw_pipeline raw_calib_cache/00378.jpg.3FR /tmp/o.tiff --log-space V-Log
```

The last one needs a RAW file — any `.3FR`/`.RAF`/`.CR3`/`.ARW` works, but
`raw_calib_cache/` is git-ignored, so supply your own on a fresh clone.

## Gotchas

- **`hybrid_engine.convert` hard-fails on an image with no EXIF** —
  `EXIF로 소스 브랜드를 못 알아봄 (Make=None, Model=None)`, exit 1. Any
  image written by `cv2.imwrite` has no EXIF, so anything you generate
  mid-pipeline hits this. Pass `--source nikon` (or whichever brand).
- **`tools.lens_correction` hard-fails the same way** —
  `--focal-length가 없고 EXIF에 FocalLength도 없음`. Pass
  `--focal-length` and `--aperture` explicitly.
- **`tools.analyze <brand>` is not read-only.** It downloads the sample
  corpus (139 images for `hasselblad`) into git-ignored
  `downloaded_samples/` on first run — it only skips what's already
  cached (`os.path.exists`). Needs network plus the allowlisted domains in
  `.claude/settings.json`. Don't run it casually to "see what it does."
- **`apply_acros` and `apply_monochrome` return 2D single-channel**, not
  3-channel BGR — deliberate, pinned by
  `test_mono_presets_return_single_channel`, and why `export_lut` refuses
  them (`알 수 없는 preset: fuji_acros`). Anything tiling `apply_*` output
  must `cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)` first. The driver does.
- **`docs/images/*.jpg` are composites with baked-in labels**, not clean
  source photos. The top ~60px is a label bar and `before_after_hncs.jpg`
  is a side-by-side pair. Crop `[60:, :width//2]` for a usable frame —
  `driver.py`'s `default_source()` does exactly this.
- **`colour-science` prints a matplotlib warning on every import.**
  Harmless noise, appears in front of real output; filter it when reading
  logs.
- **Research scripts (`tools/evaluate_*.py`) take hours**, not minutes —
  the chromatic-aberration one ran ~2h on 13 RAW pairs. Background them
  and watch the log; see `tools/CLAUDE.md`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'core'` | You're not in the repo root. `cd` there. |
| `EXIF로 소스 브랜드를 못 알아봄` | Add `--source <brand>` to `hybrid_engine.convert`. |
| `--focal-length가 없고 EXIF에 FocalLength도 없음` | Add `--focal-length N --aperture N` to `tools.lens_correction`. |
| `알 수 없는 preset: fuji_acros` from `export_lut` | Expected — monochrome presets are excluded from LUT export. Use `--list`. |
| `could not broadcast input array from shape (H,W) into (H,W,3)` | You got a mono preset's 2D output. `cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)`. |
| `FileNotFoundError` under `raw_calib_cache/` | Git-ignored dataset absent. Run `driver.py env` to confirm, then supply your own RAW+JPEG pairs. |
| Sheet tiles all look identical | Real breakage in the shared curve/engine code — check `core/curve.py` and `core/engine.py`. |
