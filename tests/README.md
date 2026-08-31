# tests/

`unittest`-based test suite (no pytest or other external dependency
added, keeping `requirements.txt`'s minimal-dependency principle).
Covers `core/curve.py` (tone-curve math, boundary conditions/
monotonicity/continuity) / `core/stats.py` (population statistics
computation) / `core/validation.py` (integrity validation, reproducing
the CDN corruption pattern) / `core/engine.py` (the population-fit
engine) / `brands/*.py` (shape/dtype preservation for every `apply_*`
look function, Fuji preset count consistency) / `tools/
fuji_chart_calibrate.py` (crop-box extraction, delta aggregation) /
`tools/download.py` (imaging-resource.com HTML parsing, filtering,
Google Drive URL classification - network calls are mocked) / all of
`datasets/*/texture_signature.json` (whether sharpening/micro_contrast/
noise fall within a sane cross-brand range - a regression guard against
a Sony-scale-bug-style order-of-magnitude error) / `core/lut.py` /
`core/denoise.py` / `tools/iso_noise.py` (including a regression test
for the patch-grid off-by-one bug) / `core/log_pipeline.py` (exposure
adjustment, Log encoding, `.cube` LUT application, every supported
`LOG_SPACES` entry) / `hybrid_engine/` (normalization/tone/color/
color-matrix/pipeline/ΔE evaluation/EXIF brand detection and preset
inversion, end to end) / `core/dcp_export.py` (DCP TIFF structure,
write/read round-trip, the shipped X2D II profile's physical
correctness against its fit report).

`.github/workflows/tests.yml` runs this suite automatically on every
push/PR.

```
python3 -m unittest discover -s tests -v
```

Run from the repo root so the `core`/`brands`/`tools`/`hybrid_engine`
import paths resolve correctly.
