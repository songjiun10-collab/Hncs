#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent) enforcing CLAUDE.md's Controller rule:
"Always name the model (omitting it inherits the session's, usually the
priciest). sonnet is the default for implementation and review; opus only
for architecture and the final whole-branch review. Skip haiku."

Flags an Agent dispatch that omits `model` entirely, or sets it to a
haiku variant. This hook can't judge whether sonnet vs opus is the right
call for a given task - that's a real judgment call left to the
controller - it only catches the two mechanically-checkable violations:
no model named at all, and haiku.

**LOW severity, log-only (2026-08-15, re-tiered).** Went deny -> ask ->
deny -> here. The deny+override churn (see git history) was itself the
signal: this flip-flopped three times in one session because a missing/
haiku model is a genuine cost-efficiency nit, not a correctness or safety
issue, and blocking work over it - even with a one-line override escape
hatch - was solving a problem this finding doesn't actually have. Now it
just logs to violations_log.jsonl (visible to a human reviewing later)
and always allows - no interruption, no override dance needed. This is
also the concrete split of the "MID/HIGH/CRITICAL all mechanically
collapsed to deny+override" limitation: not everything bucketed there
actually earns interrupting the current action, and this hook didn't.
`protect_generated_files.py`/`protect_claim_evidence.py` (the other two
former ask()-users) stay at MID deny+override - their findings (hand-
editing a shipped generated LUT array; adding an unbacked numeric claim
to docs, the same failure mode `docs/CLAUDE.md`'s confirmation-bias
section documents a real past incident of) have real enough consequences
to justify the friction."""
import json
import re
import sys

from _hook_common import allow, log_and_allow

HOOK_NAME = "protect_agent_model_naming"
SEVERITY = "LOW"

_HAIKU_RE = re.compile(r"haiku", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        allow()
        return
    ti = data.get("tool_input") or {}
    model = ti.get("model")

    if not model:
        log_and_allow(
            HOOK_NAME, SEVERITY,
            "CLAUDE.md Controller rule: \"Always name the model (omitting "
            "it inherits the session's, usually the priciest).\" This "
            "dispatch has no `model` field. Set model explicitly - "
            "`sonnet` by default, `opus` only for architecture/final "
            "whole-branch review."
        )
        return

    if _HAIKU_RE.search(str(model)):
        log_and_allow(
            HOOK_NAME, SEVERITY,
            "CLAUDE.md Controller rule: \"Skip haiku - its extra turns on "
            f"multi-step work cost more than the tokens it saves.\" This "
            f"dispatch names model={model!r}. Use `sonnet` (default) or "
            "`opus` (architecture/final whole-branch review only)."
        )
        return

    allow()


if __name__ == "__main__":
    main()
