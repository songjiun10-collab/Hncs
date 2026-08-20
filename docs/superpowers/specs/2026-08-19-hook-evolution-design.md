# HNCS Hook Evolution - 다음 단계 구상

**상태**: 사용자가 채팅으로 제시한 비전/구상 문서 - 아직 `superpowers:brainstorming`을
거친 정식 스펙도, `superpowers:writing-plans`을 거친 구현 계획도 아님.
코드 변경 없음. 이 프로젝트의 spec-before-plan 워크플로우(root
`CLAUDE.md`의 "Workflow" 절)에 따라 정식 브레인스토밍/플랜 전에 durable
기록으로 먼저 남겨두는 단계.

**작성자**: 사용자 (2026-08-19, 채팅으로 제시). 아래 1~8절은 사용자
원문을 거의 그대로 옮김 - "부록: 구현 제약" 절만 이 세션이 추가.

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
