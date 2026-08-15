# brands/

The shipped artifact. Everything here is load-bearing for users.

## Rules

- **Never modify an existing `apply_*` function.** Not to "improve" it,
  not because an experiment scored better. Appending a new function is
  fine; changing a shipped one is a separate, explicit decision.
- `apply_hncs()` in `hasselblad.py` is the hardest version of this rule —
  research scripts touch it under no circumstances.
- Uniform signature: BGR `np.ndarray` in, same-shape `np.ndarray` out,
  first arg is the image and every other arg has a default.
  `tools/video_engine.py` and `hybrid_engine/` rely on this.
- **Two deliberate exceptions**: `apply_acros` and `apply_monochrome` in
  `fuji.py` return a 2D single-channel array, not 3-channel BGR. That's
  intended for monochrome film simulations and pinned by
  `tests/test_brands.py::test_mono_presets_return_single_channel`;
  `tools/export_lut.py` excludes them from `.cube` export for the same
  reason. Anything tiling or compositing `apply_*` output has to
  `cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)` first.

## Docstrings are the measurement record

Each file's docstring carries the full fitting history (sample size,
sources, what was tried and rejected, version numbers). When new data
changes what we know, **append a dated paragraph** — don't rewrite the
old one. Example from `hasselblad.py`: the v11 parametric curve's
docstring now records that a 74-pair cross-generation retrain confirmed
it beats the learned LUT, without touching the earlier entries.

A rejected experiment belongs in the docstring too. `hasselblad_learned.py`
documents its own overfitting the same way.

## Layout

- `hasselblad.py` — `apply_hncs`, Stable, the project's origin
- `hasselblad_learned.py` — Experimental learned LUT
- `hasselblad_day.py` / `hasselblad_night.py` — Legacy, kept for history
- everything else — population-fit brands, one function each

## `*_learned.py` files share a body via `core.engine.apply_learned_lut_look`

`fuji_provia_learned.py`, `hasselblad_learned.py`, `leica_raw_learned.py`,
`sigma_bf_learned.py`, `sigma_fpl_learned.py`, `sony_a7rvi_learned.py`,
`sony_a7v_learned.py` (9 `apply_*_learned[_v2]` functions total) were
byte-identical copy-paste (LAB convert → CLAHE → `cv2.LUT` → convert back,
only the LUT array differed) until a 2026-08 code review + user-approved
behavior-preserving refactor. Each `apply_*_learned` is now a one-line
wrapper: `return apply_learned_lut_look(img_bgr, _LEARNED_LUT, clahe_clip)`.
Verified behavior-preserving both by a standalone script (old-vs-new byte
comparison on synthetic images, all identical) and by the existing golden
-hash suite (`tests/test_population_fit_look_golden.py`) passing unchanged.
A new learned-LUT brand file should call the shared helper, not re-copy
the body — same principle as `make_population_fit_look()` for the
parametric brands. This required the user's explicit, in-the-moment
sign-off per the root CLAUDE.md "Never" rule (modifying a shipped
`apply_*`), since `protect_never_touch.py` has no bypass — the hook was
temporarily removed from `.claude/settings.json`, the edits made, then
restored.
