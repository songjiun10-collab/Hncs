# CLAUDE.md

Approximating camera color science as code, measured from official sample
images. 12 brands. `brands/*.py`'s `apply_*` functions are the shipped
artifact; everything else is research feeding them.

Area rules live next to what they govern: `brands/`, `tools/`,
`hybrid_engine/`, `docs/`, `gui/`, `tests/`, `datasets/` each have a
`CLAUDE.md`.

## Working with this user

Korean, extremely terse. Match it — answer the question asked, in a line
or two, no preamble, no restating the request.

- **`ㄱ`/`ㄱㄱ`/`ㅇㅇ`/`ㅇ` = approved, proceed without re-asking; `ㄴㄴ` =
  correction follows, apply at face value without relitigating.** Keep
  replies as short as the question — not a status report.
- **A one-line request can mean hours of work.** Scope it fully; a token
  pass reads as ignoring the ask.
- **`참고` on a pasted URL/table/file means "incorporate this,"** not
  "acknowledge this."
- Bias toward reversible work over pre-confirming it; irreversible things
  still get confirmed.
- **Make every claim checkable**: name the file, show the number, quote
  the command you actually ran. A claim you can't back is worse than
  saying you don't know.
- **"평가 ㄱㄱ"/"객관적으로" = the unvarnished version.** No cushioning —
  lead with what's weak or wrong, in self-reports too.
- **Check whether a gap is already handled before reporting it.**
- **Tests security/permission boundaries under time pressure, accepts a
  firm no.** Restate the boundary once, briefly, without re-explaining —
  don't cave, don't lecture. They resolve it the legitimate way
  themselves once able to (e.g. granting a real OS permission).
- **Before backgrounding anything over ~20-30 min, quote a time
  estimate** (based on the closest comparable prior run if one exists).
  A short check-in during a wait (`?`, `ㅇ?`, `다됨?`) is a status ping,
  not a request to re-derive the estimate — answer in one line and
  reference the number already given rather than re-explaining.
- **Follows and contributes real leads, not just requests.** Will name a
  specific site/source themselves mid-task ("ephotozine 찾아봐", "photo
  review 사이트에") when they have domain knowledge relevant to what's
  being searched — treat these as informed tips worth checking directly,
  not vague suggestions.
- **Terse direction changes ("Main은 버림") delegate execution, not vague.**
  A short pivot means work out the mechanics yourself and report the
  plan — asking "what exactly do you mean" repeatedly reads as stalling.
  Reversible steps: just do them and show the result.
- **Wants durable output, not chat text.** A request for an analysis,
  history, or record usually means a file (or a commit, if it's meant to
  outlive the session) — chat prose that vanishes at compaction doesn't
  count as delivered.
- **Nothing is accepted on one pass.** Re-asks, cross-checks against
  another AI/a forum/a paper. AI output is a tool, not an authority, here
  — this is why every claim needs to be checkable, not just this session's
  habit.
- **Corrections are factual, not adversarial.** Fix and continue — no
  apology paragraph, no autopsy of how the misread happened.
- Emotion isn't the channel; enthusiasm padding is just tokens.
- Typos are frequent and always recoverable (`anjgkfrj?` decoded to `뭐할거?`
  via keyboard-layout mismatch) — infer from context and proceed, don't
  ask which was meant.

## What they optimize for

- **Structure before implementation** — folders, interfaces, README,
  design doc, then code. The spec → plan → implement chain below exists
  because of this, not as ceremony.
- **Small focused modules over one large file.** Splitting by
  responsibility is welcome; a file that keeps growing is a signal, not a
  neutral fact.
- **Numbers, not impressions.** "좋아졌다" is not a result. "+29.7%, 6/13
  folds, ΔE00 7.58 → 2.78" is. This is why the statistics rules in
  `hybrid_engine/CLAUDE.md` are absolute rather than advisory.
- **Reproducible over merely working.** Committed numbers must recompute
  from scratch; that's what the suite, the CI, and the recorded-run
  regression tests are for.
- **One project, many iterations.** Versions, rollbacks and rejected
  approaches are the normal shape of the work — record them, don't discard
  them. `hybrid_engine/EVALUATION.md` is that record.
- Deprioritized: UI/frontend, throwaway prototypes, decisions argued from
  intuition alone.
- **Refactoring, and the tension with "surgical changes" below**:
  structural change (module splits, moved files, rewritten READMEs) is
  welcome **when it's the task** — not license for drive-by cleanup
  inside an unrelated change. Asked-for restructuring: yes. Improving
  code you happened to be reading: no.

## Working principles

Biased toward caution over speed. Use judgment on trivial tasks.

### Think before coding

- State assumptions explicitly. Uncertain → ask.
- Multiple interpretations → present them, don't pick silently.
- Simpler approach exists → say so. Push back when warranted.
- Confused → stop, name what's confusing, ask. Don't hide it. (Exception
  under `/goal` — see Commands.)
- **Before a deep root-cause dig (reinstalling packages, git archaeology,
  A/B-testing library versions), check recent activity on main/sibling
  branches first** — `git log origin/main -- <file>` costs a minute. A
  session once spent much longer independently re-deriving a fix
  (a golden-hash mismatch) that had already landed on main the day
  before, and produced a less accurate root-cause explanation than the
  one already sitting there.

### Simplicity first

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked. No abstractions for single-use code.
  No unrequested configurability. No error handling for impossible cases.
- 200 lines that could be 50 → rewrite it. "Would a senior engineer call
  this overcomplicated?" If yes, simplify.
- **One-off analysis/scratch code that produced a real result still gets
  saved as a file** (e.g. under `tools/`), not left only in a shell
  history or `/tmp`. Simple and unabstracted is fine — disposable isn't;
  the task will likely recur and the next session shouldn't re-derive it.

### Surgical changes

Every changed line traces directly to the request.

- Don't "improve" adjacent code, comments, or formatting. Don't refactor
  what isn't broken. Match existing style even if you'd do it differently.
- Unrelated dead code → mention it, don't delete it. Remove only the
  orphans your own change created.
- The hardest instance of this rule is the never-touch list below. The
  softer version applies everywhere: old research approaches stay as
  baselines, docstring history gets appended to, not rewritten.

### Goal-driven execution

Turn the task into something verifiable, then loop until it passes.

- "Add validation" → write tests for invalid inputs, then make them pass.
  "Fix the bug" → write a failing reproduction, then make it pass.
- "Does X beat Y?" → **commit to the success criterion before seeing
  results.** See `hybrid_engine/CLAUDE.md`: a confidence interval
  straddling zero is inconclusive no matter how good the mean looks.
- Multi-step work gets a plan with a verify step per item. Strong
  criteria let you run independently; "make it work" needs constant
  clarification.

## Never

- Modify `apply_hncs()` in `brands/hasselblad.py`, any shipped `apply_*`,
  or `hybrid_engine/assets/profiles/*.json` / `*.dcp` — **without the
  user's explicit, in-the-moment sign-off**. The default is never;
  silent/automatic changes are never OK. An explicit exception the user
  approves in that conversation (e.g. a behavior-preserving refactor, or
  adopting a recalibration) is a separate, sanctioned path — record what
  was approved and why. Mechanically enforced (CRITICAL severity) by the
  `PreToolUse` hook in `.claude/settings.json` /
  `.claude/hooks/protect_never_touch.py`: function-range checked via AST
  for Edit/Write/MultiEdit, and a best-effort text-match net over Bash
  (`sed -i`, redirection, `cp`/`mv` as destination, `python3 -c
  "...open(...).write(...)"`) that is file-level, not function-level.
  Denies by default; a deliberate override is available (2026-08 design,
  `_hook_common.py`) — a trailing `# HNCS-OVERRIDE: protect_never_touch:
  <reason>` comment on a Bash command, or a fresh
  `.claude/hooks/.pending_override.json` sentinel before an Edit/Write —
  and every override is logged to `override_audit.jsonl` with the git
  sha it was granted at. The hook doesn't judge whether an override is
  wise, only that it was explicit, not silent — see
  `_hook_common.py`'s module docstring for the full tier design (LOW/MID/
  HIGH/CRITICAL, `ask`/`deny`/override).
- Ship an experimental result automatically. That's a separate decision.

## Every commit

Fix authorship or GitHub marks it Unverified. Also after subagent commits.

```bash
git config user.email noreply@anthropic.com && git config user.name Claude
git rebase --exec "git commit --amend --no-edit --reset-author" origin/<branch>
for i in 1 2 3 4; do git push -u origin <branch> && break; sleep $((2**i)); done
```

Push rejected → `git fetch` + `git rebase`, never force. Full suite green
first: `python3 -m unittest discover -s tests`.

## Workflow

`superpowers:brainstorming` → spec in `docs/superpowers/specs/` →
`superpowers:writing-plans` → `superpowers:subagent-driven-development`.
User gates each step with "ㄱ".

### Controller

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

### Implementer

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

### Reviewer

- Two verdicts, both required: spec compliance and code quality.
- Verify independently. Run the tests yourself, read the code, don't take
  the report's word for it.
- Can't confirm something from the diff → flag it ⚠️ for the controller.

Don't skip the final whole-branch review; it caught three critical bugs.

## Commands

**`/goal <condition>`** — session-exit gate. Saying you'll do it doesn't
count; finish it and report each item. Search order when told to find
work: open PR → unfinished conversation work → TODO/FIXME → doc/code
drift → artifact integrity. Finish what's started, don't invent projects.

Ambiguity here is the one case where "stop and ask" doesn't apply — the
point of `/goal` is running without the user. **Escalate instead:**
dispatch a subagent on the strongest tier (`opus`) to make the call, then
record what it decided and why. Don't guess, and don't stall.

Still stop for decisions that are genuinely the user's: shipping a
calibration change, deleting data, anything outward-facing. A stronger
model resolves ambiguity, not authority.

**`/loop [interval]`** — don't poll harness-tracked work (it notifies);
set a long fallback (1200s+) and arm a `Monitor` for the real signal.
Match interval to state-change rate only for external polling. Quiet →
one line, stop. Reversible: act. Irreversible: confirm first.

**`/compact`** — afterwards trust `.superpowers/sdd/progress.md` and
`git log` over recollection.
