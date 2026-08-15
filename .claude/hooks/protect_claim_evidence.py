#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), MID severity. Scoped
to README.md/README.ko.md/CLAUDE.md/hybrid_engine/EVALUATION.md (any
CLAUDE.md in the tree, not just root - project convention is per-
directory CLAUDE.md files). Root CLAUDE.md: "Make every claim checkable:
name the file, show the number, quote the command you actually ran."

Heuristic: if the text being added contains a numeric performance/scale
claim (%, "배"/"times faster", a bare count like "N brands"/"N presets")
with no nearby evidence marker (a command in backticks, a file path, "실행"
/"확인"/"로그"/"run"/"log"/"verified"), it asks for confirmation rather
than auto-denying - MID severity, unlike the stricter EVALUATION.md-only
experiment-integrity guard. Many legitimate doc edits add a number that's
already obviously checkable from context (e.g. table row counts) without
restating the command inline every time, so this stays a prompt, not a
block."""
import json
import os
import re
import sys

from _hook_common import allow, ask

HOOK_NAME = "protect_claim_evidence"
SEVERITY = "MID"

_TARGET_FILE_RE = re.compile(
    r"(^|/)(README(\.\w+)?\.md|CLAUDE\.md|hybrid_engine/EVALUATION\.md)$")

_NUMERIC_CLAIM_RE = re.compile(
    r"[+-]?\d+(?:\.\d+)?\s*%|"          # +9.12%, 15%
    r"\d+\s*(?:x|배)|"                  # 3x faster, 2배 - no trailing \b:
    r"\b\d+\s*(?:brands?|presets?|프리셋|브랜드|pairs?|쌍)",
    # ^ no trailing \b: Korean particles attach directly to an English
    # word/number with no space ("15 brands를"), and \w is unicode-aware
    # so \b doesn't fire between "brands" and "를" - both count as "word"
    # characters to Python's re module.
    re.IGNORECASE,
)
_EVIDENCE_MARKER_RE = re.compile(
    r"`[^`]+`|"                          # a backtick-quoted command/path
    r"실행|확인됨|검증|로그|run|verified|log\b|\.py\b|\.md\b",
    re.IGNORECASE,
)


def read_input():
    return json.load(sys.stdin)


def is_claim_bearing_doc(path):
    return bool(_TARGET_FILE_RE.search((path or "").replace(os.sep, "/")))


def unbacked_claim_reason(added_text):
    if not _NUMERIC_CLAIM_RE.search(added_text):
        return None
    if _EVIDENCE_MARKER_RE.search(added_text):
        return None
    return (
        "This addition contains a numeric claim with no nearby evidence "
        "marker (a command, file path, or 'verified/run/log' mention). "
        "Root CLAUDE.md: \"Make every claim checkable: name the file, "
        "show the number, quote the command you actually ran.\" Confirm "
        "this number is backed by something checkable."
    )


def main():
    data = read_input()
    tool = data.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path", "")
    if not is_claim_bearing_doc(file_path):
        allow()
        return

    if tool == "Write":
        added_text = ti.get("content", "")
    elif tool == "MultiEdit":
        added_text = "\n".join(e.get("new_string", "") for e in (ti.get("edits") or []))
    else:
        added_text = ti.get("new_string", "")

    reason = unbacked_claim_reason(added_text)
    if reason is None:
        allow()
        return

    ask(reason)


if __name__ == "__main__":
    main()
