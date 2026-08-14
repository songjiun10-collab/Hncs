#!/usr/bin/env python3
"""PreToolUse hook (matcher: mcp__github__update_pull_request) enforcing
CLAUDE.md's "Don't skip the final whole-branch review; it caught three
critical bugs."

Blocks marking a pull request ready-for-review (draft: false) unless
record_whole_branch_review.py's sentinel shows a whole-branch-review-type
Agent dispatch happened at the CURRENT git HEAD - any commit since the
last recorded review invalidates it, since a "whole-branch review" is
only meaningful against the branch's actual current state."""
import json
import subprocess
import sys
from pathlib import Path

from _hook_common import allow, deny

HOOK_NAME = "protect_ready_without_review"

_SENTINEL = Path(__file__).parent / ".last_whole_branch_review_sha"


def read_input():
    return json.load(sys.stdin)


def current_head_sha():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=10, cwd=Path(__file__).parent)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def main():
    data = read_input()
    ti = data.get("tool_input") or {}
    if ti.get("draft") is not False:
        allow()  # not a ready-for-review transition
        return

    reviewed_sha = _SENTINEL.read_text().strip() if _SENTINEL.exists() else None
    current_sha = current_head_sha()

    if reviewed_sha and current_sha and reviewed_sha == current_sha:
        allow()
        return

    if reviewed_sha and current_sha and reviewed_sha != current_sha:
        detail = (f"last whole-branch review was at {reviewed_sha[:7]}, "
                   f"current HEAD is {current_sha[:7]} - new commits landed since")
    else:
        detail = "no whole-branch review has been dispatched in this session"

    deny(
        HOOK_NAME,
        "CLAUDE.md: \"Don't skip the final whole-branch review; it caught "
        f"three critical bugs.\" Blocking draft->ready ({detail}). Dispatch "
        "a final whole-branch review Agent (superpowers:requesting-code-review "
        "style, mentioning \"whole-branch review\" in the prompt) against the "
        "current HEAD before marking this PR ready. This hook has no bypass."
    )


if __name__ == "__main__":
    main()
