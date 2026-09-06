# brands/

The shipped artifact. Everything here is load-bearing for users.

## Rules

- **Never modify an existing `apply_*` function.** Not to "improve" it,
  not because an experiment scored better. Appending a new function is
  fine; changing a shipped one is a separate, explicit decision.
- `apply_hncs()` in `hasselblad/look.py` is the hardest version of this rule —
  research scripts touch it under no circumstances.
- Uniform signature: BGR `np.ndarray` in, same-shape `np.ndarray` out,
  first arg is the image and every other arg has a default.
  `tools/video_engine.py` and `hybrid_engine/` rely on this.
- **Two deliberate exceptions**: `apply_acros` and `apply_monochrome` in
  `fuji/look.py` return a 2D single-channel array, not 3-channel BGR. That's
  intended for monochrome film simulations and pinned by
  `tests/test_brands.py::test_mono_presets_return_single_channel`;
  `tools/export_lut.py` excludes them from `.cube` export for the same
  reason. Anything tiling or compositing `apply_*` output has to
  `cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)` first.

## Docstrings are the measurement record

Each file's docstring carries the full fitting history (sample size,
sources, what was tried and rejected, version numbers). When new data
changes what we know, **append a dated paragraph** — don't rewrite the
old one. Example from `hasselblad/look.py`: the v11 parametric curve's
docstring now records that a 74-pair cross-generation retrain confirmed
it beats the learned LUT, without touching the earlier entries.

A rejected experiment belongs in the docstring too. `hasselblad/learned.py`
documents its own overfitting the same way.

## Layout

One package per brand (`brands/<brand>/`), flat modules inside it. The
files were flat (`hasselblad_x2dii.py`, `sony_a7v_learned.py`, …) until
2026-09-06; grouping them per brand was a pure move — no `apply_*` body
changed, and the golden-hash tests are what pins that.

- `<brand>/look.py` — the brand's primary look, one per package
- `<brand>/<variant>.py` — body-specific or experimental variants, with
  the brand prefix stripped (`hasselblad_x2dii.py` → `hasselblad/x2dii.py`,
  `sony_a7v_learned.py` → `sony/a7v_learned.py`)
- `<brand>/__init__.py` — re-exports every public `apply_*` in the
  package, so `from brands.hasselblad import apply_hncs` still works

Notable members:

- `hasselblad/look.py` — `apply_hncs`, Stable, the project's origin
- `hasselblad/learned.py` — Experimental learned LUT
- `hasselblad/day.py` / `hasselblad/night.py` — Legacy, kept for history
- everything else — population-fit brands, one function each

**When adding a brand or a variant**, the discovery code finds it on its
own — `tests/test_brands.py::_discover_brand_looks`,
`gui/tabs/brand_preview.list_shipped_looks` and
`.claude/skills/run-hncs/driver.shipped_looks` all glob
`brands/*/*.py` and skip `__init__`. Nothing to register by hand, but the
file does have to sit inside a brand package — a `brands/foo.py` at the
top level is invisible to all three.
