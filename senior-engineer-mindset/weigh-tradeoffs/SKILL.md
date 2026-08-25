---
name: weigh-tradeoffs
description: Compare real alternatives explicitly and record why one was chosen — 트레이드오프 비교와 결정 무게 재기. Use when picking between libraries, data structures, architectures, or storage options; when a decision is hard to reverse (schema, public API, data format, dependency); or when the user asks "A랑 B 중에 뭐가 나아". Also use to decide how much deliberation a decision even deserves.
---

# 트레이드오프와 결정의 무게

## 먼저: 이 결정이 얼마나 무거운가

모든 결정에 같은 시간을 쓰지 않는다.

- **되돌리기 쉬운 결정** (함수 내부 구현, 파일 위치, 변수명) → 고민하지 말고 만들고 나중에 고친다
- **되돌리기 어려운 결정** (DB 스키마, 공개 API, 데이터 포맷, 핵심 의존성, 이미 나간 인터페이스) → 시간을 더 쓰고 대안을 진지하게 본다

확인 절차도 같은 등급을 따른다: 되돌릴 수 있으면 그냥 하고, 되돌릴 수 없으면 먼저 확인받는다. **모든 것에 같은 무게의 게이트를 걸면 게이트 자체가 무시된다.**

## 비교하는 법

- 진짜 대안 2~3개의 장단점을 **한 줄씩** 정리한다: 속도 vs 복잡도, 유연성 vs 러닝커브, 지금 편함 vs 나중 편함, 성능 vs 가독성
- 익숙하다는 이유로 반사적으로 고르지 않는다. 익숙함은 장점이 맞지만 **명시된 장점**이어야 한다
- 각 대안이 틀렸을 때의 비용을 본다. 비용이 비대칭이면 (하나는 되돌리기 쉽고 하나는 어렵다면) 그게 대개 결정타다

## 이유를 남긴다

- 왜 이걸 골랐는지 **한두 문장**을 코드 주석·커밋 메시지·설계 메모 중 어딘가에 남긴다
- 6개월 뒤 "왜 이렇게 했지?"에 답할 수 있어야 한다. 답할 수 없으면 다음 사람은 그냥 갈아엎는다
- **기각한 대안도 함께 남긴다.** 왜 안 썼는지가 없으면 다음 사람이 같은 길로 다시 들어간다
