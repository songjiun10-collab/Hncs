"""Shared allow/deny helpers for this project's PreToolUse/PostToolUse
hooks. Every deny() call also appends a line to violations_log.jsonl
(tracked in git) - a running, append-only record of every rule violation
these hooks actually caught. This is the raw material for
docs/session_retrospectives-style CLAUDE.md entries: instead of relying
on someone remembering to write up an incident after the fact, the catch
itself is recorded automatically at the moment it happens."""
import json
import os
import sys
from datetime import datetime, timezone

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "violations_log.jsonl")


def allow():
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))


def deny(hook_name, reason):
    _log_violation(hook_name, reason)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def _log_violation(hook_name, reason):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hook": hook_name,
        "reason": reason,
    }
    try:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Logging must never be why a real deny fails to reach the caller.
        print(f"[_hook_common] failed to write violations log: {e}",
              file=sys.stderr)
