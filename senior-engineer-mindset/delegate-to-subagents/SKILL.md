---
name: delegate-to-subagents
description: >-
  Decide when to hand work to a subagent instead of doing it yourself, how to brief it, how to run the fix/review loop when something comes back wrong, and how to verify what comes back — 서브에이전트 위임 판단·브리핑·수정 루프·검증. Use when a task is big enough to delegate (independent research, a parallelizable slice, a second opinion, a review pass), when running more than one agent, when a subagent's report claims something is finished, or when a review comes back with findings that need fixing. Skip for single-step edits or when no subagent tooling is available. Bundles an optional PreToolUse/PostToolUse hook (scripts/check_dispatch_brief.py) that nudges on two of the mistakes this skill warns about.
---

# 서브에이전트에 위임하기

에이전트에게 일을 맡기는 것도 결정이다. 잘못 위임하면 직접 하는 것보다 느리고, 검증 없이 믿으면 안 한 일을 했다고 보고받는다.

## 위임할지부터 정한다

- 독립적으로 조사·실행할 수 있는 덩어리인가, 아니면 매 스텝이 직전 결과에 의존하는가? 후자는 위임보다 직접 하는 게 빠르다 — 순차로 하나씩
- **서로 다른 독립 도메인이면 병렬이 정상이다.** 관련 없는 실패 3개(다른 파일·다른 원인)를 고칠 땐 한 응답 안에서 dispatch를 여러 번 호출한다 — 이게 병렬 실행이다. 각 에이전트는 세션 히스토리를 전혀 안 받고, 좁은 범위(파일 하나·서브시스템 하나) + 명시적 제약("프로덕션 코드는 건드리지 마라") + 구체적 산출물만 받는다. 서로 관련 있는 실패(하나 고치면 다른 것도 고쳐질 수 있는)는 병렬로 쪼개지 말고 순차로
- **같은 라이브 파일을 동시에 고치는 건 안 된다.** 관련 없는 도메인이라도 겹치는 파일이 있으면 그 파일만 순차로 뺀다
  - 접근법 자체를 비교하려고 **일부러** 여러 에이전트에게 같은 문제를 다르게 풀게 시키는 것도 다른 경우다 — 이건 각자 격리된 워크스페이스(git worktree 등)에서 돌린다. 워크트리는 커밋된 것만 보인다는 점에 주의 — 아직 커밋 안 한 초안·스크립트를 워커가 봐야 하면 그 파일들을 명시적으로 복사해 넣는다(그냥 "보이겠지" 하고 넘어가면 워커가 못 찾는다)
- "귀찮아서"는 위임 이유가 아니다. 컨텍스트를 아끼려고, 진짜 독립 도메인이라서, 또는 접근법을 비교하려고 — 이유는 있어야 한다
- **역할마다 권한을 다르게 준다.** 리뷰만 시킬 서브에이전트에 쓰기 권한까지 주지 않는다 — 책임이 갈리면 지시뿐 아니라 권한도 갈라야, 리뷰어가 리뷰하다 말고 고쳐버리는 일이 없다

## 브리핑하는 법

- **작업 + 건드릴 인터페이스 + 제약**만 준다. 세션 히스토리를 요약해서 붙이지 않는다 — 필요한 파일 경로를 주고 서브에이전트가 직접 읽게 한다
- 붙여넣은 텍스트나 되받은 요약은 그 순간부터 내 컨텍스트에 눌러앉는다. 파일 경로 전달이 항상 더 싸다
- 대상이 애매하면("이거 좀 고쳐줘") 위임 전에 내가 먼저 좁힌다 — 애매한 브리핑은 애매한 결과로 돌아온다
- **위임 직전에 기준점을 적어둔다** (`git rev-parse HEAD` 등). 나중에 diff나 리뷰 범위를 잡을 땐 이 기준점을 쓴다 — `HEAD~1`은 그 사이 다른 커밋이 끼면 조용히 범위를 잘못 잡는다

## 결과를 검증한다

- **보고를 그대로 믿지 않는다.** "테스트 통과했습니다"는 주장이지 증거가 아니다 — 직접 돌려보거나 diff를 읽는다 (`verify-before-claiming`과 같은 원칙, 위임했다고 예외 아니다)
- 보고와 리뷰는 **파일로 받는다.** 대화창에 길게 받으면 압축(compaction)에 날아가고 다음 라운드가 처음부터 다시 읽어야 한다
- 리뷰를 시켰다면 무엇을 지적하지 말라고 미리 말하지 않는다 — 걸러내고 싶은 결과여도 일단 올라오게 하고 그 다음에 내가 판단한다. 스펙 준수와 코드 품질은 **다른 축**이니 하나가 다른 하나를 가리게 두지 않는다
- **병렬로 여러 개를 돌렸다면**, 합치기 전에: 각 요약을 따로 읽는다 → 같은 코드를 두 에이전트가 건드렸는지 확인한다(겹쳤으면 그 부분만 다시 본다) → 전체 테스트를 한 번 더 돌려서 개별로는 안 보이던 조합 문제를 잡는다

## 막히거나 리뷰가 안 끝나면

- "막혔다"(BLOCKED)는 보고를 받으면 같은 지시로 재시도하지 않는다 — 구체적 피드백을 주고 재시도하거나, 더 강한 모델을 쓰거나, 작업을 쪼갠다. 바뀐 게 없으면 결과도 안 바뀐다
- 리뷰에서 나온 지적은 **한 번에 한 서브에이전트**가 전부 받아서 고친다 — 지적 하나당 새 서브에이전트를 띄우면 매번 컨텍스트를 처음부터 다시 쌓는다
- 고침 → 재리뷰 루프에 **상한을 둔다** (예: 3회). 상한을 넘도록 안 끝나면 내가 직접 판정한다: 지적이 틀렸다/사소하다 → 이유를 남기고 넘어간다, 진짜고 중요하다 → 가장 작은 수정을 내가 정하고 기록한다. **조용히 버리지 않는다** — 어느 쪽이든 판정과 이유를 남긴다
- **내가 직접 고치지 않는다** (리뷰가 필요 없다고 판단한 사소한 경우 제외). 컨트롤러가 직접 고치면 리뷰 단계를 건너뛰고, 그 코드가 내 컨텍스트에 쌓인다
- 되돌리기 어려운 결정인데 판단이 갈리면, 리뷰 한 번 대신 에이전트 둘에게 반대 입장을 맡겨 논쟁시켜 본다 — 한쪽 의견만으로는 안 보이던 트레이드오프가 그제야 드러나는 경우가 있다 (`weigh-tradeoffs`·`adversarial-review`와 같은 상황에 쓰는 더 무거운 도구)

## 흔한 실패

- 여러 에이전트가 같은 파일을 동시에 고쳐서 서로 덮어쓴다
- 서브에이전트가 "완료"라고 했다는 이유만으로 검증 없이 다음 단계로 넘어간다
- 위임한 덩어리가 너무 커서 내가 결과를 검토할 수 없다 — 검토 못 할 크기면 애초에 잘못 쪼갠 것
- 서브에이전트가 끝나길 촘촘한 간격으로 계속 확인한다 — 막힌 걸 알아채려고 하는 건데, 오히려 결과 기다리는 시간만 늘어난다. 완료 신호가 올 때까지 기다렸다가 처리한다

## 선택: 훅으로 강제하기

이 원칙 중 기계적으로 잡히는 두 가지 — **긴 대화 요약을 그대로 붙여넣기**, **동시에 열린 dispatch가 너무 많아지기**(2~3개는 정상, 그 이상만 걸림) — 는 `scripts/check_dispatch_brief.py`가 Task 호출 직전(PreToolUse)에 감지한다. 기본은 **경고만 하고 막지 않는다** (자기 프로젝트가 아닌 곳에 설치될 걸 감안한 기본값). 실제로 막고 싶으면 환경변수 `DELEGATE_HOOK_STRICT=1`을 훅 명령에 붙인다 — 스크립트 상단 주석에 정확한 동작이 적혀 있다.

`.claude/settings.json`에 추가:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Task",
        "hooks": [
          { "type": "command", "command": "python3 .claude/skills/delegate-to-subagents/scripts/check_dispatch_brief.py" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Task",
        "hooks": [
          { "type": "command", "command": "python3 .claude/skills/delegate-to-subagents/scripts/check_dispatch_brief.py" }
        ]
      }
    ]
  }
}
```

같은 스크립트를 PreToolUse·PostToolUse 둘 다에 건다 — PostToolUse는 "이 dispatch가 끝났다"를 기록해서 겹침 카운트를 맞추는 용도다(하나만 걸면 카운트가 계속 늘어나기만 한다). 스킬 설치 경로가 다르면 명령의 경로도 맞춰 바꾼다. 기본은 조용히 경고만 한다(사람이 보는 transcript에만 뜬다) — Claude가 실제로 반응하게 하려면(=진짜로 막으려면) `DELEGATE_HOOK_STRICT=1`을 명령 앞에 붙인다(`"command": "DELEGATE_HOOK_STRICT=1 python3 ..."`). 이 훅은 예시 수준이다 — Hncs의 `protect_never_touch.py`처럼 몇 주간 레드팀 검증을 거친 CRITICAL 등급 강제가 아니라, 이 스킬이 말로 하는 조언을 최소한으로 기계화한 것. 정말 강하게 막을 게 필요하면 이 스크립트를 시작점으로 프로젝트에 맞게 고쳐 쓴다.
