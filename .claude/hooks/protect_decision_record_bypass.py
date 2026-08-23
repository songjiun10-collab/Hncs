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
pentest finds the gap. `.last_whole_branch_review_sha` itself was a
separate, still-open finding at the time (different file, different
writer hook) and was intentionally NOT added to this table by that
change.

**정정(2026-08-20)**: it's added now - see the 2026-08-20 correction
below. Its path moved into `_hook_common.py` first (matching every other
entry in this table), which is what made adding it here possible.

**정정(2026-08-20, 발견 - `_PROTECTED_SENTINELS`에 빠져 있던 항목)**:
`.pending_medium_approval.json`(MEDIUM 등급 "상위 에이전트 승인" 결과)도
같은 패턴 - `write_medium_approval()`의 자기 docstring이 "not meant to
be written ad-hoc by an agent"라고 명시하는데, 정작 그걸 강제하는 훅이
없었다(`.pending_override.json`과 혼동하기 쉬운 지점: 그건 설계상
컨트롤러가 직접 써도 되는 self-servable 파일이지만, 이건 아님). 추가함.

No override, no decision record required for this hook itself -
requiring a decision record to protect the decision-record mechanism
would be circular, and any override would defeat the point of the
schema/dedicated-writer-enforced-only-channel design.

**정정(2026-08-20, 침투테스트 라운드 1 finding - README "알려진 한계"
"protect_decision_record_bypass.py가 Bash를 안 봄")**: 이 훅은 원래
`settings.json`에서 `matcher: "Edit|Write|MultiEdit"`에만 등록돼 있어서,
Bash로 직접 `python3 -c "...open('.pending_decision_record.json','w')..."`
같은 명령을 실행하면 이 CRITICAL 가드를 완전히 건너뛰었다(실측 확인됨,
격리 환경에서 위조 decision record + 위조 opus 승인으로
`protect_generated_files.py`의 allow까지 실제로 끌어냄). Bash 커버리지를
추가했다 - `protect_never_touch.py`의 Bash 경로와 같은 텍스트-매칭
방식(redirect/sed -i/tee/cp·mv/python open())이지만, **heredoc 본문은
안 지운다** - `protect_never_touch.py`/`protect_destructive.py`가 heredoc
스트리핑 때문에 `python3 - <<'PY' ... PY`로 넘긴 진짜 쓰기 코드를 놓치는
결함(같은 문서, 2차 라운드 #1/#2)을 이미 확인했기 때문에, 여기서는 같은
실수를 반복하지 않는다 - 이 훅은 override가 아예 없는 CRITICAL이라
false positive 비용보다 false negative 비용이 훨씬 크다. settings.json도
`Bash` matcher에 추가해야 실제로 걸린다."""
import json
import os
import re
import sys

from _hook_common import (_CONSENSUS_PATH, _DECISION_RECORD_PATH,
                           _MEDIUM_APPROVAL_PATH,
                           _WHOLE_BRANCH_REVIEW_SHA_PATH, allow, deny)

HOOK_NAME = "protect_decision_record_bypass"
SEVERITY = "CRITICAL"

_PROTECTED_SENTINELS = {
    os.path.abspath(_DECISION_RECORD_PATH): (
        "must_hook_server.py의 write_decision_record MCP 툴"),
    os.path.abspath(_CONSENSUS_PATH): (
        "record_consensus_judgment.py (PostToolUse, 실제 2-agent Dispatch 응답 파싱)"),
    os.path.abspath(_WHOLE_BRANCH_REVIEW_SHA_PATH): (
        "record_whole_branch_review.py (PostToolUse, 실제 whole-branch-review "
        "Agent 디스패치 감지 후 현재 HEAD sha 기록)"),
    os.path.abspath(_MEDIUM_APPROVAL_PATH): (
        "record_agent_approval.py (PostToolUse, 실제 opus Agent 디스패치의 "
        "MEDIUM-APPROVE 마커 파싱)"),
}

# Bash coverage - basename-based (not full-path regex like
# protect_never_touch.py's _PROTECTED_PATH) since there are only two fixed
# sentinel filenames to watch for, wherever they're referenced from
# (absolute, relative to repo root, or relative to .claude/hooks/).
_SENTINEL_BASENAMES = sorted({os.path.basename(p) for p in _PROTECTED_SENTINELS})
_PATH_ALTERNATION = "|".join(re.escape(b) for b in _SENTINEL_BASENAMES)
_PROTECTED_BASH_PATH = r"(?:[\w./-]*/)?(?:" + _PATH_ALTERNATION + r")"
_REDIRECT_TARGET_RE = re.compile(r">{1,2}\s*[\"']?(" + _PROTECTED_BASH_PATH + r")")
_SED_INPLACE_TARGET_RE = re.compile(r"\bsed\s+-i\b[^|;&\n`]*?(" + _PROTECTED_BASH_PATH + r")")
_TEE_TARGET_RE = re.compile(r"\btee\b[^|;&\n`]*?(" + _PROTECTED_BASH_PATH + r")")
_CP_MV_DEST_RE = re.compile(
    r"\b(?:cp|mv)\b[^|;&\n`]*\s(" + _PROTECTED_BASH_PATH + r")\s*(?:[;&|\n`]|$)")
_PY_WRITE_OPEN_RE = re.compile(
    r"open\(\s*f?[\"']([^\"']*(?:" + _PATH_ALTERNATION + r"))[\"']\s*,\s*"
    r"[\"'](?:w|a|wb|ab|x)[\"']")


def read_input():
    return json.load(sys.stdin)


def protected_sentinel_writer(file_path):
    """Returns a description of the one legitimate writer for file_path,
    or None if file_path isn't a protected sentinel at all."""
    if not file_path:
        return None
    return _PROTECTED_SENTINELS.get(os.path.abspath(file_path))


def bash_write_target(command):
    """Returns the matched sentinel-path string if `command` looks like it
    writes to a protected sentinel via Bash, else None. Deliberately does
    NOT strip heredoc bodies first - see module docstring's 2026-08-20
    correction for why."""
    for rx in (_REDIRECT_TARGET_RE, _SED_INPLACE_TARGET_RE, _TEE_TARGET_RE,
               _CP_MV_DEST_RE, _PY_WRITE_OPEN_RE):
        m = rx.search(command)
        if m:
            return m.group(1)
    return None


def main():
    data = read_input()
    tool = data.get("tool_name")

    if tool == "Bash":
        command = str((data.get("tool_input") or {}).get("command", ""))
        target = bash_write_target(command)
        if target is None:
            allow()
            return
        deny(
            HOOK_NAME,
            f"이 Bash 명령이 {target}에 쓰는 것으로 보임 - decision record/"
            "consensus sentinel은 전용 writer(MCP 툴 또는 실제 Agent 디스패치를 "
            "파싱하는 PostToolUse 훅)로만 써야 함, Bash로 직접 쓰는 건 검증을 "
            "우회하는 경로라 항상 막힘, override 없음.",
            severity=SEVERITY, target=target,
        )
        return

    if tool not in ("Edit", "Write", "MultiEdit"):
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
