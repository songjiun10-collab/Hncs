#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), no override, no
decision-record gate of its own - denying writes to a protected sentinel
path is what makes each sentinel's dedicated writer (an MCP tool or a
PostToolUse hook parsing a real Agent dispatch) the sole channel for it.

Before this hook existed, any hook's `require_decision_or_deny()` deny
message told the agent to write `.pending_decision_record.json` directly
via the Write tool - free-text JSON with no schema check until read back.
must훅 (2026-08-16) replaces that with an MCP tool whose parameter schema
rejects malformed calls before they reach any code. That only holds if the
raw-Write path is closed - otherwise an agent could still hand-write a
matching-shape JSON file and skip the schema entirely. This hook closes
it for `_DECISION_RECORD_PATH`, unconditionally.

**정정(2026-08-19, HNCS Hook Evolution phase 1)**: generalized from a
single hardcoded path to a small table of protected sentinels, now also
covering `_CONSENSUS_PATH` (`.pending_consensus.json`, written only by
`record_consensus_judgment.py` after parsing a real two-agent dispatch's
CONSENSUS-VERDICT markers - see `_hook_common.py`'s module docstring).
This is the exact fix the 2차 라운드 finding #8 in
`.claude/hooks/README.md` recommended for `.last_whole_branch_review_sha`
(a sentinel shipped with zero Edit/Write coverage, later exploited),
applied here to the new sentinel *before* shipping rather than after a
pentest finds the gap. `.last_whole_branch_review_sha` itself is a
separate, still-open finding (different file, different writer hook,
different fix location - `protect_ready_without_review.py`'s domain, not
this one) and is intentionally NOT added to this table by this change.

No override, no decision record required for this hook itself -
requiring a decision record to protect the decision-record mechanism
would be circular, and any override would defeat the point of the
schema/dedicated-writer-enforced-only-channel design."""
import json
import os
import sys

from _hook_common import _CONSENSUS_PATH, _DECISION_RECORD_PATH, allow, deny

HOOK_NAME = "protect_decision_record_bypass"
SEVERITY = "CRITICAL"

_PROTECTED_SENTINELS = {
    os.path.abspath(_DECISION_RECORD_PATH): (
        "must_hook_server.py의 write_decision_record MCP 툴"),
    os.path.abspath(_CONSENSUS_PATH): (
        "record_consensus_judgment.py (PostToolUse, 실제 2-agent Dispatch 응답 파싱)"),
}


def read_input():
    return json.load(sys.stdin)


def protected_sentinel_writer(file_path):
    """Returns a description of the one legitimate writer for file_path,
    or None if file_path isn't a protected sentinel at all."""
    if not file_path:
        return None
    return _PROTECTED_SENTINELS.get(os.path.abspath(file_path))


def main():
    data = read_input()
    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    writer = protected_sentinel_writer(file_path)
    if writer is None:
        allow()
        return
    deny(
        HOOK_NAME,
        f"{file_path}는 {writer}로만 써야 함 - Write/Edit로 직접 쓰는 건 "
        "검증을 우회하는 경로라 항상 막힘, override 없음.",
        severity=SEVERITY, target=file_path,
    )


if __name__ == "__main__":
    main()
