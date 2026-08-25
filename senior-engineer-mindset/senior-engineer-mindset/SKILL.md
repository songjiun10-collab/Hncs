---
name: senior-engineer-mindset
description: Router for thinking like a senior engineer BEFORE writing code — 코드 쓰기 전에 시니어처럼 사고하기. Picks which thinking disciplines fit the task at hand and dispatches to them. Use this proactively whenever the user asks to build a feature, choose a library/framework/database, design an API or data model, fix a bug whose cause isn't obvious, or refactor — even if they never say "설계", "design review", or "시니어". Skip for one-line fixes, explicitly throwaway prototypes, or when the user handed over a fully-specified plan and just wants it typed out.
---

# Senior Engineer Mindset (라우터)

주니어와 시니어의 차이는 "코드를 얼마나 잘 짜느냐"보다 **짜기 전에 무엇을 생각하느냐**에서 갈린다. LLM은 유창하게 코드를 뽑기 때문에 이 단계를 특히 쉽게 건너뛴다 — 첫 번째로 떠오른 그럴듯한 해법이 곧바로 코드가 된다.

작업 전체는 대략 이 흐름을 탄다:

```
확인 → 이해 → 탐색 → 결정 → 설계 점검 → 검증 설계 → 계획 → 구현 → 되돌아보기
```

이 스킬은 **각 단계에서 어떤 사고 규율을 꺼낼지 고르는 라우터**다. 실제 내용은 각 하위 스킬에 있다. 전부 적용하지 않는다 — 이 작업에 실제로 물리는 2~4개만 고른다.

## 하위 스킬 (전부 model-invoked)

작업 흐름 순서대로:

| 단계 | 스킬 | 무엇을 하는가 |
|---|---|---|
| 확인 | `search-first` | 외부 API·라이브러리는 기억 말고 문서로 확인한다 |
| 확인 | `context-economy` | 무엇을 컨텍스트에 올리고 무엇을 파일에 둘지 |
| 이해 | `clarify-the-real-problem` | 요청 뒤의 진짜 목적을 캐낸다 |
| 탐색 | `widen-the-solution-space` | 첫 아이디어에 안주하지 않게 후보를 넓힌다 |
| 결정 | `weigh-tradeoffs` | 대안을 비교하고 결정 무게를 잰다 |
| 결정 | `record-the-why` | 결정과 기각한 대안을 영구 기록으로 남긴다 (ADR) |
| 설계 점검 | `premortem` | 실패 시나리오를 먼저 그린다 |
| 설계 점검 | `simplicity-budget` | YAGNI·복잡도 예산 |
| 설계 점검 | `design-for-the-next-reader` | 6개월 후 독자 + 인터페이스 먼저 |
| 설계 점검 | `interface-contracts` | Hyrum의 법칙 — 노출한 건 전부 약속이 된다 |
| 설계 점검 | `threat-and-scale-check` | 신뢰 경계·규모·다층 방어 |
| 검증 설계 | `verifiability-first` | 성공 기준을 먼저 못박는다 |
| 계획 | `bite-sized-plan` | 설계를 독립 테스트 가능한 작은 작업으로 |
| 위임 | `delegate-to-subagents` | 서브에이전트 위임 판단·브리핑·검증 (+ 선택형 훅) |
| 디버깅 | `root-cause-discipline` | 이미 풀렸는지 확인 → 근본 원인 → 증거 |
| 실행 규율 | `chestertons-fence` | 지우거나 단순화하기 전에 왜 있는지부터 |
| 실행 규율 | `surgical-change` | 요청에 추적되지 않는 줄은 넣지 않는다 |
| 실행 규율 | `measure-before-optimizing` | 성능 작업은 증거(측정)부터, 추측으로 안 건드린다 |
| 실행 규율 | `honest-artifacts` | 미검증 라벨·재현 가능성·지표의 함정 |
| 되돌아보기 | `fresh-context-review` | 쓴 맥락을 벗고 결과물만 다시 본다 |
| 되돌아보기 | `verify-before-claiming` | 완료를 말하기 전에 실제로 돌려본다 |
| 되돌아보기 | `adversarial-review` | 진행 중인 결정을 반박 편향으로 미리 심문 |

## 상황별 선택

| 상황 | 꺼낼 스킬 |
|---|---|
| 요구사항이 모호함 | clarify-the-real-problem · weigh-tradeoffs |
| 새 기능 구현 | premortem · verifiability-first · design-for-the-next-reader |
| 외부 라이브러리·API 사용 | search-first · premortem |
| 구현 끝내고 마무리 | verify-before-claiming · fresh-context-review · surgical-change |
| 여러 단계짜리 작업 착수 | bite-sized-plan · verifiability-first |
| 인수인계·긴 세션 정리 | context-economy · honest-artifacts |
| 기술·라이브러리 선택 | widen-the-solution-space · weigh-tradeoffs · simplicity-budget |
| API·인터페이스 설계 | interface-contracts · design-for-the-next-reader · weigh-tradeoffs |
| 데이터 모델·DB 스키마 | weigh-tradeoffs · threat-and-scale-check · design-for-the-next-reader |
| 버그 수정 | root-cause-discipline · verifiability-first · premortem |
| 리팩터링 | chestertons-fence · simplicity-budget · surgical-change |
| 사용자 입력·외부 연동 | threat-and-scale-check · premortem |
| 성능 문제 | measure-before-optimizing · root-cause-discipline · honest-artifacts |
| 기존 코드에 끼워넣기 | surgical-change · root-cause-discipline · design-for-the-next-reader |
| 측정·실험·파라미터 튜닝 | verifiability-first · honest-artifacts |
| 권한·인증·안전장치 | threat-and-scale-check · adversarial-review · weigh-tradeoffs |
| 되돌릴 수 없는 결정(스키마·공개 API·마이그레이션) | adversarial-review · weigh-tradeoffs · record-the-why |
| 서브에이전트·여러 에이전트 굴리기 | delegate-to-subagents · bite-sized-plan |

표에 없으면 `clarify-the-real-problem` + `premortem` + `weigh-tradeoffs`에서 시작한다.

## 먼저: 세 경로 중 하나로 분류한다

첫 질문을 하기 전에 이 작업이 어느 경로인지 **소리 내어 말한다.** 그래야 사용자가 뒤집을 수 있다.

- **스파이크** — 타당성 질문 ("되나?", "가능한가?", "대충이라도"). 산출물은 **답이지 코드가 아니다.** 무엇을 시도할지 2~3문장으로 말하고, 가장 싸게 확인한다. 만든 것은 버릴 것으로 표시한다
- **한정** — 이 레포에 **이미 존재하는 흐름**에 대한 좁은 변경. 플래그 추가, 작은 엔드포인트, 한 파일 수정. 핵심은 "내가 이런 앱을 안다"가 아니라 **바꿀 흐름을 여기서 읽을 수 있다**는 것. 읽을 흐름이 없으면 한정이 아니다. 짧은 설계를 채팅으로 제시하고 멈춘다
- **구조적** — 새 프로젝트, 새 하위 시스템, 컴포넌트 관계나 남이 의존하는 인터페이스를 바꾸는 것. 질문 → 대안 → 설계 → 계획(`bite-sized-plan`) 전 과정을 밟는다

**애매하면 무거운 쪽을 택한다.** 래칫은 한 방향으로만 돈다 — 하다가 숨은 복잡도가 나오면 경로를 올린다(멈추고 그렇게 말한다). 내려가는 일은 없다.

### "너무 간단해서 확인이 필요 없다"는 함정

**형식은 작업 크기에 따라 줄어들지만, 확인 자체는 줄지 않는다.** 두 문장짜리 설계여도 제시하고 반응을 받는다. 가정이 검토되지 않아 헛일이 되는 건 오히려 "간단한" 작업 쪽이다.

| 생각 | 실제 |
|---|---|
| "너무 간단해서 설계가 필요 없다" | 간단하면 짧은 설계다. 설계 없음이 아니다 |
| "한정이라고 부르고 스펙을 건너뛰자" | 건너뛸 구실을 찾는 것 자체가 의심 신호다. 무거운 쪽으로 |
| "이런 앱을 아니까 한정이다" | 한정은 내 익숙함이 아니라 **레포**를 기준으로 한다. 새 프로젝트는 구조적이다 |
| "커졌지만 거의 끝났으니 재분류는 생략" | 숨은 복잡도는 경로를 올린다. 멈추고 말한다 |
| "스파이크가 잘 됐으니 코드를 남기자" | 스파이크의 산출물은 답이다. 코드를 남기는 건 새 요청이다 |

## 규모에 따라 달라지는 것

경로별로 **형식**만 달라진다:

- **스파이크** — 2~3문장. 하위 스킬을 형식대로 돌리지 않는다
- **한정** — bullet 3~5개짜리 설계 메모. 관련된 규율만 꺼낸다
- **구조적** — 아래 형식으로 정리 후 `bite-sized-plan`으로 넘긴다

## 출력 형식 (중간~큰 작업)

```markdown
**설계 메모 — [작업명]**

- [항목]: [한 줄 결론]
- [항목]: [한 줄 결론]
- 선택: [고른 방향]. 이유: [한두 문장]
- 열어둔 것: [지금 의도적으로 안 한 것 / 나중에 바꿀 지점]
```

메모는 **승인 요청이 아니다** — 방향이 명백하면 쓰고 바로 진행한다. 다만 되돌리기 어려운 결정이 걸렸거나, 대안의 우열이 사용자 우선순위에 따라 뒤집히거나, 요청대로 만들면 진짜 목적이 달성 안 될 것 같을 때는 메모까지만 쓰고 한 번 멈춘다.

## 생략

- 한 줄 수정·오타·변수명 변경
- 사용자가 구체적 스펙을 주고 "이대로 짜줘"라고 한 경우 — 결정은 끝났다
- "실험용", "프로토타입"이라고 명시된 코드
- 이 대화에서 같은 작업에 이미 사고 과정을 거친 경우 (단 `fresh-context-review`는 구현 후에 별도로 돈다)
