#!/usr/bin/env python3
"""PostToolUse hook (matcher: Agent). Part of enforcing CLAUDE.md's "Don't
skip the final whole-branch review; it caught three critical bugs."

When an Agent dispatch looks like the final whole-branch review (mentions
the review skill/phrase), records the current git HEAD sha to a sentinel
file. protect_ready_without_review.py (PreToolUse on marking a PR ready)
reads this sentinel to confirm a whole-branch review actually happened at
the current commit before the PR can leave draft.

**Known limitation (flagged in code review)**: this only checks that a
dispatch *prompt* mentioned review language - it does not verify the
dispatched agent actually ran, returned, or reported a clean result before
recording the sentinel. A dispatch that matches the pattern but fails,
gets interrupted, or returns findings still marks the sentinel as
satisfied. Combined with protect_reviewer_prejudging.py's phrase-blocklist
limitation above, "PR left draft" mechanically guarantees only that a
review-shaped Agent call was *made* at this commit, not that it passed."""
import json
import re
import subprocess
import sys
from pathlib import Path

_SENTINEL = Path(__file__).parent / ".last_whole_branch_review_sha"

_REVIEW_MARKERS = re.compile(
    r"whole[- ]branch review|final.{0,20}review|requesting-code-review|code-reviewer",
    re.IGNORECASE,
)


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
    if data.get("tool_name") != "Agent":
        return
    ti = data.get("tool_input") or {}
    combined = " ".join(str(ti.get(k, "")) for k in ("prompt", "description"))
    if not _REVIEW_MARKERS.search(combined):
        return
    sha = current_head_sha()
    if sha:
        _SENTINEL.write_text(sha)


if __name__ == "__main__":
    main()
