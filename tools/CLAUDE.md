# tools/

CLIs and research scripts. Nothing here is imported by shipped code.

## `evaluate_*.py` conventions

- **Standalone.** Never import from a sibling `evaluate_*.py` — copy the
  loader instead. Keeps experiments from coupling as they accumulate.
- Data: `datasets/hasselblad/hasselblad_raw_jpeg_pairs.csv` +
  `raw_calib_cache/`. Files are `{jpeg_basename}.{raw_ext}` and
  `{jpeg_basename}.target.jpg`.
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
