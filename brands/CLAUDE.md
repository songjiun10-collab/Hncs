# brands/

The shipped artifact. Everything here is load-bearing for users.

## Rules

- **Never modify an existing `apply_*` function.** Not to "improve" it,
  not because an experiment scored better. Appending a new function is
  fine; changing a shipped one is a separate, explicit decision.
- `apply_hncs()` in `hasselblad.py` is the hardest version of this rule —
  research scripts touch it under no circumstances.
- Uniform signature: BGR `np.ndarray` in, BGR `np.ndarray` out. No
  exceptions, `tools/video_engine.py` and `hybrid_engine/` both rely on it.

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
