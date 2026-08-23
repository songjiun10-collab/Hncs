#!/usr/bin/env python3
"""PreToolUse hook (matcher: Edit|Write|MultiEdit), MEDIUM severity. This
codebase doesn't have a `src/generated*` directory, but it has the same
shape of risk: `_LEARNED_LUT`/`_LEARNED_LUT_V2` numpy array literals in
`brands/*_learned.py` are measurement output from `tools/fit_final_lut.py`
(raw+jpeg pairs -> per-bin averages -> PAVA smoothing), not hand-tuned
constants. Hand-editing the array numbers directly would silently
desync the shipped LUT from anything the fitting pipeline could
reproduce or re-verify - the exact failure mode "generated file, don't
hand-edit" guards against elsewhere.

MEDIUM severity: deny unless a genuine "상위 에이전트" (opus) approves via
the MEDIUM-APPROVE marker mechanism - not a hard block, since sometimes a
small hand-correction genuinely is the intended fix (this session's own
PAVA non-monotonic-cliff correction was a full regeneration, but a
one-value typo fix might not warrant re-running a 2-hour fit).

**정정(2026-08-15)**: 원래 `ask()`를 썼는데, subagent 디스패치로 실측한
결과 subagent의 Edit 콜에서는 `ask()`가 프롬프트 없이 조용히 통과됨
(subagent 컨텍스트엔 프롬프트를 띄울 화면이 없어서로 추정). 이
프로젝트는 Controller가 subagent를 디스패치해서 실제 작업을 시키는
워크플로우라 `ask()`는 정확히 그 경우에 보호 기능이 0. deny + sentinel
override로 바꿔서 orchestrator/subagent 둘 다 동일하게 동작하게 함.

**정정(2026-08-16)**: "그 애매한 중간단계?" - plain self-declared
override(bash 주석/sentinel)가 MEDIUM-APPROVE와 나란히 열려있으니
컨트롤러가 항상 더 쉬운 쪽(override 한 줄)을 써서 "상위 에이전트 승인"
경로가 사실상 죽은 코드였음. **plain override 제거, MEDIUM-APPROVE(opus
전용)만 유효** - HIGH(ask)/CRITICAL(subagent 차단)처럼 진짜 구분되는
메커니즘이 되도록.

**정정(2026-08-19)**: `touched_lut_array()`가 AST 파싱 실패
(`lut_array_ranges()` -> `None`)와 LUT 배열 없음(`-> []`)을
`if not ranges` 한 줄로 동일하게 취급해 fail-OPEN이었음 - 파일이 조금만
손상돼도 이 가드가 통째로 무력화되는 비대칭 버그(외부 AI 리뷰로
발견, `protect_never_touch.py`의 `touched_function()`이 이미 쓰고 있는
`"__unknown__"` fail-closed 패턴과 대조해서 확인). 파싱 실패 시
`"__unknown__"`을 반환하도록 분리하고, `main()`에서 그 경우를 별도
deny 경로로 처리하도록 수정.

**추가 (2026-08-20, README "알려진 한계" 9차 라운드 B - 대응 방향
반영)**: 배치 검토(여러 브랜드를 한 디스패치로 같이 확인해달라는 요청)에서
opus 승인자가 "커밋 메시지/diff 패턴이 서로 내적으로 일관됨"만으로
마커를 낸 사례가 실측됐다 - 코드 결함이 아니라 디스패치 프롬프트
설계에만 의존하던 행동 레벨 위험이라, deny 메시지 자체에 재현
가능성을 스스로 자문하게 하는 체크리스트를 박아 넣어 프롬프트 설계와
무관하게 항상 보이게 함(아래 deny 메시지의 체크리스트 항목)."""
import ast
import json
import os
import re
import sys

from _hook_common import (allow, allow_with_medium_approval, deny, medium_approval,
                           require_decision_or_deny, write_pending_caution)

HOOK_NAME = "protect_generated_files"
SEVERITY = "MEDIUM"

_LEARNED_LUT_FILE_RE = re.compile(r"(^|/)brands/[^/]*_learned\.py$")
_LUT_ASSIGN_NAME_RE = re.compile(r"^_LEARNED_LUT\w*$")


def read_input():
    return json.load(sys.stdin)


def normalize(path):
    return (path or "").replace(os.sep, "/")


def is_learned_brand_file(path):
    return bool(_LEARNED_LUT_FILE_RE.search(normalize(path)))


def lut_array_ranges(file_path):
    """Returns [(name, start_line, end_line), ...] for every module-level
    `_LEARNED_LUT*= np.array([...])` assignment, or None if unparseable."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return None
    ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and _LUT_ASSIGN_NAME_RE.match(t.id):
                    end = getattr(node, "end_lineno", node.lineno)
                    ranges.append((t.id, node.lineno, end))
    return ranges


def line_of_offset(text, offset):
    return text.count("\n", 0, offset) + 1


def touched_lut_array(file_path, old_string):
    """Returns the LUT array name touched by old_string, `"__unknown__"` if
    file_path couldn't be parsed (fail-closed - see lut_array_ranges()), or
    None if it's clear."""
    if not old_string or not os.path.exists(file_path):
        return None
    with open(file_path, encoding="utf-8") as f:
        text = f.read()
    ranges = lut_array_ranges(file_path)
    if ranges is None:
        return "__unknown__"
    if not ranges:
        return None
    idx = text.find(old_string)
    if idx == -1:
        return None
    start_line = line_of_offset(text, idx)
    end_line = line_of_offset(text, idx + len(old_string))
    for name, s, e in ranges:
        if start_line <= e and end_line >= s:
            return name
    return None


def _deny_or_override(target, reason, tool_use_id=None):
    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, target, reason)
    if decision is None:
        return
    caution = medium_approval(HOOK_NAME, target)
    if caution is not None:
        write_pending_caution(tool_use_id, caution)
        allow_with_medium_approval(HOOK_NAME, SEVERITY, HOOK_NAME, target, caution,
                                    decision=decision)
        return
    deny(
        HOOK_NAME,
        f"{reason} No plain override for MEDIUM (2026-08-16: removed - it "
        "made the opus-approval path pointless since a one-line override "
        "was always easier). Dispatch an opus Agent whose response "
        f'contains "MEDIUM-APPROVE: {HOOK_NAME} :: {target} :: <caution>" '
        "- the next matching call will be let through with that caution "
        "delivered back to you. Before issuing MEDIUM-APPROVE, the "
        "approving agent should be able to answer yes to: (1) did I "
        "actually reproduce this value from tools/fit_final_lut.py or an "
        "equivalent re-run, not just check that a commit message and diff "
        "shape are internally consistent with each other? (2) if this is "
        "one of several items in a batch, did I verify this specific item "
        "on its own, not by pattern-matching it against the others in the "
        "batch?",
        severity=SEVERITY, target=target, decision=decision,
    )


def main():
    data = read_input()
    tool = data.get("tool_name")
    if tool not in ("Edit", "Write", "MultiEdit"):
        allow()
        return
    ti = data.get("tool_input") or {}
    file_path = ti.get("file_path", "")
    tool_use_id = data.get("tool_use_id")
    if not file_path or not is_learned_brand_file(file_path):
        allow()
        return

    if tool == "Write":
        # Overwriting the whole file could plausibly rewrite the LUT too -
        # can't tell from a Write call alone, so flag rather than guess.
        _deny_or_override(
            file_path,
            f"{file_path} contains a _LEARNED_LUT array generated by "
            "tools/fit_final_lut.py - a Write overwrites the whole file, "
            "which may include hand-editing that array instead of "
            "regenerating it. Confirm this isn't a hand-edit of the LUT "
            "values, or regenerate via tools/fit_final_lut.py instead.",
            tool_use_id=tool_use_id,
        )
        return

    if tool == "MultiEdit":
        edits = ti.get("edits") or []
    else:
        edits = [{"old_string": ti.get("old_string", "")}]

    for e in edits:
        name = touched_lut_array(file_path, e.get("old_string", ""))
        if name == "__unknown__":
            _deny_or_override(
                file_path,
                f"Couldn't parse the current contents of {file_path} to "
                "check for _LEARNED_LUT arrays before this edit. Blocking "
                "to be safe - confirm this isn't a hand-edit of the LUT "
                "values, or fix whatever broke the parse.",
                tool_use_id=tool_use_id,
            )
            return
        if name:
            _deny_or_override(
                file_path,
                f"This edit touches `{name}` in {file_path}, a numpy array "
                "generated by tools/fit_final_lut.py (raw+jpeg fitting + "
                "PAVA smoothing), not a hand-tuned constant. Hand-editing "
                "the numbers desyncs the shipped LUT from anything the "
                "fitting pipeline could reproduce. Confirm this is "
                "intentional (e.g. reverting to a re-generated array), or "
                "re-run tools/fit_final_lut.py instead.",
                tool_use_id=tool_use_id,
            )
            return

    allow()


if __name__ == "__main__":
    main()
