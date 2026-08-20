# HNCS Hook Evolution - 다음 단계 구상

**상태 (2026-08-19 갱신)**: 브레인스토밍 완료(아래 "브레인스토밍
결정사항" 절) - `superpowers:writing-plans` 단계로 넘어갈 준비 됨.
`superpowers:brainstorming`/`writing-plans` 둘 다 이 세션엔 설치 안 돼
있어서(marketplace에 `hook`만 있음) 두 단계 다 스킬 없이 수동으로
진행 - 스킬의 의도(질문으로 모호성 먼저 걷어내기, 안 정한 것 안 남기고
넘어가기)는 그대로 지키되 메커니즘만 대체. 아직 코드 변경 없음 - 이
문서는 스펙, 플랜이 아님(root `CLAUDE.md`의 "Workflow" 절: spec → plan
→ implement).

**작성자**: 1~8절은 사용자 원문(2026-08-19, 채팅으로 제시)을 거의
그대로 옮김. "부록: 구현 제약"과 "브레인스토밍 결정사항"은 이 세션이
추가.

## 1. 기본 철학

에이전트를 믿지도, 불신하지도 않는다.
실제 에이전트의 생각과 행동을 관찰하고, 그 결과를 통해 시스템을 발전시킨다.

Hook의 목적은 에이전트의 판단을 전부 대신하는 게 아니라,
위험하거나 이탈하는 행동을 관찰하고 필요한 순간에만 개입하는 것.

## 2. Agent Drift / Aggression 관찰

먼저 에이전트가 실제로 어떤 식으로 딴짓하거나 과잉행동하는지 수집한다.

```
사용자 요청
   ↓
Agent 행동
   ↓
행동 관찰
   ├─ 정상 수행
   ├─ Task 범위 이탈
   ├─ 불필요한 반복
   ├─ 과잉 수정
   ├─ 위험한 우회
   └─ 사용자 의도와 무관한 행동
```

여기서 중요한 건 처음부터 "이건 나쁜 행동"이라고 규정하지 않는 것.
실제 행동을 모아서 패턴을 발견한다.

## 3. 행동 데이터 → 재학습

관찰된 행동을 데이터셋으로 만든다.

```
instruction
intended_scope
agent_action
target
deviation
reason
outcome
human_judgment
```

```
Agent 행동
   ↓
Hook 관찰
   ↓
데이터 축적
   ↓
패턴 분석
   ↓
재학습 / 정책 개선
   ↓
새로운 Agent
```

즉 Hook이 단순 방어벽이 아니라 데이터 수집 장치가 됨.

## 4. 데이터로 새로운 Hook 설계

여기가 핵심.

```
실제 Agent 행동
       ↓
      관찰
       ↓
   실패 패턴 발견
       ↓
      가설
       ↓
    새 Hook 설계
       ↓
      실험
       ↓
     결과 평가
       ↓
   다시 행동 데이터
       └──────────→ 반복
```

예를 들어: "Agent가 특정 종류의 파일 수정에서 자주 범위를 벗어난다."
→ `protect_scope.py` 같은 새로운 Hook을 설계. 그런데 Hook이 너무
자주 막음? → 그것도 데이터. → Hook을 다시 수정.

즉 Hook 자체가 실험 결과를 통해 진화한다.

## 5. HIGH-level Hook: 2-Agent Consensus

위험도가 높은 판단은 단일 Agent에게 맡기지 않는다.

```
             HIGH-RISK ACTION
                    ↓
          ┌─────────┴─────────┐
          ↓                   ↓
       Agent A             Agent B
       독립 판단             독립 판단
          ↓                   ↓
          └─────────┬─────────┘
                    ↓
                 비교
              /         \
            일치          불일치
             ↓              ↓
          Hook 판단       인간 판단
```

둘이 같은 판단(A=위험, B=위험) → 합의된 판단을 Hook이 처리.
둘이 다른 판단(A=위험, B=안전) → 자동 판단하지 않고 인간에게
escalation. 중요한 이유: disagreement를 불확실성의 신호로 취급하기
때문.

## 6. 인간은 "마지막 판사"가 아니라 "불확실성 해결 장치"

```
Agent A
   +
Agent B
   ↓
Consensus?
 ├─ YES → 자동 처리
 └─ NO  → Human
```

따라서 인간은 모든 행동을 검토할 필요가 없고, 에이전트들이 서로
판단하지 못하는 애매한 경우만 본다.

## 7. disagreement도 데이터

```
action
agent_a_judgment
agent_b_judgment
agreement
human_judgment
outcome
```

을 기록하면 나중에 "어떤 종류의 행동에서 Agent들이 자주 의견이
갈리는가?"를 분석할 수 있음. 그리고 그 결과가 다시 새 Hook 설계 →
새 실험으로 들어간다.

## 8. 최종 루프

```
                 ┌──────────────────────┐
                 │     User Instruction  │
                 └──────────┬───────────┘
                            ↓
                       Agent 행동
                            ↓
                     ┌─────────────┐
                     │ Hook 관찰   │
                     └──────┬──────┘
                            ↓
                       행동 데이터
                            ↓
                    ┌───────────────┐
                    │ 행동 분석     │
                    │ 실패 패턴     │
                    │ disagreement  │
                    └───────┬───────┘
                            ↓
                       가설 생성
                            ↓
                     새로운 Hook
                            ↓
                         실험
                            ↓
                       결과 평가
                            ↓
                    ────────┘
```

HIGH-risk 영역에서는:

```
Agent A ─┐
         ├─ Agreement → Hook
Agent B ─┘
Agent A ─┐
         ├─ Disagreement → Human
Agent B ─┘
```

**한 문장으로**: HNCS는 에이전트를 통제하기 위한 고정된 Hook 집합이
아니라, 에이전트의 실제 행동과 판단을 관찰하고 그 데이터를 이용해 더
나은 Hook을 계속 발견하는 피드백 시스템을 만든다. 기존 Decision Record
→ Outcome → Judgment Eval이 여기에 붙으면, 행동 → 판단 → 결과 → 평가
→ Hook 진화라는 하나의 폐루프가 만들어진다.

## 부록: 구현 제약 (2026-08-19, 이 세션이 추가)

**PreToolUse/PostToolUse 훅은 Agent를 직접 디스패치할 수 없다.** 훅은
stdin으로 JSON을 받고 stdout으로 JSON을 뱉는 동기 프로세스(`_hook_common.py`의
`allow()`/`deny()`/`ask()` 전부 `print(json.dumps(...))` 한 번으로
끝남) - Agent 툴 호출 권한이 없다. 이건 새로 발견한 문제가 아니라, MEDIUM
등급 설계 당시 이미 확정된 제약과 동일하다(`_hook_common.py` 모듈
docstring: "MEDIUM: 상위 에이전트가 허용하면 실행 에이전트가 실행" -
훅이 opus를 부르는 게 아니라, **컨트롤러가 가드된 액션 전에 opus Agent를
미리 디스패치**하고 `record_agent_approval.py`(PostToolUse)가 그 결과를
사후 파싱해서 sentinel을 남기는 구조였다).

따라서 5절 "HIGH-level Hook: 2-Agent Consensus" 다이어그램의
`HIGH-RISK ACTION → Agent A / Agent B` 화살표는 훅이 트리거하는 게
아니라, 다음 형태로 구현돼야 한다 - MEDIUM 패턴의 직접적 확장:

1. 컨트롤러가 가드된 HIGH-risk 액션 **전에** Agent A, Agent B 두 개를
   각각 독립적으로 디스패치(서로의 판단을 못 보게 - 진짜 독립 판단이
   되려면 순차 디스패치 시 이전 응답을 프롬프트에 안 넣어야 함).
2. 각 응답에서 판단 마커를 파싱하는 새 PostToolUse 훅
   (`record_consensus_judgment.py`류)이 A/B 결과를 비교해서:
   - 일치 → 합의 sentinel 기록(`medium_approval()`/`sentinel_override()`와
     같은 패턴, consensus 전용 파일).
   - 불일치 → sentinel을 안 남기거나 "disagreement" 상태로 남겨서, 가드
     훅이 `ask()`(HIGH 등급 기존 사람-확인 경로)로 넘어가게.
3. 가드 훅(PreToolUse)은 그 sentinel을 확인해서 합의 시 통과, 불일치/
   sentinel 없음 시 기존 HIGH 등급 처리(`ask()` 또는 서브에이전트발
   deny)로 fallback.

이 제약이 설계를 막지는 않는다 - 그대로 구현 가능하다는 뜻. 단
"훅이 자체적으로 두 에이전트를 부른다"는 다이어그램의 문자 그대로의
해석은 안 되고, 컨트롤러 워크플로우 규율(두 번 디스패치 + 순서/격리
규칙)이 추가로 필요하다는 것만 명시해둔다.

## 브레인스토밍 결정사항 (2026-08-19)

4개 블로킹 질문을 사용자에게 직접 묻고 답 받음 - 안 정하고 넘어가지
않음(`AskUserQuestion`, `superpowers:brainstorming` 부재로 인한 수동
대체):

1. **2-Agent Consensus 적용 범위**: **6개 HIGH 훅 전부에 한 번에**
   (`protect_branch.py`/`protect_test_coverage.py`/
   `protect_experiment_integrity.py`/`protect_reviewer_prejudging.py`/
   `protect_ready_without_review.py`/`protect_rubber_stamp_approval.py`) -
   파일럿(훅 1개만 먼저) 아님. 즉 플랜 단계에서 6개 훅 전부의 HIGH-tier
   기본 경로(`high_tier_decision()`)를 한 번에 consensus 경로로
   바꿔야 함 - 부록의 "구현 제약" 3단계(디스패치→PostToolUse 훅→
   PreToolUse 가드 확인)를 6개 모두에 적용.
2. **Agent A/B 독립성 확보 방법**: **같은 모델, 다른 프레이밍/역할**
   (다른 모델 아님 - 예: A는 "opus" B도 "opus"). 부록 1단계("서로의
   판단을 못 보게")에 이 조건이 추가됨: 프롬프트 자체가
   역할/관점(예: "승인 기준으로 검토" vs "거부 사유를 적극적으로
   찾아라")을 다르게 줘야 함 - 같은 프롬프트를 단순히 두 번 부르는 건
   상관관계 높은 판단만 낼 위험이 크다고 판단됨(질문에서 명시). 플랜
   단계에서 A/B 각각의 정확한 역할 문구를 확정해야 함 - 아직 미정.
3. **Agent Drift 관찰 로깅 범위**: **기존 게이트(decision record 있는
   MEDIUM/HIGH/CRITICAL 이벤트) 위에 `intended_scope`/`deviation` 필드만
   추가** - 모든 툴콜을 새로 커버하는 블랭킷 훅 아님. 즉 3절의
   `instruction/intended_scope/agent_action/target/deviation/reason/
   outcome/human_judgment` 스키마 중 `instruction`/`agent_action`/
   `target`/`reason`/`outcome`은 이미 Decision Record + 로그 파이프라인이
   커버하고, `intended_scope`/`deviation`/`human_judgment`만 신규 -
   `write_decision_record()`(must훅 MCP 툴) 스키마 확장 대상이 이
   3개로 좁혀짐.
4. **가설 생성 자동화 수준**: **opus 서브에이전트가
   `learning_data.jsonl`을 분석해서 새 Hook 후보를 제안** - 사람이
   로그를 직접 읽는 방식(2~7차 라운드가 해온 방식)에서 한 단계
   자동화. 단, 이 프로젝트의 기존 원칙("어떤 훅의 등급/임계값도
   자동으로 안 바꾼다", `tools/CLAUDE.md`/`eval_hook_judgments.py`
   docstring)과 일관되게 **배포(새 훅 코드 작성/`settings.json` 등록)는
   여전히 사람 승인 필요** - 제안까지만 자동, 승인/구현은 기존
   subagent-driven-development 게이트(Implementer→Reviewer→사용자)
   그대로 통과해야 함.

**다음 단계**: `superpowers:writing-plans`(역시 이 세션엔 미설치 -
시작 시 동일하게 수동 대체 필요)로 위 4개 결정을 반영한 구현 플랜
작성.
