# tools/

CLIs and research scripts. Nothing here is imported by shipped code.

## `evaluate_*.py` conventions

- **Standalone.** Never import from a sibling `evaluate_*.py` — copy the
  loader instead. Keeps experiments from coupling as they accumulate.
- Data: `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` +
  `raw_calib_cache/`. Files are `{jpeg_basename}.{raw_ext}` and
  `{jpeg_basename}.target.jpg`. 13 official pairs.
- To also use contributed pairs (`datasets/hasselblad/contributed/`),
  wrap the official list in `hybrid_engine.utils.pairs.combine_pairs()` —
  as of `local-mixed-2026-07`, official+contributed is 74 pairs. Not
  every `evaluate_*.py` does this; check whether a script calls
  `combine_pairs()` before assuming its pair count.
- `_resize_max_dim(img, DOWNSAMPLE_MAX_DIM)` **immediately after decode**.
  A 100MP float64 Hasselblad frame OOMs the box — this already happened.
  Global-statistics ΔE isn't distorted by downsampling.
- ΔE is always `hybrid_engine.utils.evaluate.mean_delta_e` (CIEDE2000).
- Statistics go through `summarize()` — see `hybrid_engine/CLAUDE.md`,
  the rules there are non-negotiable.

## Subprocesses

Build an explicit `env=`. The parent's `OMP_NUM_THREADS` once leaked into
`darktable-cli` and silently rendered only 1/4 of every frame — exit code
0, no error, 75% black. Check output plausibility, never just the exit
code.

## dpreview sample-gallery downloads

Plain `curl` gets Cloudflare's challenge page on dpreview.com. Use the
OpenCLI browser (`opencli browser main ...`), which drives an already
-authenticated real Chrome session and passes the challenge. Within a
gallery page (`dpreview.com/samples/<id>/...`), clicking
`.sg-thumb-carousel__item` thumbnails exposes download links at
`a.sg-details__download-link[href$=".jpg"]`/`[href$=".3fr"]` (or whatever
raw ext) - scriptable via `opencli browser main eval`. JPG URLs
(`wp-content/uploads/sample_galleries/...jpg`) are plain CDN assets and
`curl` them directly. RAW URLs are Cloudflare-gated specifically -
`curl` gets the challenge page regardless of User-Agent; the fix is
`opencli browser main open <raw_url>` (navigate), which triggers a real
Chrome download to `~/Downloads` (needs Files-and-Folders TCC permission
granted to the Claude app itself, not Terminal - restart the app after
granting). `tools/download_xcd_lens_gallery.py` and
`tools/download_x1d_x2d100c_restore.py` (2026-08) are worked examples of
this whole pipeline (link CSV -> curl+browser download -> manifest.csv).
`tools/split_local_pool.py` (2026-08) does the inverse: given a folder
with several brands' raw+jpeg mixed together, matches pairs once
globally then routes each into the right `datasets/<brand>/contributed/`
by the raw file's EXIF Make.

## Long runs

RAW-decode experiments hit hours (chromatic aberration: ~2h).

```bash
nohup python3 -m tools.<script> > /tmp/<name>.log 2>&1 &
```

Watch with `Monitor`, filtering for progress **and** failure:
`ΔE=|판정:|Traceback|Error|Killed|OOM`. A success-only filter makes a
crash indistinguishable from silence.

If the turn ends mid-run, report the log path and status. Never fabricate
a result.
