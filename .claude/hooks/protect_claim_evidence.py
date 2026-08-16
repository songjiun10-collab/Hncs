#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), MEDIUM severity. Scoped
to README.md/README.ko.md/CLAUDE.md/hybrid_engine/EVALUATION.md (any
CLAUDE.md in the tree, not just root - project convention is per-
directory CLAUDE.md files). Root CLAUDE.md: "Make every claim checkable:
name the file, show the number, quote the command you actually ran."

Heuristic: if the text being added contains a numeric performance/scale
claim (%, "배"/"times faster", a bare count like "N brands"/"N presets")
with no nearby evidence marker (a command in backticks, a file path, "실행"
/"확인"/"로그"/"run"/"log"/"verified"), it flags it. Many legitimate doc
edits add a number that's already obviously checkable from context (e.g.
table row counts) without restating the command inline every time, so
this is MEDIUM (softer default), not HIGH/CRITICAL.

**정정(2026-08-15)**: 원래 `ask()`(사람 확인 프롬프트)를 썼는데, 서브
에이전트로 실측한 결과 디스패치된 subagent의 Edit 콜에서는 `ask()`가
아무 denial도 ask 프롬프트도 없이 그냥 조용히 통과됨(subagent 컨텍스트엔
프롬프트를 띄울 화면이 없어서로 추정 - fail-open 방향). 이 프로젝트의
평상시 워크플로우가 Controller가 subagent를 디스패치해서 실제 작업을
시키는 구조라, `ask()`는 정확히 그 경우에 보호 기능이 0이 됨. deny +
override로 바꿔서 orchestrator든 subagent든 동일하게 동작하도록 함(둘 다
결정론적 파일/텍스트 체크지 UI 렌더링에 안 기댐) - MEDIUM 등급 라벨은
유지하되(정말 사소한 건 override 한 줄로 바로 뚫림), 메커니즘은 HIGH와
같은 sentinel override."""
import json
import os
import re
import sys

from _hook_common import (allow, allow_with_medium_approval, allow_with_override,
                           deny, medium_approval, sentinel_override, write_pending_caution)

HOOK_NAME = "protect_claim_evidence"
SEVERITY = "MEDIUM"

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

    override_reason = sentinel_override(HOOK_NAME, file_path)
    if override_reason:
        allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, file_path, override_reason)
        return

    caution = medium_approval(HOOK_NAME, file_path)
    if caution is not None:
        write_pending_caution(data.get("tool_use_id"), caution)
        allow_with_medium_approval(HOOK_NAME, SEVERITY, HOOK_NAME, file_path, caution)
        return

    deny(
        HOOK_NAME,
        f"{reason} To override: write .claude/hooks/.pending_override.json "
        f'with {{"rule": "{HOOK_NAME}", "target": "{file_path}", "reason": '
        '"<reason>", "timestamp": <time.time()>}, then retry immediately. '
        "Or: dispatch a sonnet/opus Agent whose response contains "
        f'"MEDIUM-APPROVE: {HOOK_NAME} :: {file_path} :: <caution>" - the '
        "next matching call will be let through with that caution "
        "delivered back to you.",
        severity=SEVERITY,
    )


if __name__ == "__main__":
    main()
