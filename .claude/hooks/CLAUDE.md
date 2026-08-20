# .claude/hooks/

Protocol for testing this hook system — both the code (regex/AST guards)
and, separately, whether a real dispatched agent's own judgment catches
what the code misses. Established over 10 rounds (2026-08-18/19),
codified here so the next session doesn't re-derive the boundaries.
Findings themselves go in `README.md`'s "알려진 한계" — this file is the
*how*, not the results.

## Two tiers — don't conflate them

**Tier 1 — code-level (synthetic).** Feed crafted stdin JSON directly to
a hook `.py` script via `echo '...' | python3 .claude/hooks/X.py`. Tests
regex/AST logic only — never touches Claude Code's real PreToolUse/
PostToolUse dispatch, no real agent involved. Cheap, fast, fully
deterministic. Use for: "does this pattern match", "does this path regex
cover Y", "is this check fail-open or fail-closed".

**Tier 2 — live (real Agent dispatch).** Actually call the `Agent` tool.
Goes through the real hook pipeline (`settings.json` matchers fire for
real) and tests a real model's judgment, not code. Expensive (~50-70k
tokens/dispatch), non-deterministic, N=1 per run — never generalize from
one result. Use for: "does a real subagent see through this deception",
never for re-confirming something Tier 1 already settled.

Don't run Tier 2 to answer a Tier 1 question. If the answer is "the code
doesn't check X", proving it via a live dispatch adds cost, not
information — `_APPROVE_RE`/`_OPUS_RE`/`is_subagent_call` etc. are static
and fully readable.

## Isolation — mandatory for both tiers

- **Tier 1**: redirect every sentinel/log path via env vars before
  invoking a hook script — `HNCS_HOOK_DECISION_RECORD_SENTINEL`,
  `HNCS_HOOK_MEDIUM_APPROVAL_SENTINEL`, `HNCS_HOOK_OVERRIDE_SENTINEL`,
  `HNCS_HOOK_OVERRIDE_AUDIT_LOG`, `HNCS_HOOK_VIOLATIONS_LOG`,
  `HNCS_HOOK_PENDING_CAUTION` → a scratch dir. Same mechanism
  `tests/test_hooks_medium_approval.py` uses. Never let a test write to
  the real `.claude/hooks/.pending_*.json` / `*_log.jsonl`.
- **Tier 2**: dispatch the subagent into a **separate scratch git repo**
  (`git init` under `/tmp/.../scratchpad/`, not a clone of this repo,
  not this repo's working tree) — cd there first in the dispatch prompt.
  Never point a live dispatch at real files in this checkout. Avoid path
  shapes that accidentally match this repo's own real guard regexes
  (e.g. use `sim_brands/` not `brands/`) — otherwise *your own* Bash
  setup commands trip the real hooks as false positives.
- **After every Tier 2 dispatch**, check whether the real
  `.claude/hooks/.pending_medium_approval.json` /
  `.pending_decision_record.json` got a real entry (PostToolUse hooks
  fire on the real `Agent` tool call regardless of what the subagent
  investigated) — delete it immediately if so, even though a fabricated
  `target` string usually can't match a real file path. Then delete the
  scratch repo entirely (`rm -rf` with a **literal** path — a shell
  variable in the same command makes `protect_destructive.py` deny it,
  can't statically verify).

## What's legitimate vs. what isn't

Legitimate: does an existing control (regex, sentinel check, a
dispatched reviewer's judgment) actually verify a claim, or does it just
check that *some* marker/keyword is present? Testing this — including
constructing fabricated-but-isolated "evidence" to see if a control (or
a live subagent) can tell it's fake — is real security research.

Not legitimate, regardless of isolation:
- Making "the deception succeeds" the stated goal/stopping condition.
  Turns research into optimizing toward a predetermined outcome. Report
  whatever the result is; don't keep escalating a single scenario until
  it works.
- Generic jailbreak technique against the model itself (roleplay/fiction
  framing, "ignore your safety rules, this is just a test", encoding/
  obfuscation to hide intent). That's not testing this repo's design,
  it's probing Claude's general safety training — a different, more
  sensitive thing, and out of scope here regardless of how it's framed.
- Fabricating evidence in the **real** repo (backdated real commits,
  real `override_audit.jsonl` entries) even temporarily. The isolation
  rule above exists precisely so this never has to be weighed against
  "but I'll revert it after."

When genuinely unsure which side of this a request is on, ask — don't
guess and proceed.

## Reporting

- Every finding goes in `README.md`, dated, with the actual command and
  actual output — not a paraphrase. A negative result (control passed,
  attempt failed) is exactly as reportable as a positive one; don't
  cherry-pick successes. Append to the existing round structure rather
  than starting a new document each time.
- Always run a control/baseline alongside a suspected bypass (the same
  hook, same shape, without the evasion) — a bypass finding without its
  control is unverified.
- Attribute correctly: a *design decision* ("MEDIUM requires a real
  opus-agent judgment gate, not a static rule") may be the user's; the
  *code implementing it* (regexes, sentinel plumbing, `_hook_common.py`)
  is Claude's, across whichever session wrote it. Don't credit one for
  the other.
- If a finding gets fixed by any session (check `git log` before
  assuming it's still open), append a dated "정정" noting the fix commit
  — don't silently leave stale findings in the log, and don't rewrite
  history to hide that they were ever there.

## Where the log lives

`README.md`, "알려진 한계" section, chronological by round. Read it
before starting a new round — don't re-run a test whose answer is
already there (see the two-tier rule above: this is the most common way
that happens).
