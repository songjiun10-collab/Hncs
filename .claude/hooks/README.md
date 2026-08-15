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
| `protect_reviewer_prejudging.py` | 🟠 HIGH | Agent | 리뷰어에게 발견사항 미리 재단 지시 |
| `protect_ready_without_review.py` | 🟠 HIGH | mcp__github__update_pull_request | 전체-브랜치 리뷰 없이 PR draft 해제 |
| `protect_agent_model_naming.py` | 🟡 MID | Agent | model 미지정/haiku 디스패치 |
| `record_whole_branch_review.py` | PostToolUse, 등급 없음 | Agent | (차단 아님) 전체-브랜치 리뷰 sentinel 기록 |

**2026-08-15 레거시 3개 재설계 완료.** "리뷰 에이전트" 관련 3개
(`protect_reviewer_prejudging.py`/`protect_ready_without_review.py`/
`protect_agent_model_naming.py`)를 심각도/override 체계에 편입:

- `protect_reviewer_prejudging.py`/`protect_ready_without_review.py`
  → HIGH + sentinel override(target은 각각 dispatch의 `description`,
  `<owner>/<repo>#<pullNumber>`). CRITICAL이 아니라 HIGH인 이유: 둘 다
  recoverable(다시 리뷰 돌리면 됨)이지 데이터 유실/shipped 아티팩트
  손상이 아님.
- `protect_agent_model_naming.py` → MID + `ask()`(원래 deny였음). 모델
  누락/haiku는 안전성이 아니라 비용 효율 문제라 하드 블록보다 사람 확인
  한 번이 더 맞는 등급.

`protect_ready_without_review.py`의 override sentinel은
`record_whole_branch_review.py`가 쓰는 `.last_whole_branch_review_sha`와
다른 파일(`.pending_override.json`) - 하나는 "리뷰가 실제로 일어났다"를
기록하고 다른 하나는 "이번만 그 체크를 의도적으로 건너뛴다"를 기록하는
별개 개념.

**MID `ask()` 실전 검증 완료(2026-08-15)**: `protect_claim_evidence.py`가
근거 없는 수치 주장(CLAUDE.md에 "성능이 37% 향상됨" 같은 테스트 문구
추가)에 실제로 `ask()`를 발동시켰고, Claude Code가 진짜 사람 확인
프롬프트를 띄웠으며 사용자가 직접 승인함을 확인. subprocess 테스트가
검증하는 "hookSpecificOutput.permissionDecision == 'ask' 문자열 반환"
너머, harness가 그 값을 실제로 존중해서 인터랙티브 승인으로 이어짐까지
라이브로 확인됨(1차 시도는 테스트 문구에 우연히 근거마커 단어("검증")가
섞여 있어 정상적으로 `allow`됐던 오탐 아닌 오탐 - 2차로 깨끗한 문구를
써서 재확인).

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
- override는 self-servable함 - agent가 이유를 지어내면(예: 사용자가
  실제로 승인 안 했는데 "사용자 승인함"이라고 씀) 훅은 검증할 방법이
  없다. 대화 맥락을 못 보기 때문. 설계 철학(`_hook_common.py` docstring)
  상 의도된 트레이드오프 - "의식적 행동 + 로그"까지만 보장하지 승인의
  진위 검증은 안 함.
- **디스패치된 서브에이전트의 툴콜도 이 훅 체인을 타는지 - 조사 중,
  아직 결과 안 나옴.**
- **사람이 없을 때(`/loop` 자율 모드, 스케줄된 Routine) `ask()`가
  어떻게 되는지 - claude-code-guide 서브에이전트로 공식 문서 근거까지
  조사 완료(2026-08-15).** 결론: 단일 보편 규칙은 없음 - 프롬프트를
  받을 메커니즘(`--permission-prompt-tool`/Agent SDK `canUseTool`)이
  있는지, 그리고 세션의 `permission_mode`가 뭔지에 달림.
  - `--permission-prompt-tool` 지정 시: 그 MCP 도구가 대신 답함(기본
    30초 `MCP_TIMEOUT`).
  - Agent SDK `canUseTool` 콜백 등록 시: 콜백이 응답할 때까지 **무기한
    대기**(타임아웃 아님) - `defer`로 세션을 접고 나중에 재개 가능.
  - **`dontAsk` 권한 모드일 때: 프롬프트를 띄웠을 모든 호출이 자동
    거부됨** - 훅의 `ask()`도 여기 해당. 이게 문서화된, 확실한
    fail-closed 경로.
  - 평범한 `claude -p`(위 셋 다 없음)는 공식 문서에 명시적 결과가
    없음 - 대신 문서 자체가 "이 상황에선 훅이 ask 대신 allow/deny를
    직접 결정하라"고 권고함. 가장 가까운 관련 문서(같은 문서 세트,
    백그라운드 서브에이전트 항목): "훅이 결정을 안 내리면 거부한다" -
    즉 Anthropic이 프롬프트 메커니즘이 없는 모든 경우에 대해 일관되게
    문서화하는 방향은 fail-closed(거부)지 무기한 대기나 자동 허용이
    아님.
  - **실무 권장**: 이 프로젝트를 무인/자율 모드(`/loop`, 스케줄된
    Routine)로 돌릴 때는 `--permission-mode dontAsk`로 실행 - MID
    등급 `ask()` 훅이 확실하게 fail-closed되도록. 훅 스크립트 자체는
    입력 JSON에서 `permission_mode` 필드를 읽을 수 있지만(확인된
    필드), "사람이 실제로 있는지"를 직접 알려주는 필드는 없음 - 그래서
    이건 훅 코드 변경이 아니라 세션 실행 방식(퍼미션 모드 선택)의
    문제로 남겨둠.

## 로그 유지관리

`violations_log.jsonl`/`override_audit.jsonl`은 append-only + git-tracked라
계속 커진다. `tools/rotate_hook_logs.py`가 retention 기간(기본 90일)보다
오래된 항목을 월별 아카이브 파일로 옮긴다 - 훅 체인에는 안 걸려있음(매
툴콜마다 로그 크기 재는 오버헤드 방지), 가끔 수동으로 돌리거나
Routine으로 스케줄:

```bash
python3 -m tools.rotate_hook_logs
```
