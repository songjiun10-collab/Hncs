#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent) enforcing CLAUDE.md's Controller rule:
"Always name the model (omitting it inherits the session's, usually the
priciest). sonnet is the default for implementation and review; opus only
for architecture and the final whole-branch review. Skip haiku."

Denies an Agent dispatch that omits `model` entirely, or sets it to a
haiku variant. This hook can't judge whether sonnet vs opus is the right
call for a given task - that's a real judgment call left to the
controller - it only catches the two mechanically-checkable violations:
no model named at all, and haiku."""
import json
import re
import sys

_HAIKU_RE = re.compile(r"haiku", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def allow():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        allow()
        return
    ti = data.get("tool_input") or {}
    model = ti.get("model")

    if not model:
        deny(
            "CLAUDE.md Controller rule: \"Always name the model (omitting "
            "it inherits the session's, usually the priciest).\" This "
            "dispatch has no `model` field. Set model explicitly - "
            "`sonnet` by default, `opus` only for architecture/final "
            "whole-branch review. This hook has no bypass."
        )
        return

    if _HAIKU_RE.search(str(model)):
        deny(
            "CLAUDE.md Controller rule: \"Skip haiku - its extra turns on "
            f"multi-step work cost more than the tokens it saves.\" This "
            f"dispatch names model={model!r}. Use `sonnet` (default) or "
            "`opus` (architecture/final whole-branch review only). This "
            "hook has no bypass."
        )
        return

    allow()


if __name__ == "__main__":
    main()
