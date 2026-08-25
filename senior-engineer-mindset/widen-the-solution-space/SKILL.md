---
name: widen-the-solution-space
description: Deliberately widen the set of candidate approaches before committing to one — 첫 아이디어에 안주하지 않기. Use before irreversible decisions (architecture, DB schema, data format, public API), when the first solution feels complicated or awkward, when the user is deciding rather than instructing ("어떻게 하는 게 좋을까"), or when a previous attempt at the same problem failed. Skip for routine work with one obvious answer.
---

# 발산 후 수렴

가장 흔한 실패는 **첫 번째로 떠오른 그럴듯한 해법이 곧바로 정답이 되는 것**이다. 그 해법이 나쁘지 않기 때문에 더 나은 해법을 찾을 이유가 사라진다. 유창하게 코드를 생성할 수 있을수록 이 함정이 깊다.

## 발산: 12개 자극축

머릿속으로 빠르게 훑는다. 각 한 줄이면 충분하고, 억지로 다 채우지 않는다.

1. **뻔한 해법** — 가장 먼저 떠오른 것. 기준점으로 남긴다
2. **업계 표준** — 이 문제를 이미 푼 사람들은 보통 어떻게 하는가
3. **가장 단순한 것** — 부끄러울 만큼 단순한 방법. 의외로 이게 정답일 때가 많다
4. **아무것도 만들지 않기** — 기존 라이브러리·기능·수동 절차로 대체되는가
5. **문제 자체를 없애기** — 애초에 이 상황이 안 생기게 상류를 바꿀 수 있는가
6. **반대 방향** — 정반대 전제를 깔면? (push↔pull, 동기↔비동기, 저장↔재계산, 즉시↔지연)
7. **다른 계층에서 풀기** — 코드 대신 DB에서, 앱 대신 인프라에서, 런타임 대신 빌드타임에
8. **범위를 줄인 버전** — 80%만 커버하는 해법. 나머지 20%가 정말 필요한가
9. **인접 분야에서 빌려오기** — 다른 도메인의 익숙한 패턴이 여기 맞는가
10. **다른 자료구조·모델** — 데이터를 다르게 표현하면 문제가 쉬워지는가
11. **사거나 빌리기** — 직접 만들지 않고 외부 서비스·도구를 쓴다면
12. **미래에서 역산** — 이게 잘 굴러가는 1년 뒤 모습에서 거꾸로 오면 지금 무엇부터인가

## 수렴

- 실제로 검토할 가치가 있는 **2~3개만** 남긴다. 명백히 안 되는 건 이유를 설명하지 말고 조용히 뺀다
- 남은 후보는 `weigh-tradeoffs`로 넘긴다
- **탈락시킨 것 중 아까운 게 있었다면 한 줄로 언급한다** — 사용자가 그쪽을 원할 수도 있고, 나중에 방향을 틀 때의 실마리가 된다

## 출력

**12개를 나열하지 않는다.** 발산은 대부분 머릿속에서 끝나고, 사용자에게는 추려진 2~3개와 무엇을 왜 골랐는지만 보여준다. 아이디어 목록 자체는 사용자에게 가치가 없다.
