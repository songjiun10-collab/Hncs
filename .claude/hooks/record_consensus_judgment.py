#!/usr/bin/env python3
"""PostToolUse hook (matcher: Agent). Implements the 2-Agent Consensus
half of the HNCS Hook Evolution phase 1 design
(docs/superpowers/specs/2026-08-19-hook-evolution-design.md, section 5;
docs/superpowers/plans/2026-08-19-hook-evolution-phase1-consensus.md,
Task 2) - watches every completed Agent dispatch's response for an
explicit consensus marker, one line anywhere in the subagent's final
response:

    CONSENSUS-VERDICT: <rule> :: <target> :: <role:A|B> :: <SAFE|RISKY> :: <reasoning>

Same field-shape and matching discipline as record_agent_approval.py's
MEDIUM-APPROVE marker (see that file's docstring) - `tool_response.
content[0].text`/`resolvedModel` confirmed present on PostToolUse's Agent
matcher input via the same 2026-08-15 live-dispatch measurement. Requires
resolvedModel to match opus (anchored `^claude-opus-`, NOT the bare
substring `re.compile(r"opus")` record_agent_approval.py uses - the 4차
라운드 finding #1 in `.claude/hooks/README.md` already documented that
substring match as a real code-level defect there; this file doesn't
repeat it). Opus-for-both requirement is this plan's stated default
assumption (see the plan's Global Constraints), not yet a user-confirmed
decision the way MEDIUM's opus-only bar was.

Two independent dispatches (role A, role B - different framing per the
2026-08-19 brainstorming decision, NOT different models) each produce
their own PostToolUse event and each call write_consensus_verdict()
separately - `_hook_common.consensus_verdict()` merges them and only
resolves once both roles have reported (see that function's docstring)."""
import json
import re
import sys

from _hook_common import write_consensus_verdict

_VERDICT_RE = re.compile(
    r"^\s*CONSENSUS-VERDICT:\s*(?P<rule>[\w.-]+)\s*::\s*(?P<target>[^:]+?)\s*::\s*"
    r"(?P<role>[AB])\s*::\s*(?P<verdict>SAFE|RISKY)\s*::\s*(?P<reasoning>.+?)\s*$",
    re.MULTILINE,
)
_OPUS_RE = re.compile(r"^claude-opus-", re.IGNORECASE)


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
    if not _OPUS_RE.match(model):
        return  # only opus dispatches count - see module docstring

    m = _VERDICT_RE.search(response_text(data))
    if not m:
        return
    write_consensus_verdict(
        m.group("rule"), m.group("target").strip(), m.group("role"),
        m.group("verdict"), m.group("reasoning").strip())


if __name__ == "__main__":
    main()
