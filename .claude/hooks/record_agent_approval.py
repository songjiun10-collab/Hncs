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
_hook_common.py's module docstring).

**정정(2026-08-20, 침투테스트 라운드 4 - README "알려진 한계" 4차
라운드 #1/#2)**: 두 개 실측 결함을 여기서 고쳤다. (1) `_OPUS_RE`가
`re.search(r"opus", ...)`라 경계가 없어서 `"claude-sonopusnet-5"` 같은
가짜 문자열도 "opus 부분문자열이 있다"는 이유로 통과했다 - 알려진 opus
모델 ID 접두사(`claude-opus-`/`claude-3-opus`/`claude-3.5-opus` 등,
버전 넘버는 유동적이라 "opus" 앞에 `claude-`류 접두사 + 숫자·점이
오는 모양만 앵커)로 좁혔다. (2) 이 훅에 `is_subagent_call()` 게이트가
아예 없어서, 서브에이전트가 자기 턴 안에서 중첩 opus 서브서브에이전트를
디스패치해 자기 자신을 승인하는 경로가 CRITICAL 4개와 달리 안 막혀
있었다 - 이제 `agent_id`가 있는(서브에이전트발) PostToolUse 입력은
마커가 있어도 기록하지 않는다. 두 수정 다 `protect_never_touch.py`/
`protect_destructive.py` 등 CRITICAL 훅이 이미 쓰는 것과 같은 원칙을
그대로 적용한 것 - 새 메커니즘 아님."""
import json
import re
import sys

from _hook_common import is_subagent_call, write_medium_approval

_APPROVE_RE = re.compile(
    r"^\s*MEDIUM-APPROVE:\s*(?P<rule>[\w.-]+)\s*::\s*(?P<target>[^:]+?)\s*::\s*(?P<caution>.+?)\s*$",
    re.MULTILINE,
)
# Anchored to real opus model-ID shapes (claude-opus-5, claude-3-opus,
# claude-3.5-opus-20240229, ...) rather than a bare "opus" substring
# match, which a fabricated resolvedModel string could satisfy without
# being an opus dispatch at all (e.g. "claude-sonopusnet-5").
_OPUS_RE = re.compile(r"claude-(?:\d+(?:\.\d+)?-)?opus\b", re.IGNORECASE)


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
    if is_subagent_call(data):
        return  # a subagent's own nested dispatch can't self-approve
    tr = data.get("tool_response") or {}
    model = str(tr.get("resolvedModel") or "")
    if not _OPUS_RE.search(model):
        return  # only a real opus dispatch counts as a valid approval

    m = _APPROVE_RE.search(response_text(data))
    if not m:
        return
    write_medium_approval(
        m.group("rule"), m.group("target").strip(), m.group("caution").strip())


if __name__ == "__main__":
    main()
