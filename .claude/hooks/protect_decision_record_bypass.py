#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), no override, no
decision-record gate of its own - denying writes to the decision-record
sentinel itself is what makes `must_hook_server.py`'s
`write_decision_record` MCP tool the sole channel for writing it.

Before this hook existed, any hook's `require_decision_or_deny()` deny
message told the agent to write `.pending_decision_record.json` directly
via the Write tool - free-text JSON with no schema check until read back.
must훅 (2026-08-16) replaces that with an MCP tool whose parameter schema
rejects malformed calls before they reach any code. That only holds if the
raw-Write path is closed - otherwise an agent could still hand-write a
matching-shape JSON file and skip the schema entirely. This hook closes
it: any Edit/Write/MultiEdit targeting the sentinel path is denied,
unconditionally.

No override, no decision record required for this hook itself -
requiring a decision record to protect the decision-record mechanism
would be circular, and any override would defeat the point of the
schema-enforced-only-channel design."""
import json
import os
import sys

from _hook_common import _DECISION_RECORD_PATH, allow, deny

HOOK_NAME = "protect_decision_record_bypass"
SEVERITY = "CRITICAL"


def read_input():
    return json.load(sys.stdin)


def is_decision_record_path(file_path):
    if not file_path:
        return False
    return os.path.abspath(file_path) == os.path.abspath(_DECISION_RECORD_PATH)


def main():
    data = read_input()
    if data.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not is_decision_record_path(file_path):
        allow()
        return
    deny(
        HOOK_NAME,
        f"{file_path}는 must_hook_server.py의 write_decision_record MCP 툴로만 "
        "써야 함(2026-08-16) - Write/Edit로 직접 쓰는 건 스키마 검증을 우회하는 "
        "경로라 항상 막힘, override 없음. "
        "mcp__must_hook__write_decision_record 툴을 호출할 것.",
        severity=SEVERITY, target=file_path,
    )


if __name__ == "__main__":
    main()
