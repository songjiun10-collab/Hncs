# Start Here

*[한국어](START_HERE.md)*

Back to the [main README](../README.md).

Read the root [README](../README.md)'s TL;DR first to see what this
project does. This doc only covers "where to read next" — the actual
code/methodology content lives in each directory's `CLAUDE.md` and in
`docs/methodology.en.md`.

## Directory map

| Directory | What it does | Rules doc |
|---|---|---|
| `brands/` | Per-brand color-approximation functions (`apply_*`) - the actual shipped artifact | [brands/CLAUDE.md](../brands/CLAUDE.md) |
| `core/` | Tone-curve/LUT/stats/validation helpers shared by `brands/*.py` | No dedicated doc - covered in [brands/CLAUDE.md](../brands/CLAUDE.md) |
| `tools/` | CLIs + research `evaluate_*.py` experiment scripts | [tools/CLAUDE.md](../tools/CLAUDE.md) |
| `hybrid_engine/` | Cross-camera color conversion + calibration/evaluation engine, `EVALUATION.md` (the measurement record) | [hybrid_engine/CLAUDE.md](../hybrid_engine/CLAUDE.md) |
| `gui/` | Tkinter desktop app - wraps the existing CLIs only | [gui/CLAUDE.md](../gui/CLAUDE.md) |
| `tests/` | `unittest` test suite | [tests/CLAUDE.md](../tests/CLAUDE.md) |
| `datasets/` | Committed reference CSV/JSON (official sample metadata, signature-analysis results) | [datasets/CLAUDE.md](../datasets/CLAUDE.md) |
| `docs/` | This directory - detailed documentation | [docs/CLAUDE.md](CLAUDE.md) |

## Want to do X → read Y

| Goal | Read first |
|---|---|
| Add a new brand | [docs/methodology.en.md](methodology.en.md) + [brands/CLAUDE.md](../brands/CLAUDE.md) + copy an existing population-fit brand file (e.g. `brands/nikon.py`) as a template |
| Write/run a research experiment | [tools/CLAUDE.md](../tools/CLAUDE.md) - `evaluate_*.py` conventions (standalone, statistics via `summarize()`) |
| Understand the significance/CI verdict rules | [hybrid_engine/CLAUDE.md](../hybrid_engine/CLAUDE.md)'s "Statistics — non-negotiable" |
| Add/change a GUI tab | [gui/CLAUDE.md](../gui/CLAUDE.md) |
| Edit docs (bilingual pairs etc.) | [docs/CLAUDE.md](CLAUDE.md) |
| Write a test | [tests/CLAUDE.md](../tests/CLAUDE.md) - CI has no image data |
| Add a new dataset/sample | [datasets/CLAUDE.md](../datasets/CLAUDE.md) |
| Find where a specific file lives | [docs/project_structure.en.md](project_structure.en.md) - full file index |

## Absolute rules (summary)

Full list in the root [CLAUDE.md](../CLAUDE.md)'s "## Never" section. The most important one: `apply_hncs()` in `brands/hasselblad.py`, every other shipped `apply_*`, and `hybrid_engine/assets/profiles/*.json`/`*.dcp` never get auto-overwritten by a research script.
