# Hncs 훅 가드 목록 (2026-08)

CLAUDE.md 규칙 중 기계적으로 강제 가능한 것들을 PreToolUse/PostToolUse
훅으로 구현한 것 - 설계 원칙은 `_hook_common.py` 모듈 docstring 참고:

> 훅은 개발자를 대신해 판단하지 않는다. 훅은 "위험한 행동을 무의식적으로
> 해버리는 것"만 막는다. 의식적으로 override하면 허용하되, 왜 뚫었는지는
> 항상 남는다.

## 심각도 4단계

| 등급 | 기본 동작 | Override |
|---|---|---|
| 🟢 LOW | allow + 로그 | (해당 없음 - 통과 자체가 로그) |
| 🟡 MID | `ask()` - Claude Code의 실제 사람 승인 프롬프트로 넘김 | (프롬프트 자체가 승인 절차) |
| 🟠 HIGH | deny | `# HNCS-OVERRIDE: <rule>: <이유>` (Bash) / sentinel 파일 (Edit·Write) |
| 🔴 CRITICAL | deny | 위와 동일 메커니즘 - 등급 차이는 "얼마나 신중해야 하는가"이지 우회 난이도가 아님 |

## Override 방법

- **Bash 트리거 훅**: 명령 끝에 `# HNCS-OVERRIDE: <rule>: <이유>` 주석 추가.
- **Edit/Write/MultiEdit 트리거 훅**: `.claude/hooks/.pending_override.json`에
  `{"rule": "<rule>", "target": "<file_path>", "reason": "<이유>",
  "timestamp": <time.time()>}`를 먼저 쓰고 바로 재시도(10분 내, 1회성 소비).

모든 override는 `override_audit.jsonl`에 `{timestamp, rule, severity,
target, reason, git_sha}`로 기록됨(git_sha는 훅이 직접 계산 - 위조 불가).
실제 deny/override 이벤트는 `violations_log.jsonl`에도 남음(둘 다
git-tracked, append-only).

## 가드 목록

| 훅 | 등급 | 트리거 | 무엇을 막는가 |
|---|---|---|---|
| `protect_never_touch.py` | 🔴 CRITICAL | Edit/Write/MultiEdit, Bash | shipped `apply_*` / 프로필 json·dcp 수정 |
| `protect_push_safety.py` | 🔴 CRITICAL (force-push) / HIGH (authorship, override 없음) | Bash | force push, 잘못된 커밋 작성자로 push |
| `protect_destructive.py` | 🔴 CRITICAL | Bash | `rm -rf`류(스크래치 경로 제외), `git reset --hard`, `git clean -f`, `git branch -D` |
| `protect_branch.py` | 🟠 HIGH | Bash | main/master/detached HEAD에서 commit·push |
| `protect_test_coverage.py` | 🟠 HIGH | Bash | 새 소스 파일을 테스트 없이 커밋(신규 파일에만 적용 - 기존 파일 수정은 대상 아님) |
| `protect_experiment_integrity.py` | 🟠 HIGH | Edit/Write/MultiEdit (EVALUATION.md만) | CI/부트스트랩 언급 없이 수치 결과 기록 |
| `protect_generated_files.py` | 🟡 MID | Edit/Write/MultiEdit | `_LEARNED_LUT*` 배열(생성물) 직접 수정 |
| `protect_claim_evidence.py` | 🟡 MID | Edit/Write/MultiEdit | README/CLAUDE.md/EVALUATION.md에 근거 없는 수치 주장 |
| `protect_reviewer_prejudging.py` | (미분류 - 레거시) | Agent | 리뷰어에게 발견사항 미리 재단 지시 |
| `protect_ready_without_review.py` | (미분류 - 레거시) | mcp__github__update_pull_request | 전체-브랜치 리뷰 없이 PR draft 해제 |
| `protect_agent_model_naming.py` | (미분류 - 레거시) | Agent | model 미지정/haiku 디스패치 |
| `record_whole_branch_review.py` | PostToolUse, 등급 없음 | Agent | (차단 아님) 전체-브랜치 리뷰 sentinel 기록 |

레거시 3개(`protect_reviewer_prejudging.py`/`protect_ready_without_review.py`/
`protect_agent_model_naming.py`)는 이 심각도 체계 이전에 만들어져서
`deny(hook_name, reason)`만 쓴다 - `severity` 인자 기본값(HIGH)으로
로그는 남지만 override 메커니즘은 아직 없음. 다음에 손댈 일 있으면
같이 정리.

## 알려진 한계

- 전부 텍스트/AST 패턴 매칭이지 실제 셸 파서나 의미 분석이 아님 -
  `protect_never_touch.py`/`protect_push_safety.py`/`protect_branch.py`/
  `protect_destructive.py`/`protect_test_coverage.py`가 공유하는
  `_STMT_START` + heredoc 스트리핑 패턴으로 known false-positive 클래스는
  막았지만, "충분히 다른" 셸 문법에는 여전히 뚫릴 수 있음.
- `protect_experiment_integrity.py`/`protect_claim_evidence.py`는 특히
  근사적 - "CI 언급이 있다"까지만 확인하지 그 CI가 실제로 올바르게
  계산됐는지는 검증 불가.
- `protect_test_coverage.py`는 의도적으로 좁게 스코프됨(새 파일만) -
  모든 커밋에 새 테스트를 요구하면 이 세션 자체의 정당한 리팩토링
  커밋들(예: `f460233`, 기존 테스트로 이미 커버됨)이 계속 걸렸을 것.
