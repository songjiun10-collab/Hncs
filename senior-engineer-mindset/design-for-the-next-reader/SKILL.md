---
name: design-for-the-next-reader
description: Design so that the next person to open this code can understand and change it — 6개월 후의 독자와 인터페이스 우선 설계. Use when designing an API, module boundary, or data model; when naming things that other code will depend on; when taking a shortcut that should be labeled; or when deciding how to split responsibilities across files.
---

# 다음 독자를 위한 설계

지금 동작하게 만드는 것과, 6개월 뒤 다른 사람(또는 미래의 자신)이 이해하고 고칠 수 있게 만드는 것은 다른 문제다.

## 인터페이스 먼저

구현부터 쓰면 **짜기 편한** API가 나오고, 인터페이스부터 쓰면 **쓰기 편한** API가 나온다.

- 이걸 호출하는 코드는 어떻게 생겼으면 좋겠는가? **그 호출 코드를 먼저 한 줄 써본다**
- 잘못 쓰기 어려운 형태인가? 인자 순서를 헷갈리게 하지 않는가? 잘못된 상태를 애초에 표현할 수 없게 만들 수 있는가?
- 이 경계를 넘나드는 데이터의 형태와 책임이 명확한가?
- 좋은 모듈은 깊다 — **작은 인터페이스 뒤에 많은 동작.** 인터페이스가 내부만큼 복잡해지면 경계를 잘못 그은 것이다

## 6개월 후의 관점

- 이름과 구조만 보고 무슨 일을 하는지 알 수 있는가?
- 요구사항이 조금 바뀌면(필드 하나 추가) 이 구조가 버티는가, 다시 짜야 하는가?
- 프로젝트의 기존 용어를 쓰고 있는가? 같은 개념에 새 이름을 붙이면 다음 사람은 두 개가 다른 건 줄 안다
- 기존 스타일과 어긋나는가? 내 취향이 더 나아도 **기존 스타일에 맞춘다**

## 지름길은 라벨을 붙인다

하드코딩·임시방편·성능을 위한 트릭을 썼다면 **그 사실과 이유를 남긴다.** 근거 없이 남은 코드는 다음 사람이 손대지 못하거나, 반대로 아무 생각 없이 지운다.
