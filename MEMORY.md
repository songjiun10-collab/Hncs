# MEMORY.md

Living state snapshot, not instructions — see `CLAUDE.md` for rules. This
file answers "where does the project actually stand right now," so a new
session doesn't have to re-derive it from git log or ask. Append dated
entries below; don't rewrite old ones.

## Snapshot (2026-08-03, branch `claude/unknown-character-0x48vp`)

- 12 shipped brands (`brands/*.py`, excluding `__init__.py` and the
  `hasselblad_day`/`hasselblad_night`/`hasselblad_learned` legacy/
  experimental variants): Hasselblad, Canon, Fujifilm, Leica, Nikon,
  Olympus, Panasonic, Pentax, Phase One, Ricoh GR, Sigma, Sony.
- `python3 -m unittest discover -s tests` → 615 tests. 8 currently error
  in this container on `ModuleNotFoundError: torch` (upscale) and
  missing GUI deps (`gui/` tabs) — not a code regression, just packages
  this container never installed. Everything else green.
- Other sessions landed a lot on this branch concurrently while this one
  was running: a `gui/` desktop wrapper (PyQt, tabs for brand-look
  preview/hybrid convert/lens correction/RAW-Log/upscale), AI
  super-resolution (`core/upscale.py`, Real-ESRGAN via PyTorch or ONNX),
  SD-card deleted-photo recovery (`core/sdcard_undelete.py` +
  `core/sdcard_carve.py`, `tools/data/recover_sdcard.py`), PQ/HLG HDR output
  alongside the Log pipeline, White Patch/Shades-of-Gray AWB modes in
  `raw_pipeline`, and a v11 hybrid-engine recalibration on 65 pairs. None
  of this was reviewed by this session — treat `docs/project_structure.md`
  as the source of truth for what each new file does, not this bullet.
- `apply_hncs()` (Hasselblad) is the only calibration-fit brand; the
  other 11 population-fit brands are docstring-measured from
  imaging-resource.com galleries.
- Sigma (12th brand) is fully shipped: 5 bodies (Bayer fp/fp L + Foveon
  sd Quattro/dp2 Quattro/SD1 Merrill), n=83, `datasets/sigma/` pixel
  signatures present, in `tools/cli/classify_brand.py`'s 10-brand LOO
  discriminability check.
- `apply_acros`/`apply_monochrome` (Fuji) are the only `apply_*`
  functions that return 2D single-channel output, not 3-channel BGR —
  see `brands/CLAUDE.md`.
- `.claude/skills/run-hncs/` exists and is verified working (driver +
  `env`/`smoke`/`sheet`/`look` subcommands) — the equivalent of a
  screenshot for a project with no GUI/server.
- CLAUDE.md was just restructured: short root file + per-directory
  `CLAUDE.md` in `brands/`, `tools/`, `hybrid_engine/`, `docs/`,
  `tests/`, `datasets/`.
- The 61-pair personal-library dataset (not dpreview — that source was a
  dead end, blocked by the site) landed as `datasets/hasselblad/
  contributed/local-mixed-2026-07/` (CFV 100C/907X 30, X2D 100C 24, X1D
  II 50C 6, X1D 1). Another session used it to re-run the HNCS
  illuminant-blend experiment at 74 pairs (13 official + 61 contributed):
  `tools/research/evaluate_hncs_blend.py`, recorded in `hybrid_engine/
  EVALUATION.md`. Result flipped from the 13-pair "inconclusive" verdict
  — both RB and CCT blending now beat hard-cluster classification by
  +1.8%, statistically significant but close to the boundary (RB sign
  test p=0.047, CCT bootstrap CI lower bound +0.017). RB vs. CCT is still
  inconclusive. `apply_hncs()` itself was not touched.

## Snapshot (2026-09-05, branch `develop`)

- `python3 -m unittest discover -s tests` → **855 tests, 0 failures, 0
  errors, 15 skipped** in this container (was 843 with 12 errors). The
  "errors are just packages this container lacks" caveat in the
  2026-08-03 snapshot above is obsolete: every environment-dependent
  test now skips instead of erroring. The 15 skips are 12 needing
  `exiftool` + 3 needing committed `.dcp`/`.icc`/`transicc`. CI installs
  `libimage-exiftool-perl`, so all 12 run there
  (`.github/workflows/tests.yml`).
- `tools/maintenance/audit_repo_integrity.py` no longer dies on a machine without
  `exiftool` — it skips only that check and says so on the last line, so
  "이상 없음" never over-claims the verified scope. It also gained a
  pure-Python header check (`dcp_header_problems` /
  `icc_header_problems`) that catches what `exiftool -validate` cannot:
  a DCP with the standard TIFF magic (42) instead of Adobe's `0x4352`
  passes exiftool, and that magic was the real cause of the 2026-08-31
  "Lightroom won't read the profiles" bug. All 65 committed artifacts
  (3 DCP + 62 ICC) pass — a regression guard, not a fix.
- Default branch is `claude/hncs-v13-dpreview-calibration`; `develop` is
  51 commits ahead of it and 113 behind, so the two have long diverged.
  Work landed directly on `develop`.

## Snapshot (2026-09-07, branch `develop`) - correcting a false claim from commit 6676e97

Commit `6676e97`'s message claimed `.codex/hooks.json`, `AGENTS.md`, and
`CONTRIBUTING.md` "don't exist in this checkout" and that an external
review describing them had fabricated or looked at a different repo.
**That claim was wrong.** All three exist and were already on `develop`
at the time (added by `641147b`/`58db9d7`, both ancestors of 6676e97's
parent). What actually happened: an earlier turn checked for these files
against a local checkout that hadn't yet fetched those commits (a
concurrent push from another session landed them mid-session) - that
check was honest for the state at the time, but the finding was then
carried into a *later* commit message without re-verifying against the
checkout that commit was actually built on. The lesson isn't "don't
trust external reviews" - two of that same review's other findings
(discovery recursion limit, missing Fuji ICC test) were real and fixed
in that same commit. It's: a claim about repo state goes stale the
moment another session might have pushed, and a commit message is
permanent - re-check immediately before writing one, don't reuse a
finding from earlier in the conversation. Not amending/force-pushing
6676e97 (shared branch, already on origin) - this entry is the
correction of record, same pattern as a dated correction blockquote in
`docs/CLAUDE.md`.

Re-verified same-day, all real:
- `.codex/hooks.json` has ~20 hooks hardcoded to `/Users/songjiun/Hncs/...`
  absolute paths - breaks if the checkout path or machine changes.
  `.claude/settings.json` avoids this with relative paths / a
  `$CLAUDE_PROJECT_DIR` var for the one script that needs an absolute
  path. Not fixed here - guessing at Codex's hook-invocation env without
  a way to test against the real Codex CLI risks silently breaking the
  CRITICAL safety hooks (`protect_never_touch` etc.) for whoever actually
  runs Codex on that machine. Flagged for the user instead.
- `AGENTS.md` tells Codex to commit as `user.name Codex` +
  `user.email noreply@anthropic.com` - real Codex commits in the log
  (`f3e1e764`, `a8149e5b`, `1c600790`) match that exactly. This mirrors
  this repo's own root `CLAUDE.md` convention for Claude (`user.name
  Claude` + the same email) - looks like a deliberate "AI agent commits
  share one email, name identifies the tool" policy the user set up
  themselves, not a Codex-specific bug. Flagged rather than changed
  unilaterally - it's a cross-repo identity policy, not a local fix.
- `CONTRIBUTING.md`/`.ko.md` said `hybrid_engine.*` needs "Python 3.12
  specifically" - real requirement is `colour-science==0.4.7` pinning
  Python>=3.11; 3.12 was just what was available on the machine that
  wrote `hybrid_engine/CLAUDE.md`'s venv instructions when its default
  `python3` was 3.9. Fixed both files to say >=3.11.
- `tests/test_brand_jpeg_approx_icc_profiles.py`'s new discovery-based
  brand list asserted `>= 1` while its own comment said "4 currently" -
  3 of 4 could vanish and the meta-test would still pass. Tightened to
  `>= 4`, confirmed by mutation (removing one ICC drops the count to 3
  and the assertion fails).
- **The bigger one**: commits up to and including 6676e97 stated "error
  9건은 pydantic 부재, 이 컨테이너 환경 문제" as if that were a fixed
  baseline, violating `tests/CLAUDE.md`'s "full suite green before every
  commit" - `pip install pydantic` in this exact container makes all 9
  `test_must_hook_server` errors disappear (it's declared as `mcp`'s
  transitive dependency in `requirements.txt`; this sandbox had just
  never run `pip install -r requirements.txt` fully). 1349/1349 green,
  0 errors, 15 skipped (exiftool-only, legitimate) confirmed after
  installing it. `requirements.txt` itself needed no change.

**Same-day follow-up**: both items the previous snapshot flagged as "the
user's call" got the user's call, later the same day. `.codex/hooks.json`
was rewritten to repo-relative paths (verified: `.codex/hooks/*.py` are
symlinks into `.claude/hooks/`, so `os.getcwd()`-based resolution works
identically; a real invocation of `protect_never_touch.py` via the new
relative path returned a valid JSON response). `AGENTS.md`'s Codex email
turned out to be an actual mistake, not deliberate design as its own text
implied - the user said so directly, so `noreply@anthropic.com` there is
now `noreply@openai.com` (best guess matching Claude's `noreply@<its
company>.com` pattern - user hasn't corrected it, but flag it here in
case it's wrong).

## Open threads

- `apply_classic_negative` recalibration is **decided by the user, not
  open work**: `hybrid_engine/EVALUATION.md` (2026-09-04) measured that
  4 of its 47 pairs were mis-paired and its mode mean was inflated by
  1.0532 ΔE00. Nothing in `brands/fuji.py` or the profiles was touched.
- Otherwise nothing tracked here as blocking; check
  `.superpowers/sdd/progress.md` for any in-flight
  subagent-driven-development plan before assuming a clean slate.
