# Contributing to HNCS

*[한국어](CONTRIBUTING.ko.md)*

Thanks for considering a contribution. This project measures official
camera sample images and approximates each brand's color science as
code — see [README.md](README.md) for the full picture. Two kinds of
contribution are equally welcome: **code** and **data**.

## Before you start

- Read the area's `CLAUDE.md` first: [`brands/CLAUDE.md`](brands/CLAUDE.md),
  [`tools/CLAUDE.md`](tools/CLAUDE.md), [`hybrid_engine/CLAUDE.md`](hybrid_engine/CLAUDE.md),
  [`docs/CLAUDE.md`](docs/CLAUDE.md), [`gui/CLAUDE.md`](gui/CLAUDE.md),
  [`tests/CLAUDE.md`](tests/CLAUDE.md), [`datasets/CLAUDE.md`](datasets/CLAUDE.md).
  These hold the conventions that actually govern each directory —
  file layout, statistics rules, what's shipped vs. research-only.
- For anything beyond a small fix, open an issue first describing what
  you want to change and why. Saves both sides a rewritten PR.
- PRs target `develop`, not `main` — `main` is synced from `develop`
  periodically, not worked on directly.

## Code contributions

### Setup

```bash
pip install -r requirements.txt
python3 -m unittest discover -s tests
```

`hybrid_engine.*` modules need Python 3.12 specifically (colour-science/
numpy version pinning) — see `hybrid_engine/CLAUDE.md` if you're touching
that directory. Everything else runs on 3.11+ (CI uses 3.11).

CI (`.github/workflows/tests.yml`) runs the full suite on every push and
PR — it must be green before review.

### Conventions

- **Minimum code that solves the problem.** No abstractions for
  single-use code, no speculative configurability, no error handling for
  cases that can't happen. If it could be 50 lines instead of 200,
  make it 50.
- **Surgical diffs.** Every changed line should trace to what the PR is
  about. Don't reformat, refactor, or "improve" adjacent code in the
  same PR — file a separate issue/PR for that instead.
- **Never modify a shipped `apply_*` function** (`brands/*/look.py` etc.)
  or anything under `hybrid_engine/assets/profiles/` (`.json`/`.dcp`)
  without discussing it in an issue first. These are the actual shipped
  calibration artifacts; changing them is a deliberate, reviewed decision,
  never a drive-by. (Mechanically enforced on the maintainer's side by a
  pre-commit hook — see `.claude/hooks/README.md` if you're curious how.)
- One-off analysis scripts that produced a real result belong in `tools/`
  as a plain, unabstracted file — not left in a gist or your own fork.
  The next person very likely needs the same script again for a new
  camera/brand.

### If your change touches a calibration claim

Any "this is better" claim about color-science output needs to survive
this project's statistics bar (`hybrid_engine/CLAUDE.md`, non-negotiable):

- Never call a result from a mean difference alone — pair it with a
  bootstrap 95% CI (or the project's `summarize()` helper, which also
  runs a paired t-test and sign test).
- A CI straddling zero is **inconclusive**, no matter how good the mean
  looks. Don't round that up to a win.
- Record the result either way in `hybrid_engine/EVALUATION.md` — losses
  and inconclusive results are as valuable as wins; they stop the next
  person from re-running the same dead end. See the file's existing
  entries for the expected format (per-pair table, exact numbers from
  the run log, no hand-rounding).

## Data contributions

This is often more valuable than code — the project is bottlenecked on
real official sample images and controlled RAW+JPEG pairs far more than
on implementation. [Issue #4](https://github.com/songjiun10-collab/Hncs/issues/4)
is a live example of exactly this kind of contribution (Hasselblad X2D II
ColorChecker + RAW/JPEG pairs).

### What's useful

- Simultaneous RAW+JPEG pairs from a camera/generation the project is
  thin on, ideally across a few different lighting conditions (daylight,
  overcast, tungsten/mixed, low-light).
- ColorChecker/color-target frames under a **measured** illuminant.
  These let the project fit a real camera-to-XYZ matrix instead of
  relying on `libraw`'s generic one.
- Manufacturer-app renders (e.g. Hasselblad Phocus TIFF exports) paired
  with the same RAW, so JPEG-engine vs. RAW-processing-app vs.
  photographer-grading can be told apart.

### Format

See `datasets/hasselblad/contributed/README.md` for the exact intake
spec (currently the most fleshed-out one; other brands follow the same
shape). In short: a `manifest.csv` with required columns (camera, lens,
ISO, WB setting, scene type, a `download_url` or other stated
provenance), images hosted externally rather than committed (they're
git-ignored — only the manifest and derived analysis are tracked), and
your set passes `python3 -m tools.data.verify_contributed_pairs <your-dir>`
(checks required columns/files, EXIF Make/Model against the manifest,
RAW/JPEG timestamps within 2 seconds of each other, and no
Photoshop/Lightroom signature in the JPEG's EXIF Software tag) before it
enters any analysis.

**Provenance is the whole point.** Data whose origin can't be stated
doesn't get used, no matter how good it looks — this project's value is
specifically in not doing that.

## License

MIT (see [LICENSE](LICENSE)). By contributing, you agree your
contribution is provided under the same license.
