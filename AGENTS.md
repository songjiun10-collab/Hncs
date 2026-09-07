# AGENTS.md

Read [`CLAUDE.md`](CLAUDE.md) — every rule there applies here too (working
style, area `CLAUDE.md` files, never-touch list, statistics bar, `/goal`
escalation ladder, commit/push conventions). This file exists only
because Codex reads `AGENTS.md` instead of `CLAUDE.md`; the two names
point at one set of conventions, not two.

Kept as a separate file rather than a symlink because of one real
difference:

## Commit authorship

```bash
git config user.email noreply@anthropic.com && git config user.name Codex
```

Use `Codex`, not `Claude`, as `user.name` — everything else in
`CLAUDE.md`'s "Every commit" section applies unchanged (rebase-exec to
fix authorship on prior commits, retry-loop push, full suite green
first).

## Hooks

`.codex/hooks/` mirrors `.claude/hooks/` (most files are symlinks into
it — same logic, same severity tiers, same override mechanism described
in `.claude/hooks/README.md`), registered via `.codex/hooks.json` instead
of `.claude/settings.json`. Logs (`violations_log.jsonl`,
`override_audit.jsonl`) are kept separate per tool on purpose, so
`tools/maintenance/eval_hook_judgments.py` can tell which agent triggered
which event.

Area-level guidance is likewise symlinked: `brands/AGENTS.md` →
`brands/CLAUDE.md`, and the same for `tools/`, `hybrid_engine/`, `docs/`,
`gui/`, `tests/`, `datasets/`. Follow whichever name your tool reads —
the content is identical.
