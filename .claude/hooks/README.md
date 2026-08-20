# Hncs 훅 가드 목록 (2026-08)

CLAUDE.md 규칙 중 기계적으로 강제 가능한 것들을 PreToolUse/PostToolUse
훅으로 구현한 것 - 설계 원칙은 `_hook_common.py` 모듈 docstring 참고:

> 훅은 개발자를 대신해 판단하지 않는다. 훅은 "위험한 행동을 무의식적으로
> 해버리는 것"만 막는다. 의식적으로 override하면 허용하되, 왜 뚫었는지는
> 항상 남는다.

## 심각도 4단계

**2026-08-15, 사용자 확정 스펙으로 재설계 - 4단계가 이제 실제로 다르게
동작한다** (이전 버전은 MID/HIGH/CRITICAL이 전부 deny+override로
기계적으로 동일했음 - 그 히스토리는 아래 남겨둠):

| 등급 | 기본 동작 | Override |
|---|---|---|
| 🟢 LOW | allow + 로그 | (해당 없음 - 통과 자체가 로그) |
| 🟡 MEDIUM | 상위 에이전트 승인이면 통과 + caution 전달, 아니면 deny | plain override 없음(2026-08-16 제거) - 실제 opus Agent 디스패치의 `MEDIUM-APPROVE` 마커만 유효 |
| 🟠 HIGH | 직접 호출은 `ask()`(실제 사람 프롬프트), 서브에이전트발은 override 없인 무조건 deny | 위와 동일한 override, 둘 다 여전히 유효 |
| 🔴 CRITICAL | deny (Never-touch/파괴적 명령/force-push) | 오케스트레이터 직접 호출만 override 가능 - 서브에이전트발은 override 자체가 없음 |

**MEDIUM/HIGH/CRITICAL 공통 전제조건(2026-08-16 추가)**: 위 표의 Override
칸에 적힌 경로들은 전부 `require_decision_or_deny()` 필수 게이트를
통과한 *다음에만* 평가된다 - decision record가 없으면 override가
유효하든 MEDIUM-APPROVE가 진짜 opus 승인이든 상관없이 그 자리에서
바로 deny. "Decision Record" 섹션 참고.

- **LOW**: `log_and_allow()` - 항상 allow, 로그만. 안 바뀜.
- **MEDIUM**: "상위 에이전트가 허용하면 실행 에이전트가 실행, 단
  주의사항 전달." 실제 디스패치된 서브에이전트의 응답에
  `MEDIUM-APPROVE: <rule> :: <target> :: <caution>` 마커가 있고 그
  디스패치 모델이 **opus**면(2026-08-16 정정: "에이전트는 오퍼스 허락만
  유효" - sonnet도 불인정) (`record_agent_approval.py`, PostToolUse/Agent)
  승인을 기록한다 - 자기 자신이 못 쓰고 진짜 opus Agent 디스패치가
  있어야 생기는 sentinel. 통과할 때 caution은
  `deliver_caution.py`(PostToolUse, Edit|Write|MultiEdit)가
  `additionalContext`로 실행 에이전트에게 돌려준다(같은 `tool_use_id`로
  상관관계). `protect_generated_files.py`/`protect_claim_evidence.py`가
  이 등급. **정정(같은 날, "그 애매한 중간단계?")**: plain
  self-declared override(bash 주석/sentinel)를 이 두 훅에서 완전히
  제거했다 - MEDIUM-APPROVE와 나란히 있으면 항상 더 쉬운 override
  쪽만 쓰여서 "상위 에이전트 승인" 경로가 사실상 죽은 코드였음. 이제
  MEDIUM은 override로 안 뚫림 - opus MEDIUM-APPROVE가 유일한 통과 경로.
- **HIGH**: "사람 승인." `agent_id` 필드 유무로 분기(아래 "서브에이전트
  훅 적용 여부" 항목에서 확인된 필드) - 오케스트레이터 직접 호출은
  `ask()`(실측 확인된 진짜 사람 프롬프트), 서브에이전트발 호출은
  override 없이는 무조건 deny(ask()가 서브에이전트에서 fail-open이라는
  걸 이미 확인했으므로 - "ask()가 사람 없을 때" 항목 참고).
  `protect_branch.py`/`protect_test_coverage.py`/
  `protect_experiment_integrity.py`/`protect_reviewer_prejudging.py`/
  `protect_ready_without_review.py` 5개가 이 등급.
- **CRITICAL**: 서브에이전트발 호출은 override조차 받지 않고 무조건
  deny - override가 self-servable(자기 자신이 사유를 지어내면 훅은
  검증 불가)이라는 한계가 가장 치명적인 등급이라, 서브에이전트가 스스로
  bash 주석/sentinel 파일을 써서 통과하는 경로 자체를 없앴다.
  오케스트레이터 직접 호출은 기존 override 메커니즘 그대로(이 세션의
  learned-LUT 리팩토링이 바로 이 경로로 진행됐다). `protect_never_touch.py`
  /`protect_destructive.py`/`protect_push_safety.py`(force-push 분기)가
  이 등급.

### 이전 버전(2026-08-15 이전) - 참고용으로 남김

2026-08-15 전에는 MID가 `ask()`(Claude Code의 실제 사람 확인 프롬프트)를
썼는데, 서브에이전트로 실측한 결과 `ask()`가 디스패치된 subagent의
툴콜에서는 프롬프트 없이 조용히 `allow`로 새는 게 확인돼서(아래
"서브에이전트 훅 적용 여부" 항목) MID 3개 전부 일단 deny+override로
되돌렸다.

그 다음 재검토(같은 날): MID 3개 중 `protect_agent_model_naming.py`는
이 세션 안에서만 deny→ask→deny로 등급이 3번 바뀌었다 - 그 churn 자체가
"이건 원래 막을 정도가 아니었다"는 신호였다. 모델 누락/haiku는 비용
효율 문제지 정확성/안전성 문제가 아니라서, override 한 줄이라도 요구하는
게 이 finding엔 안 맞는 마찰이었다. **LOW로 재분류하고 `log_and_allow()`
(항상 allow, 로그만 남김, override 개념 자체가 없음)로 바꿨다.** 이건
지금도 유효 - LOW는 그대로다.

그 다음(같은 날, 이 섹션 맨 위) 사용자가 4단계를 실제로 다르게 동작하는
스펙으로 재확정해서, 남은 MID/HIGH/CRITICAL도 각자 다른 메커니즘으로
갈라졌다 - 위 표가 현재 상태.

## Decision Record (예측 로그, 2026-08-16)

가드된 액션 직전에 에이전트 스스로 자기 위험도 판단을 기록해두면, 그
액션이 실제로 어떤 훅 결정으로 이어졌는지에 자동으로 붙는다.

**정정(같은 날, 사용자 지시 - "그거도 훅 걸어라 강제적훅 예외 없이")**:
처음 설계할 땐 "로깅 전용, allow/deny를 절대 gating하지 않는다"였다 -
아래 "한계 3가지"의 1번(자기강제 없음)이 실제로 문제가 됐다: 이 세션의
두 organic 테스트(테스트라고 안 밝히고 서브에이전트한테 실제 작업을
시킴 - README에 decision record가 문서화돼 있고 실제로 읽었는데도
2번 다 자발적으로 안 씀)로 "문서화만 해두면 쓰이겠지"가 성립 안
한다는 게 확인된 뒤, **MEDIUM/HIGH/CRITICAL 전부에서 decision record가
필수 게이트로 바뀌었다** - `require_decision_or_deny()`가 override/
MEDIUM-APPROVE/ask 판단보다 먼저 실행돼서, decision record가 없으면
그 어떤 통과 경로도 고려하지 않고 무조건 deny한다(예외 없음 - subagent/
direct 호출 구분도 없음). LOW(`protect_agent_model_naming.py`)는
대상이 아님 - LOW의 "마찰 없음" 설계 자체가 이미 별개로 확정된 결정이라
여기서 안 뒤집었다.

**쓰는 법 - 정정(같은 날, must훅 - "처음부터 다 만들자 pre tool use
말고" / "MCP 툴 스키마 강제")**: 원래는 아래처럼 Write 툴로
`.claude/hooks/.pending_decision_record.json`에 자유 텍스트 JSON을
직접 쓰는 방식이었다 - 필드 누락/타입 오류/범위 밖 confidence를 막을
수단이 나중에 읽는 쪽 검증뿐이었다. 이제는 `must_hook_server.py`가
노출하는 **`mcp__must_hook__write_decision_record` MCP 툴을 호출**한다
- 파라미터 스키마(타입 힌트 + pydantic `Field` 제약: `severity`는
LOW/MEDIUM/HIGH/CRITICAL 패턴, `confidence`는 0.0-1.0, `reason`/
`expected_risk`는 non-empty)가 MCP 프로토콜 단에서 검증돼서, 스키마를
어긴 호출은 서버 코드에 도달하지도 못한다. Write 툴로 이 sentinel
파일을 직접 쓰는 옛 경로는 `protect_decision_record_bypass.py`(신규,
override 없음)가 무조건 막는다 - MCP 툴이 유일한 통로.

```
mcp__must_hook__write_decision_record(
  rule="<발동할 훅의 HOOK_NAME>", target="<그 훅이 이미 쓰는 override target과 같은 값>",
  severity="<자기평가 등급>", confidence=0.0-1.0,
  reason="<왜 이렇게 판단했나>", expected_risk="<뭐가 잘못될 수 있나>")
```

(툴 내부는 `_hook_common.write_decision_record(rule, severity,
confidence, reason, expected_risk, target=..., decision_id=...)`를 그대로
호출 - 파일 쓰기/포맷은 여전히 그 함수가 단일 구현. `target` 또는
`decision_id` 중 하나는 필수 - 스키마가 둘 다 optional이라 이건
함수 쪽에서 `ValueError`로 잡는다.)

매칭되는 fresh(10분 이내) 레코드가 있으면 `deny()`/`ask()`/
`log_and_allow()`/`allow_with_override()`/`allow_with_medium_approval()`을
거쳐 `violations_log.jsonl`/`override_audit.jsonl` 항목에 `decision`
키(`self_severity`/`confidence`/`reason`/`expected_risk`)로 붙는다.
`self_severity`는 에이전트 자신의 판단이고, 항목의 최상위 `severity`는
그 훅의 고정 등급 - 이 둘이 다를 수 있고(그게 정상), 그 차이를
`tools/eval_hook_judgments.py`가 측정한다.

**한계 (숨기지 않고 명시)**:
1. ~~자기강제가 없다.~~ **정정(2026-08-16, 같은 날 나중에): 이제 자기강제
   있음** - 위 필수 게이트 추가로 override sentinel과 동일하게 "안 쓰면
   계속 막힌다"는 압박이 생겼다. 원래 이 항목이 지적했던 문제(organic
   테스트 2번 다 자발적으로 안 씀)가 바로 이 정책 변경의 이유였다 - 이제는
   "안 써도 그만"이 아니라 "안 쓰면 아무 작업도 못 한다." **추가
   정정(같은 날, must훅)**: 강제된 게 "decision record 자체가 존재하는지"
   뿐이었고, "존재하는 그 내용이 스키마상 유효한지"는 여전히 안 봤다 -
   에이전트가 Write 툴로 필드 누락/타입 오류 JSON을 써도 나중에 읽을 때야
   걸렸다. `must_hook_server.py`의 MCP 툴 스키마가 이 틈도 닫는다 -
   잘못된 호출은 파일이 써지기도 전에 거부됨.
2. **`decision_id`는 "어느 규칙이 발동할지 이미 알 때"만 도움된다.**
   "9개 가드 중 뭐가 걸릴지 모르겠다"는 상황은 못 푼다 - `target`이
   그 훅이 쓰는 override target과 정확히 일치해야 매칭되므로, 현실적
   범위는 CLAUDE.md에 이미 문서화된 뻔한 케이스(`brands/*.py` 수정 →
   `protect_never_touch`, main에 커밋 → `protect_branch` 등)에 그친다.
3. **`ask()`의 실제 사람 답변은 구조적으로 관측 불가능하다.** `ask()`
   docstring 참고 - Claude Code 런타임이 훅 프로세스 밖에서 프롬프트를
   처리해서, `decision_kind="ask"`인 이벤트는 `tools/eval_hook_judgments.py`
   에서 항상 `ask_unknown`으로만 보고된다.

**신규 도구**: `tools/eval_hook_judgments.py` - `decision`이 붙은 항목만
골라 `decision_kind`별로 결과를 자동 분류하고(`deny`→blocked,
`ask`→ask_unknown, 나머지는 git log로 revert 여부 판정), severity
과대/과소평가와 confidence×revert 상관을 계산한다. `hybrid_engine/CLAUDE.md`
의 "평균 차이만으로 승자를 부르지 않는다" 규율 그대로 - 표본이
`--min-n`(기본 20) 미만이면 rate/verdict는 항상 `None`/"표본 부족",
raw count만 보여준다. **훅 체인에는 안 걸림 - 어떤 훅의 등급/임계값도
자동으로 안 바꾼다.** 수동/Routine 실행, `rotate_hook_logs.py`와 같은
스탠드얼론 관례:

```bash
python3 -m tools.eval_hook_judgments              # 리포트 + learning_data.jsonl에 기록
python3 -m tools.eval_hook_judgments --no-record  # 리포트만
```

## Override 방법

- **Bash 트리거 훅**: 명령 끝에 `# HNCS-OVERRIDE: <rule>: <이유>` 주석 추가.
- **Edit/Write/MultiEdit 트리거 훅**: `.claude/hooks/.pending_override.json`에
  `{"rule": "<rule>", "target": "<file_path>", "reason": "<이유>",
  "timestamp": <time.time()>}`를 먼저 쓰고 바로 재시도(10분 내, 1회성 소비).
- **예외 - `protect_generated_files.py`/`protect_claim_evidence.py`
  (MEDIUM)**: 위 방법 둘 다 안 먹힘(2026-08-16 제거). opus Agent
  디스패치의 `MEDIUM-APPROVE` 마커만 유효 - "심각도 4단계" 섹션의
  MEDIUM 항목 참고.

모든 override는 `override_audit.jsonl`에 `{timestamp, rule, severity,
target, reason, git_sha}`로 기록됨(git_sha는 훅이 직접 계산 - 위조 불가).
실제 deny/override 이벤트는 `violations_log.jsonl`에도 남음(둘 다
git-tracked, append-only).

## 가드 목록

MEDIUM/HIGH/CRITICAL 행 전부 decision record 필수 게이트가 먼저 적용됨
(2026-08-16) - 아래 override/승인/ask 설명은 그 게이트를 통과한 다음
이야기. LOW(`protect_agent_model_naming.py`)만 게이트 대상 아님.

| 훅 | 등급 | 트리거 | 무엇을 막는가 |
|---|---|---|---|
| `protect_never_touch.py` | 🔴 CRITICAL | Edit/Write/MultiEdit, Bash | shipped `apply_*` / 프로필 json·dcp 수정 (서브에이전트발은 override 불가) |
| `protect_push_safety.py` | 🔴 CRITICAL (force-push, 서브에이전트발은 override 불가) / HIGH (authorship, override 없음) | Bash | force push, 잘못된 커밋 작성자로 push |
| `protect_destructive.py` | 🔴 CRITICAL | Bash | `rm -rf`류(스크래치 경로 제외), `git reset --hard`, `git clean -f`, `git branch -D` (서브에이전트발은 override 불가) |
| `protect_branch.py` | 🟠 HIGH | Bash | main/master/detached HEAD에서 commit·push (직접 호출: ask, 서브에이전트발: override 없인 deny) |
| `protect_test_coverage.py` | 🟠 HIGH | Bash | 새 소스 파일을 테스트 없이 커밋(신규 파일에만 적용 - 기존 파일 수정은 대상 아님) |
| `protect_experiment_integrity.py` | 🟠 HIGH | Edit/Write/MultiEdit (EVALUATION.md만) | CI/부트스트랩 언급 없이 수치 결과 기록 |
| `protect_generated_files.py` | 🟡 MEDIUM | Edit/Write/MultiEdit | `_LEARNED_LUT*` 배열(생성물) 직접 수정 - plain override 없음, opus 상위 에이전트 승인(`MEDIUM-APPROVE`)만 유효 |
| `protect_claim_evidence.py` | 🟡 MEDIUM | Edit/Write/MultiEdit | README/CLAUDE.md/EVALUATION.md에 근거 없는 수치 주장 - plain override 없음, opus 상위 에이전트 승인(`MEDIUM-APPROVE`)만 유효 |
| `protect_reviewer_prejudging.py` | 🟠 HIGH | Agent | 리뷰어에게 발견사항 미리 재단 지시 |
| `protect_ready_without_review.py` | 🟠 HIGH | mcp__github__update_pull_request | 전체-브랜치 리뷰 없이 PR draft 해제 |
| `protect_agent_model_naming.py` | 🟢 LOW | Agent | model 미지정/haiku 디스패치 - 항상 allow, 로그만 남김 |
| `protect_decision_record_bypass.py` | 🔴 CRITICAL, override 없음 | Edit/Write/MultiEdit | `.pending_decision_record.json` 직접 쓰기 차단 - `mcp__must_hook__write_decision_record`만 유효 통로(must훅) |
| `record_agent_approval.py` | PostToolUse, 등급 없음 | Agent | (차단 아님) MEDIUM 승인 마커 파싱 + sentinel 기록 |
| `deliver_caution.py` | PostToolUse, 등급 없음 | Edit/Write/MultiEdit | (차단 아님) MEDIUM 승인의 caution을 `additionalContext`로 전달 |
| `record_whole_branch_review.py` | PostToolUse, 등급 없음 | Agent | (차단 아님) 전체-브랜치 리뷰 sentinel 기록 |

`protect_ready_without_review.py`의 override sentinel은
`record_whole_branch_review.py`가 쓰는 `.last_whole_branch_review_sha`와
다른 파일(`.pending_override.json`) - 하나는 "리뷰가 실제로 일어났다"를
기록하고 다른 하나는 "이번만 그 체크를 의도적으로 건너뛴다"를 기록하는
별개 개념.

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
  진위 검증은 안 함. **MEDIUM의 `MEDIUM-APPROVE` 마커도 이 한계에서
  완전히 자유롭진 않다** - 진짜 Agent 디스패치가 있어야 하고 모델이
  opus여야 한다는 조건(2026-08-16 정정: sonnet도 불인정)이 있어서 일반
  override보다 위조 난이도는 높지만, 컨트롤러가 그 디스패치 프롬프트
  자체를 "무조건 승인해"로 짜면
  똑같이 우회 가능 - "한 단계 더 어렵게" 만든 것이지 막은 게 아니다.
- `record_agent_approval.py`/`deliver_caution.py`(2026-08-15 신규)는
  PostToolUse의 `tool_response.content[0].text`/`resolvedModel`(Agent
  매처)과 `additionalContext`(Edit/Write/MultiEdit 매처)에 의존한다 -
  둘 다 실제 서브에이전트 디스패치로 실측 확인됨(아래 두 항목). 반면
  PreToolUse의 "allow" 시 `permissionDecisionReason`이 모델에게
  전달되는지는 claude-code-guide로 공식 문서를 조사한 결과 **전달 안
  됨으로 확정**됐고(여러 번 fetch 결과 일관됨), PreToolUse의
  `additionalContext` 지원 여부는 같은 조사에서 **문서마다 결과가
  갈려서 불확실**했다(GitHub 기능 요청 이슈 #15345/#15664가 아직
  없다고 언급 - closed지만 PR 링크 없음) - 그래서 caution 전달을
  PreToolUse가 아니라 PostToolUse 경로로 설계했다.

### 서브에이전트 툴콜의 훅 적용 여부 - 확인 완료(2026-08-15)

실제로 Agent 툴로 서브에이전트를 디스패치해서 실측:

1. **Bash 트리거 훅은 서브에이전트에도 적용됨(확인).** 서브에이전트가
   `rm -rf` 명령을 실행하려 하자 `protect_destructive.py`가 정확히 같은
   메시지로 차단함 - 오케스트레이터 직접 호출 때와 동일.
2. **`ask()` 기반 훅은 서브에이전트에서 실질적으로 무력화됨(확인,
   심각한 문제였음).** 같은 서브에이전트가 `protect_claim_evidence.py`가
   막아야 할 근거 없는 수치 주장을 CLAUDE.md에 추가했는데, 아무 denial도
   ask 프롬프트도 없이 그냥 성공함. 서브에이전트 실행 컨텍스트엔 프롬프트를
   띄울 화면이 없어서 fail-open(자동 허용)된 것으로 추정 - 정확히 이
   프로젝트의 정상 워크플로우(Controller가 Implementer/Reviewer
   서브에이전트를 디스패치해서 실제 작업시키는 구조)에서 보호가 0이
   되는 경우였음.

**대응**: `protect_claim_evidence.py`/`protect_generated_files.py`/
`protect_agent_model_naming.py` 3개 전부 `ask()`를 버리고
deny+override로 전환(위 "심각도 4단계" 섹션 참고) - deny+override는
결정론적 파일/텍스트 체크라 오케스트레이터든 서브에이전트든 동일하게
동작한다. 위 "서브에이전트 훅 적용 여부" 실측 결과, Bash 트리거 훅(CRITICAL/
HIGH deny 계열)은 애초에 원래 설계대로 서브에이전트에도 안전하게
작동했었다 - 이번에 문제였던 건 딱 `ask()`를 쓰던 3개뿐이었다.

### `ask()`가 사람 없을 때 어떻게 되는지 - 참고용 조사 결과(2026-08-15)

**정정(같은 날, 이후)**: 아래는 원래 "이 프로젝트는 ask()를 완전히
버렸다"는 맥락에서 조사한 참고 자료였는데, 그날 안에 4단계가 재설계되면서
HIGH 등급이 `ask()`를 다시 쓰게 됐다(단, `agent_id` 없는 직접 호출에만 -
"심각도 4단계" 섹션 참고, 서브에이전트발은 여전히 이 조사가 확인한
fail-open 문제 때문에 `ask()`를 안 씀). 아래 조사 내용 자체는 여전히
유효한 배경 지식이라 그대로 남김:

claude-code-guide 서브에이전트로 공식 문서 근거까지 조사한 내용:

- 단일 보편 규칙은 없음 - 프롬프트를 받을 메커니즘
  (`--permission-prompt-tool`/Agent SDK `canUseTool`)이 있는지, 세션의
  `permission_mode`가 뭔지에 달림.
- `--permission-prompt-tool` 지정 시: 그 MCP 도구가 대신 답함(기본 30초
  `MCP_TIMEOUT`).
- Agent SDK `canUseTool` 콜백 등록 시: 콜백이 응답할 때까지 **무기한
  대기**(타임아웃 아님) - `defer`로 세션을 접고 나중에 재개 가능.
- **`dontAsk` 권한 모드일 때: 프롬프트를 띄웠을 모든 호출이 자동
  거부됨** - 문서화된, 확실한 fail-closed 경로.
- 평범한 `claude -p`(위 셋 다 없음)는 공식 문서에 명시적 결과가 없음 -
  대신 문서 자체가 "이 상황에선 훅이 ask 대신 allow/deny를 직접
  결정하라"고 권고함. 가장 가까운 관련 문서(같은 문서 세트, 백그라운드
  서브에이전트 항목): "훅이 결정을 안 내리면 거부한다" - 프롬프트
  메커니즘이 없는 모든 경우에 대해 문서가 일관되게 가리키는 방향은
  fail-closed(거부)지 무기한 대기나 자동 허용이 아님. 근데 실측 결과
  (위 항목)는 이 방향과 안 맞았음(자동 허용) - 이 프로젝트가 `ask()`를
  완전히 버린 이유가 이거다.

### PostToolUse의 Agent 응답 필드 - 확인 완료(2026-08-15)

MEDIUM 등급의 "상위 에이전트 승인" 마커를 실제로 파싱할 수 있는지
확인하려고 임시 진단 훅 + 실제 서브에이전트 디스패치로 실측:

`PostToolUse`(matcher: Agent) 훅 입력에는 `duration_ms`와
`tool_response` 객체가 있고, `tool_response`는 `{status, prompt,
agentId, agentType, content: [{type: "text", text: "<서브에이전트 최종
응답 전문>"}], resolvedModel, totalDurationMs, totalTokens,
totalToolUseCount, usage, toolStats}` 형태 - 서브에이전트가 실제로
출력한 텍스트(테스트로 심어둔 마커 문자열 포함)가
`tool_response.content[0].text`에 그대로 보였고, `resolvedModel`이
실제 실행된 모델(예: `"claude-sonnet-5"`)을 정확히 반영했다.
`record_agent_approval.py`가 `MEDIUM-APPROVE` 마커를 파싱하고 opus 여부를
확인하는 근거가 이 실측(2026-08-16: 사용자가 sonnet도 불인정으로 정정 -
"에이전트는 오퍼스 허락만 유효"). 진단 훅과 그 `settings.json`
연결/`/tmp` 덤프는 실측 후 전부 제거함(이 세션의 다른 실측들과 동일한
정리 관례).

## 로그 유지관리

`violations_log.jsonl`/`override_audit.jsonl`/`learning_data.jsonl`(2026-08-16
추가)은 append-only + git-tracked라 계속 커진다. `tools/rotate_hook_logs.py`
가 retention 기간(기본 90일)보다 오래된 항목을 월별 아카이브 파일로
옮긴다 - 훅 체인에는 안 걸려있음(매 툴콜마다 로그 크기 재는 오버헤드
방지), 가끔 수동으로 돌리거나 Routine으로 스케줄:

```bash
python3 -m tools.rotate_hook_logs
```
