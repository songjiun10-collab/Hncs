---
name: interface-contracts
description: Design public interfaces so that observable behavior becomes an implicit promise — Hyrum's Law and contract-first API design. Use when designing REST/GraphQL endpoints, module boundaries, type contracts between files, component props, or any surface where one piece of code talks to another. Complements design-for-the-next-reader with a sharper focus on what you're accidentally promising.
---

# 인터페이스 계약

## Hyrum의 법칙

> API 사용자가 충분히 많아지면, 계약에 뭐라고 약속했든 상관없이 **관찰 가능한 모든 동작**을 누군가는 의존하게 된다.

문서화 안 된 특이 동작, 에러 메시지 문구, 처리 순서, 타이밍까지 — **보이는 모든 것이 사실상의 계약이 된다.** 이게 뜻하는 것:

- 노출하는 것에 **의도적**이어야 한다. 관찰 가능한 모든 동작이 잠재적 약속이다
- 구현 세부사항을 새어나가게 하지 않는다. 보이면 누군가는 의존한다
- 나중에 없애기 어려운 것은 **설계 시점에** 없앨 계획을 세운다
- 테스트를 통과한다고 안전한 게 아니다. 계약 테스트가 완벽해도, 문서화 안 된 동작에 의존한 사용자는 "안전한" 변경에도 깨진다

## 인터페이스 먼저 정의한다

구현보다 계약을 먼저 쓴다. 계약이 스펙이고, 구현은 그걸 따른다.

- 함수 시그니처, 입출력 타입, 각 메서드가 무엇을 보장하는지(멱등성, 부분 업데이트, 실패 시 동작)를 코드보다 먼저 적는다
- 에러 상황을 명시한다: 없는 리소스를 요청하면? 잘못된 입력이면? 부분 실패는 어떻게 표현되는가?
- 이 계약을 호출자 관점에서 한 줄 써본다 — 쓰기 편한가?

## 원 버전 규칙

같은 의존성·API의 여러 버전을 소비자가 선택하게 만들지 않는다. 다른 소비자가 다른 버전을 요구하면 다이아몬드 의존성 문제가 생긴다. 언제나 한 버전만 존재하는 세계를 설계한다 — 갈라 치지 말고 확장한다.

## 점검 질문

- 이 인터페이스가 노출하는 것 중, **의도치 않게** 약속이 되어버릴 수 있는 게 있는가? (에러 메시지 문구, 반환 순서, 내부 타입 이름)
- 이걸 나중에 바꾸려면 얼마나 아파질까? 아프다면 지금 더 신중하게 설계한다
- 경계를 넘는 데이터의 형태와 책임이 명확한가? 잘못 쓰기 어려운 형태인가?
- 이 변경이 기존 사용자의 **문서화 안 된** 관찰 동작을 깨는가? 테스트 통과와 무관하게 물어야 한다
