#!/usr/bin/env python3
"""PostToolUse hook (matcher: Edit|Write|MultiEdit). Implements MEDIUM
tier's "단 주의사항 전달" half of the user's spec.

When a MEDIUM-tier PreToolUse guard (protect_generated_files.py /
protect_claim_evidence.py) allows a call via a higher-agent approval
(medium_approval()), it queues the approval's caution text keyed by this
exact call's `tool_use_id` via _hook_common.write_pending_caution(). This
hook runs right after that same call completes, looks up the caution by
the same `tool_use_id` (present on both PreToolUse and PostToolUse hook
input for one call - confirmed empirically 2026-08-15), and delivers it
via `additionalContext`, which PostToolUse is documented to append to the
tool's own result - the one confirmed-solid mechanism for surfacing text
back to the executing agent after an allow (2026-08-15 doc research:
`permissionDecisionReason` on a PreToolUse "allow" never reaches the
model; PreToolUse `additionalContext` support is unsettled in current
docs; PostToolUse `additionalContext` is not).

No-op (prints nothing) when there's no queued caution for this
tool_use_id - the overwhelming majority of Edit/Write/MultiEdit calls."""
import json
import sys

from _hook_common import pop_pending_caution


def read_input():
    return json.load(sys.stdin)


def main():
    data = read_input()
    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        return
    caution = pop_pending_caution(data.get("tool_use_id"))
    if not caution:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": f"[MEDIUM-tier 상위 에이전트 승인 주의사항] {caution}",
    }}))


if __name__ == "__main__":
    main()
