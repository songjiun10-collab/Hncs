#!/usr/bin/env python3
"""PreToolUse hook enforcing CLAUDE.md's subagent-driven-development rule:
"Never tell a reviewer what not to flag or pre-rate a finding's severity.
Think it's a false positive -> let it be raised, settle it in the loop."

Scans an Agent-tool dispatch prompt for language that pre-judges a
reviewer's findings before the reviewer has seen the diff. Denies the
dispatch outright - there is no bypass through this hook. The controller
must rewrite the prompt so any concern about a specific finding is raised
AFTER the reviewer reports it, not baked into the dispatch."""
import json
import re
import sys

from _hook_common import allow, deny

HOOK_NAME = "protect_reviewer_prejudging"

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
        deny(
            HOOK_NAME,
            "CLAUDE.md subagent-driven-development rule: \"Never tell a "
            "reviewer what not to flag or pre-rate a finding's severity. "
            "Think it's a false positive -> let it be raised, settle it "
            "in the loop.\" This dispatch prompt pre-judges a finding "
            f"(matched: \"{phrase}\"). Rewrite the dispatch so the "
            "reviewer sees the diff cold - if you believe a concern is a "
            "false positive, raise that AFTER the reviewer reports it, "
            "not before. This hook has no bypass."
        )
        return
    allow()


if __name__ == "__main__":
    main()
