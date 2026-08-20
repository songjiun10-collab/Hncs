#!/usr/bin/env python3
"""PostToolUse hook (matcher: Agent). Implements MEDIUM tier's "상위
에이전트가 허용하면 실행 에이전트가 실행" half of the user's spec -
 watches every completed Agent dispatch's response text for an explicit
approval marker, one line anywhere in the subagent's final response:

    MEDIUM-APPROVE: <rule> :: <target> :: <caution text>

`tool_response.content[0].text` (the dispatched subagent's full final
response) is confirmed present on PostToolUse's Agent-matcher input
(2026-08-15, live dispatch + diagnostic hook). Requires the dispatch's
`resolvedModel` to be opus specifically (2026-08-16, user correction:
"에이전트는 오퍼스 허락만 유효" - only an opus dispatch's approval
counts) - sonnet, haiku, and no-model dispatches are all rejected. A
higher-stakes bar than CLAUDE.md's general Controller rule (sonnet
default, opus only for architecture/final whole-branch review), because
this specific marker is standing in for a human-grade "상위 에이전트"
sign-off, not routine implementation/review work.

On a match, records the approval via _hook_common.write_medium_approval()
- consumed by the MEDIUM-tier PreToolUse guard (protect_generated_files.py
/ protect_claim_evidence.py) the next time it sees a matching rule+target.

This does NOT verify the approval is *substantively* correct - only that
a real Agent dispatch happened, used a strong-enough model, and its
response contains the marker in the right shape. Same "conscious action +
logged, not verified-true" tradeoff as every override mechanism here (see
_hook_common.py's module docstring)."""
import json
import re
import sys

from _hook_common import write_medium_approval

_APPROVE_RE = re.compile(
    r"^\s*MEDIUM-APPROVE:\s*(?P<rule>[\w.-]+)\s*::\s*(?P<target>[^:]+?)\s*::\s*(?P<caution>.+?)\s*$",
    re.MULTILINE,
)
_OPUS_RE = re.compile(r"opus", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def response_text(data):
    tr = data.get("tool_response") or {}
    content = tr.get("content") or []
    parts = [c.get("text", "") for c in content
             if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(parts)


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        return
    tr = data.get("tool_response") or {}
    model = str(tr.get("resolvedModel") or "")
    if not _OPUS_RE.search(model):
        return  # only opus dispatches count as a valid approval

    m = _APPROVE_RE.search(response_text(data))
    if not m:
        return
    write_medium_approval(
        m.group("rule"), m.group("target").strip(), m.group("caution").strip())


if __name__ == "__main__":
    main()
