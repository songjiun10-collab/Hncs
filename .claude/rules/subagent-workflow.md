# Subagent-driven workflow

`superpowers:brainstorming` → spec in `docs/superpowers/specs/` →
`superpowers:writing-plans` → `superpowers:subagent-driven-development`.
User gates each step with "ㄱ".

## Controller

- **Always name the model** (omitting it inherits the session's, usually
  the priciest). **`sonnet` is the default for implementation and
  review; `opus` only for architecture and the final whole-branch
  review.** Skip `haiku` — its extra turns on multi-step work cost more
  than the tokens it saves.
- **Hand off files, not pasted text** — anything pasted into a dispatch,
  or printed back by a subagent, sits in your context all session. Use
  the skill's `scripts/task-brief` for requirements, a matching report
  path for the reply, `scripts/review-package BASE HEAD` for the diff
  (`BASE` = the commit recorded before dispatch, never `HEAD~1`, which
  silently truncates multi-commit tasks).
- A dispatch describes one task, not the session's history: task +
  interfaces it touches + constraints. Nothing else.
- One implementer at a time. Parallel implementers conflict.
- **Never tell a reviewer what not to flag** or pre-rate a finding's
  severity. Think it's a false positive → let it be raised, settle it in
  the loop.
- Ledger at `.superpowers/sdd/progress.md`. Tasks marked complete are
  done — never re-dispatch, especially after a compaction.
- **Verify claims yourself.** Re-run the suite, read the diff, re-derive
  a number. Reports have been wrong.
- Fix commit authorship after subagent commits — they don't.
- `BLOCKED` → change something (more context, stronger model, smaller
  task); never re-dispatch unchanged. A subagent's turn ending with a
  long job still running → wait for it and use the real output, don't
  restart hours of work from scratch.

## Implementer

- Read the brief first. Its values are exact — use them verbatim.
- Full report to the report file; return only status, commits, a one-line
  test summary, and concerns.
- Honest status: `DONE` / `DONE_WITH_CONCERNS` / `NEEDS_CONTEXT` /
  `BLOCKED`.
- Brief looks wrong → say so and explain, don't silently adapt (a wrong
  constant in a brief was caught exactly this way).
- **Never fabricate a result.** Turn ending mid-run → `DONE_WITH_CONCERNS`
  plus the log path.
- Plain `git commit -m`; the controller fixes authorship.

## Reviewer

- Two verdicts, both required: spec compliance and code quality.
- Verify independently. Run the tests yourself, read the code, don't take
  the report's word for it.
- Can't confirm something from the diff → flag it ⚠️ for the controller.

Don't skip the final whole-branch review; it caught three critical bugs.
