# docs/

## Bilingual parity is mandatory

Every doc is a pair: `docs/*.md` (Korean) ↔ `docs/*.en.md` (English), and
at the repo root `README.md` (English) ↔ `README.ko.md` (Korean). Edit
both or neither — a one-sided change is a broken commit.

## project_structure.md / .en.md

An exhaustive per-file index of `brands/ core/ datasets/ tools/ models/`.
New file → new row, both languages. Stale counts in existing rows are
bugs (a "10 brands" row survived long after it became 21).

`hybrid_engine/` internals are out of scope here by convention.

## Links

Relative, resolved from the file's own location. A doc under `docs/`
links a spec as `superpowers/specs/...`; `hybrid_engine/EVALUATION.md`
links the same spec as `../docs/superpowers/specs/...`. Check, don't
assume.

## superpowers/

- `specs/YYYY-MM-DD-<topic>-design.md` — design, written and committed
  before planning
- `plans/YYYY-MM-DD-<feature>.md` — implementation plan, complete code in
  every step, no placeholders

When a spec's premise turns out wrong, add a dated correction blockquote
at the top rather than rewriting it. The plan and spec are historical
records of what was believed at execution time.

## Research notes

`hncs_structural_research.md`, `hncs_external_sources_analysis.md` and
friends cite sources explicitly and mark confidence. External
reverse-engineering (blogs, forums) is labeled as such — never presented
as vendor-confirmed fact.
