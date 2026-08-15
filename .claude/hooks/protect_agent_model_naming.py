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

**MID severity, deny + sentinel override (2026-08-15, corrected).**
First retrofit used `ask()` on the theory that a missing/haiku model is a
cost-efficiency issue, not a safety one, so a human glance beat a hard
block. Reverted after subagent testing showed `ask()` silently resolves
to allow when there's no interactive surface to render the prompt on
(confirmed for a dispatched subagent's own tool calls; an Agent dispatch
that itself spawns a nested Agent call would hit the same gap). Kept MID
severity/labeling (still a lighter-weight override bar than HIGH/
CRITICAL in spirit), but the mechanism is now the same deterministic
sentinel-override path as everything else, since that's the one proven
to behave identically whether the caller is the orchestrator or a
subagent."""
import json
import re
import sys

from _hook_common import allow, allow_with_override, deny, sentinel_override

HOOK_NAME = "protect_agent_model_naming"
SEVERITY = "MID"

_HAIKU_RE = re.compile(r"haiku", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def _deny_or_override(target, reason):
    override_reason = sentinel_override(HOOK_NAME, target)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason)
        return
    deny(
        HOOK_NAME,
        f"{reason} To override: write .claude/hooks/.pending_override.json "
        f'with {{"rule": "{HOOK_NAME}", "target": "{target}", "reason": '
        '"<reason>", "timestamp": <time.time()>}, then retry immediately.',
        severity=SEVERITY,
    )


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        allow()
        return
    ti = data.get("tool_input") or {}
    model = ti.get("model")
    target = str(ti.get("description", "")) or str(ti.get("prompt", ""))[:80]

    if not model:
        _deny_or_override(
            target,
            "CLAUDE.md Controller rule: \"Always name the model (omitting "
            "it inherits the session's, usually the priciest).\" This "
            "dispatch has no `model` field. Set model explicitly - "
            "`sonnet` by default, `opus` only for architecture/final "
            "whole-branch review."
        )
        return

    if _HAIKU_RE.search(str(model)):
        _deny_or_override(
            target,
            "CLAUDE.md Controller rule: \"Skip haiku - its extra turns on "
            f"multi-step work cost more than the tokens it saves.\" This "
            f"dispatch names model={model!r}. Use `sonnet` (default) or "
            "`opus` (architecture/final whole-branch review only)."
        )
        return

    allow()


if __name__ == "__main__":
    main()
