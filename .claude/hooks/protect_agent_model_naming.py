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

**MID severity (2026-08 retrofit).** `ask()` - falls through to Claude
Code's normal permission prompt rather than a hard deny. Unlike the other
"review agent" hooks, a missing/haiku model is a cost-efficiency issue,
not a correctness or safety one - worth a human glance, not worth
blocking outright with an override dance."""
import json
import re
import sys

from _hook_common import allow, ask

HOOK_NAME = "protect_agent_model_naming"
SEVERITY = "MID"

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
        ask(
            "CLAUDE.md Controller rule: \"Always name the model (omitting "
            "it inherits the session's, usually the priciest).\" This "
            "dispatch has no `model` field. Set model explicitly - "
            "`sonnet` by default, `opus` only for architecture/final "
            "whole-branch review."
        )
        return

    if _HAIKU_RE.search(str(model)):
        ask(
            "CLAUDE.md Controller rule: \"Skip haiku - its extra turns on "
            f"multi-step work cost more than the tokens it saves.\" This "
            f"dispatch names model={model!r}. Use `sonnet` (default) or "
            "`opus` (architecture/final whole-branch review only)."
        )
        return

    allow()


if __name__ == "__main__":
    main()
