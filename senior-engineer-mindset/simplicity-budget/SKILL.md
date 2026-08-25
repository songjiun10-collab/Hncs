---
name: simplicity-budget
description: Keep the solution as small as the problem — YAGNI와 복잡도 예산. Use when a design starts growing abstractions, config options, or extension points; when adding a dependency; when a file or function keeps getting longer; or when the user asks whether something is over-engineered. Also use before building anything justified by "나중에 필요할지도".
---

# 복잡도 예산

복잡도는 예산처럼 취급한다. 쓸 때마다 나중에 이자를 붙여 갚는다.

## YAGNI — 지금 필요 없는 건 만들지 않는다

"나중에 필요할 것 같아서" 넣은 추상화·설정 옵션·확장 포인트는 대부분 쓰이지 않고, 대신 **지금** 코드를 읽기 어렵게 만든다.

- 이 기능·파라미터·계층이 **지금** 필요한가?
- "언젠가 DB를 바꿀 수도 있으니까" 같은 가정 위에 설계하고 있지 않은가?
- 요청받지 않은 기능, 단일 사용처를 위한 추상화, 일어날 수 없는 경우의 에러 처리 — 전부 뺀다
- 확장성은 지금 만들어두는 게 아니라 **나중에 확장하기 쉬운 구조로 남겨두는 것**이다

## 복잡도 점검

- 이 문제를 **절반의 코드**로 푸는 방법이 있는가? 200줄이 50줄이 될 수 있으면 다시 쓴다
- "시니어 엔지니어가 이걸 보고 과하다고 할까?" — 그렇다면 단순화한다
- 새로 도입하는 의존성·개념·계층이 그만한 값어치를 하는가?
- 조건 분기가 늘고 있다면, 애초에 그 케이스가 **안 생기게** 만들 수는 없는가?
- 파일이 계속 커지는 건 중립적 사실이 아니라 신호다. 책임별로 쪼갠다

## 단순함 ≠ 일회용

한 번 쓰고 버릴 분석·스크립트라도 **실제 결과를 만들어냈다면 파일로 남긴다.** 단순하고 추상화 없는 건 괜찮지만, 셸 히스토리나 `/tmp`에만 있는 건 다음 사람이 다시 만들어야 한다는 뜻이다.
