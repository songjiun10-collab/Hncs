#!/usr/bin/env python3
"""PreToolUse hook enforcing CLAUDE.md's subagent-driven-development rule:
"Never tell a reviewer what not to flag or pre-rate a finding's severity.
Think it's a false positive -> let it be raised, settle it in the loop."

Scans an Agent-tool dispatch prompt for language that pre-judges a
reviewer's findings before the reviewer has seen the diff. The controller
must rewrite the prompt so any concern about a specific finding is raised
AFTER the reviewer reports it, not baked into the dispatch.

**Known limitation (flagged in code review)**: this is a fixed phrase
blocklist, so it only catches prejudging language that matches one of
these specific patterns - a rephrase ("skip that one", "not worth
flagging", "no significant issue there") passes through undetected. It
raises the bar against the common phrasings observed so far; it is not a
semantic check and cannot be made airtight by adding more phrases alone.

**HIGH severity, override available (2026-08 retrofit).** Denies by
default. Override via the same sentinel-file mechanism as
`protect_never_touch.py` - write `.claude/hooks/.pending_override.json`
with `{"rule": "protect_reviewer_prejudging", "target": "<dispatch
description>", "reason": "<reason>", "timestamp": <time.time()>}`. Kept
HIGH rather than CRITICAL: a prejudged review is recoverable (dispatch a
fresh, unbiased one), unlike data loss or a corrupted shipped artifact."""
import json
import re
import sys

from _hook_common import allow, allow_with_override, deny, sentinel_override

HOOK_NAME = "protect_reviewer_prejudging"
SEVERITY = "HIGH"

# Each pattern pairs a regex with the phrase that triggered it, so the
# denial message can quote the actual match instead of a generic template.
_PREJUDGING_PATTERNS = [
    re.compile(r"do\s*n[o']?t\s+flag", re.IGNORECASE),
    re.compile(r"do\s+not\s+flag", re.IGNORECASE),
    re.compile(r"no\s+need\s+to\s+flag", re.IGNORECASE),
    re.compile(r"don['’]?t\s+treat\s+.{0,60}\s+as\s+a\s+defect", re.IGNORECASE),
    re.compile(r"not\s+a\s+(real\s+)?defect", re.IGNORECASE),
    re.compile(r"at\s+most\s+minor", re.IGNORECASE),
    re.compile(r"the\s+plan\s+chose", re.IGNORECASE),
    re.compile(r"ignore\s+(this|that|the)\s+finding", re.IGNORECASE),
    re.compile(r"don['’]?t\s+(need\s+to\s+)?worry\s+about\s+.{0,40}(finding|issue)", re.IGNORECASE),
]


def read_input():
    return json.load(sys.stdin)


def find_prejudging_phrase(text):
    if not text:
        return None
    for pattern in _PREJUDGING_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        allow()
        return
    ti = data.get("tool_input") or {}
    combined = " ".join(str(ti.get(k, "")) for k in ("prompt", "description"))
    phrase = find_prejudging_phrase(combined)
    if phrase:
        target = str(ti.get("description", "")) or combined[:80]
        override_reason = sentinel_override(HOOK_NAME, target)
        if override_reason:
            allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason)
            return
        deny(
            HOOK_NAME,
            "CLAUDE.md subagent-driven-development rule: \"Never tell a "
            "reviewer what not to flag or pre-rate a finding's severity. "
            "Think it's a false positive -> let it be raised, settle it "
            "in the loop.\" This dispatch prompt pre-judges a finding "
            f"(matched: \"{phrase}\"). Rewrite the dispatch so the "
            "reviewer sees the diff cold - if you believe a concern is a "
            "false positive, raise that AFTER the reviewer reports it, "
            f'not before. To override: write '
            f'.claude/hooks/.pending_override.json with {{"rule": '
            f'"{HOOK_NAME}", "target": "{target}", "reason": "<reason>", '
            '"timestamp": <time.time()>}, then retry immediately.',
            severity=SEVERITY,
        )
        return
    allow()


if __name__ == "__main__":
    main()
