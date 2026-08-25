---
name: fresh-context-review
description: Review code with the assumptions of the person who wrote it deliberately stripped away — 자기가 쓴 코드를 다른 눈으로 보기. Use after finishing an implementation and before declaring it done, before opening a PR, or when asked to review code that you (or the same session) just wrote. Also use when a change touched more files than expected or when the implementation drifted from the original plan.
---

# 다른 눈으로 보기

> **`adversarial-review`와의 차이**: 이건 **끝난 작업물**을 사후에 훑는 것. `adversarial-review`는 **진행 중인 결정**을 되돌리기 아직 싼 시점에 반박 편향으로 미리 심문하는 것. 되돌릴 수 없는 결정이 걸려 있다면 끝난 뒤가 아니라 `adversarial-review`를 먼저 쓴다.

코드를 쓴 맥락 그대로 그 코드를 리뷰하면 **같은 맹점을 그대로 갖는다.** 왜 그렇게 짰는지 알기 때문에 이상한 부분이 이상해 보이지 않는다. 리뷰의 가치는 대부분 "모르는 채로 보는 것"에서 나온다.

## 맥락을 벗는 법

- **결과물만 본다.** 왜 그렇게 됐는지는 잠시 잊고, diff와 최종 코드만 읽는다
- 이 코드를 처음 보는 사람이 가질 질문을 던진다: 이 변수는 언제 null이 되나? 이 함수는 무엇을 반환하나? 이 조건은 왜 필요한가?
- **원래 요구사항으로 되돌아가 대조한다.** 만든 것이 요청받은 것인가? 중간에 표류하지 않았는가?

## 두 축으로 본다

한 번에 두 가지를 섞어 보면 둘 다 놓친다. 분리한다.

1. **스펙 준수** — 요청한 것을 실제로 했는가? 빠뜨린 요구사항은? 요청하지 않은 것을 했는가?
2. **코드 품질** — 이름, 구조, 중복, 에러 처리, 경계 조건

## 검증은 직접

- 리포트나 기억을 믿지 말고 **테스트를 실제로 돌린다**
- diff를 실제로 읽는다. "고쳤다"고 생각한 것과 실제 바뀐 줄이 다를 때가 있다
- diff에서 확인할 수 없는 게 있으면 **확인 불가로 표시한다.** 넘어가지 않는다

## 자기 검열 금지

리뷰 전에 "이건 아마 괜찮을 거야"로 미리 걸러내지 않는다. 오탐이라고 생각해도 일단 올려놓고 판단은 나중에 한다. 미리 등급을 매기면 진짜 문제가 같이 묻힌다.
