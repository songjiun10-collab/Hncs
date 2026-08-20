#!/usr/bin/env python3
"""PreToolUse hook (matcher: Agent), HIGH severity. Companion to
protect_reviewer_prejudging.py - same mechanism, different target: instead
of catching a dispatch prompt that pre-judges a REVIEWER's findings, this
catches a dispatch prompt that tells a MEDIUM-tier approver to skip real
review and just emit the MEDIUM-APPROVE marker.

**Discovered 2026-08-18** (탐지/rubber-stamp 침투테스트 시도 중):
`tests/test_hooks_medium_approval.py`가 이미 이 결함을 코드로
증명하고 있었다 - `TestRecordAgentApproval.
test_opus_response_with_marker_records_approval`은
`record_agent_approval.py`가 opus 모델 응답이 MEDIUM-APPROVE 마커만
포함하면(실제 검토 여부 검증 전혀 없이) 그대로 승인을 기록함을 보여주고,
`TestProtectGeneratedFilesMediumApprovalEndToEnd.
test_medium_approval_allows_and_queues_caution`은 그 승인이 있으면
`protect_generated_files.py`가 무조건 신뢰해서 실제 생성 파일 수정을
통과시킴을 보여준다. 둘을 이으면: 컨트롤러가 디스패치 프롬프트를
"이 마커만 출력해, 실제로 파일 안 열어봐도 돼"로 지으면 MEDIUM 게이트가
전적으로 무력화된다 - 이 아키텍처는 "진짜 검토가 있었는지"를 전혀 검증
못하고 "그 문자열이 있는 opus 응답이 있었는지"만 보기 때문.

이 훅도 진짜 검토 여부를 검증하지는 못한다(protect_reviewer_prejudging.py의
고정 문구 블록리스트와 같은 구조적 한계) - 디스패치 프롬프트 자체에서 검토를
명시적으로 생략하라고 지시하는 컨트롤러만 잡는다. 마커/생략지시 없이
서브에이전트가 스스로 rubber-stamp하는 경우는 여전히 못 잡는다 - 이건
이 우회의 명시적이고 쉬운 버전만 닫는다.

Override: protect_reviewer_prejudging.py와 동일한 sentinel-file 메커니즘.

**정정(2026-08-18, CI 첫 커밋에서 바로 발견)**: 첫 버전의 "그냥 이 줄만
출력" 패턴이 실제 예시 문구("정확히 이 한 줄만 출력해")와 단어가 안
맞아서(둘 다 없음) 매칭 실패 - 자기 자신의 테스트를 못 통과했다. "이
(한 )?줄만 출력"으로 완화해서 "이 줄만 출력"/"이 한 줄만 출력" 둘 다
잡게 고침.

**추가 (2026-08-19, 2-Agent Consensus)**: override 체크 다음, 기존
high_tier_decision() fallback 전에 consensus 확인 단계가 하나 더 생겼다
- 자세한 설계는 `_hook_common.py`의 `write_consensus_verdict()`/
`consensus_verdict()` docstring 참고. 안 쓰면(컨트롤러가 2-agent 디스패치를
아예 안 하면) 기존 동작과 완전히 동일."""
import json
import re
import sys

from _hook_common import (allow, allow_with_consensus, allow_with_override,
                           consensus_verdict, high_tier_decision,
                           require_decision_or_deny, sentinel_override)

HOOK_NAME = "protect_rubber_stamp_approval"
SEVERITY = "HIGH"

_RUBBER_STAMP_PATTERNS = [
    re.compile(r"이\s*(한\s*)?줄만\s*출력", re.IGNORECASE),
    re.compile(r"실제로\s*확인\s*안\s*해도", re.IGNORECASE),
    re.compile(r"파일\s*열어보지\s*말", re.IGNORECASE),
    re.compile(r"검토\s*없이", re.IGNORECASE),
    re.compile(r"just\s+output", re.IGNORECASE),
    re.compile(r"don'?t\s+actually\s+(review|check)", re.IGNORECASE),
    re.compile(r"skip\s+the\s+review", re.IGNORECASE),
    re.compile(r"without\s+(actually\s+)?review(ing)?", re.IGNORECASE),
]

_MEDIUM_APPROVE_MENTION_RE = re.compile(r"MEDIUM-APPROVE", re.IGNORECASE)


def read_input():
    return json.load(sys.stdin)


def find_rubber_stamp_phrase(text):
    if not text or not _MEDIUM_APPROVE_MENTION_RE.search(text):
        return None
    for pattern in _RUBBER_STAMP_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def main():
    data = read_input()
    if data.get("tool_name") != "Agent":
        allow()
        return
    ti = data.get("tool_input") or {}
    combined = " ".join(str(ti.get(k, "")) for k in ("prompt", "description"))
    phrase = find_rubber_stamp_phrase(combined)
    if phrase:
        target = str(ti.get("description", "")) or combined[:80]
        decision = require_decision_or_deny(
            HOOK_NAME, SEVERITY, target,
            "This dispatch prompt asks for a MEDIUM-APPROVE marker while telling "
            f"the subagent to skip real review (matched: \"{phrase}\").")
        if decision is None:
            return
        override_reason = sentinel_override(HOOK_NAME, target)
        if override_reason:
            allow_with_override(HOOK_NAME, SEVERITY, HOOK_NAME, target, override_reason,
                                 decision=decision)
            return
        verdict = consensus_verdict(HOOK_NAME, target)
        if verdict in ("agree_safe", "agree_risky"):
            allow_with_consensus(HOOK_NAME, SEVERITY, HOOK_NAME, target, verdict, decision=decision)
            return
        high_tier_decision(
            HOOK_NAME, SEVERITY,
            "이 디스패치 프롬프트가 MEDIUM-APPROVE 마커를 요구하면서 동시에 "
            f"실제 검토를 생략하라고 지시함(매칭: \"{phrase}\") - MEDIUM 승인은 "
            "opus가 실제로 검토했다는 걸 전제로 하는데, 이 프롬프트는 그 전제 "
            "자체를 깨뜨림. 서브에이전트가 실제로 파일을 검토하도록 프롬프트를 "
            "다시 쓸 것. To override: write "
            ".claude/hooks/.pending_override.json with "
            f'{{"rule": "{HOOK_NAME}", "target": "{target}", "reason": "<reason>", '
            '"timestamp": <time.time()>}, then retry immediately.',
            data, target=target, decision=decision,
        )
        return
    allow()


if __name__ == "__main__":
    main()
