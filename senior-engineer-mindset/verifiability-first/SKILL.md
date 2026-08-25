---
name: verifiability-first
description: Turn the task into something verifiable and declare the success criterion before seeing results — 검증 가능성과 성공 기준 선언. Use when the request is vague about "done" ("동작하게 해줘", "개선해줘"), when writing tests, when fixing a bug (write the failing reproduction first), or when comparing two approaches. Critical before any measurement or benchmark, where deciding the bar after seeing the numbers guarantees a "success".
---

# 검증 가능성 우선

## 성공 기준을 먼저 못박는다

결과를 본 뒤에 기준을 정하면 무엇이든 성공으로 만들 수 있다. 그래서 **작업 전에** "무엇을 만족하면 끝인가"를 정한다.

- "동작하게 해줘" → 무엇이 동작이면 동작인가? 검증 가능한 형태로 바꾼다
- "검증 추가" → 잘못된 입력에 대한 테스트를 **먼저** 쓰고 통과시킨다
- "버그 수정" → 실패하는 **재현**을 먼저 쓰고 통과시킨다
- "A가 B보다 나은가" → 비교하기 전에 무엇을 넘겨야 이겼다고 할지 정한다 (몇 % 이상, 몇 건 중 몇 건)
- 측정·실험이 걸렸다면: 차이가 우연으로 설명될 수 있는 범위 안이면 평균이 아무리 좋아도 **"판단 불가"가 정답**이다. 결론을 못 냈다고 인정하는 것도 결과다

기준이 강하면 혼자 끝까지 갈 수 있고, "잘 되게 해줘"는 매 단계 되물어야 한다.

## 테스트 가능한 설계

검증 방법을 먼저 떠올리면 설계가 자연스럽게 좋아진다. 테스트하기 어려운 코드는 대개 책임이 뒤엉킨 코드다.

- 이 로직이 맞게 도는지 어떻게 확인할 것인가?
- 확인하려면 DB·네트워크·시간·랜덤이 꼭 필요한가? **그 부분만 떼어낼 수 있는가?**
- 실패하는 케이스를 하나 먼저 떠올린다 — 그게 사실상 첫 번째 테스트다
- 여러 단계짜리 작업은 **항목마다 검증 단계가 붙은 계획**으로 만든다
