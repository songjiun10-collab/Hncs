#!/usr/bin/env python3
"""PreToolUse hook (matcher: mcp__github__update_pull_request) enforcing
CLAUDE.md's "Don't skip the final whole-branch review; it caught three
critical bugs."

Blocks marking a pull request ready-for-review (draft: false) unless
record_whole_branch_review.py's sentinel shows a whole-branch-review-type
Agent dispatch happened at the CURRENT git HEAD - any commit since the
last recorded review invalidates it, since a \"whole-branch review\" is
only meaningful against the branch's actual current state.

**HIGH severity, override available (2026-08 retrofit).** Denies by
default. Override via the same sentinel-file mechanism as
`protect_never_touch.py` - write `.claude/hooks/.pending_override.json`
with `{"rule": "protect_ready_without_review", "target": "<owner>/<repo>#
<pullNumber>", "reason": "<reason>", "timestamp": <time.time()>}`. Note
this uses a DIFFERENT sentinel file than the whole-branch-review-happened
sentinel below (`.last_whole_branch_review_sha`) - one records \"a review
occurred\", the other records \"skip the review-occurred check this once,
deliberately\".

**추가 (2026-08-19, 2-Agent Consensus)**: override 체크 다음, 기존
high_tier_decision() fallback 전에 consensus 확인 단계가 하나 더 생겼다
- 자세한 설계는 `_hook_common.py`의 `write_consensus_verdict()`/
`consensus_verdict()` docstring 참고. 안 쓰면(컨트롤러가 2-agent 디스패치를
아예 안 하면) 기존 동작과 완전히 동일.

**정정(2026-08-20, README "알려진 한계" 2차 라운드 #8 - 가장 약한
고리로 지목됐던 finding)**: `.last_whole_branch_review_sha`는 어떤
훅으로도 보호 안 되고 있었다 - decision record sentinel과 달리
`protect_decision_record_bypass.py`의 대상이 아니었고, 격리 scratch
git repo에서 `echo -n $(git rev-parse HEAD) > .last_whole_branch_review_sha`
한 줄로(Agent 디스패치도, opus도, decision record도 전혀 안 거치고)
"최종 리뷰 통과"를 완전히 위조할 수 있음이 실측 확인됐다. 경로를
`_hook_common.py`의 `_WHOLE_BRANCH_REVIEW_SHA_PATH`로 옮기고
`protect_decision_record_bypass.py`의 보호 테이블에 추가해서 Edit/Write/
Bash로의 직접 쓰기를 막았다."""
import json
import subprocess
import sys
from pathlib import Path

from _hook_common import (_WHOLE_BRANCH_REVIEW_SHA_PATH, allow,
                           allow_with_consensus, allow_with_override,
                           consensus_verdict, high_tier_decision,
                           require_decision_or_deny, sentinel_override)

HOOK_NAME = "protect_ready_without_review"
SEVERITY = "HIGH"

_SENTINEL = Path(_WHOLE_BRANCH_REVIEW_SHA_PATH)


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

    target = f"{ti.get('owner', '?')}/{ti.get('repo', '?')}#{ti.get('pullNumber', '?')}"
    decision = require_decision_or_deny(HOOK_NAME, SEVERITY, target, f"Blocking draft->ready ({detail}).")
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
        "CLAUDE.md: \"Don't skip the final whole-branch review; it caught "
        f"three critical bugs.\" Blocking draft->ready ({detail}). Dispatch "
        "a final whole-branch review Agent (superpowers:requesting-code-review "
        "style, mentioning \"whole-branch review\" in the prompt) against the "
        f'current HEAD before marking this PR ready. To override: write '
        f'.claude/hooks/.pending_override.json with {{"rule": "{HOOK_NAME}", '
        f'"target": "{target}", "reason": "<reason>", "timestamp": '
        "<time.time()>}, then retry immediately.",
        data, target=target, decision=decision,
    )


if __name__ == "__main__":
    main()
