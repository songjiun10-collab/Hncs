---
name: measure-before-optimizing
description: Verify a bottleneck exists before touching performance — 추측 대신 측정 먼저. Use before any caching, memoization, query rewrite, algorithm swap, or "이거 느릴 것 같은데" change; when a spec sets a performance target or Core Web Vitals threshold; when a user reports slowness; or when a PR bundles a performance claim with no before/after number. Skip for a fix where the bottleneck is already obvious from the code itself (e.g. an accidental O(n²) on a hot path).
---

# 측정 먼저

증거 없이 최적화하지 않는다. "이건 느릴 것 같다"는 추측이지 문제가 아니고, 추측에서 시작한 최적화는 대개 복잡도만 늘리고 체감은 없다.

## 순서: 측정 → 지목 → 고치기 → 재측정

- 먼저 **재현 가능한 측정**부터 만든다 (프로파일러, 타이밍 로그, Lighthouse, 실사용자 지표) — 감으로 "여기가 문제"라고 짚지 않는다
- 병목을 **정확히 하나** 지목한다. N+1 쿼리인지, 캐시 미스인지, 번들 크기인지 — 여러 개를 한 번에 고치면 뭐가 효과 있었는지 알 수 없다
- 고친 뒤 **같은 방법으로 재측정**한다. 개선이 측정 오차보다 커야 진짜 개선이다
- 재측정 없이 "빨라졌다"고 말하지 않는다

## 흔한 함정

- 프로파일링 없이 memoization이나 캐시부터 넣는다 — 캐시는 무효화 버그라는 새 비용을 만든다
- 여러 최적화를 한 커밋에 묶어서 뭐가 효과 있었는지 못 밝힌다
- "중립적인 변경이니 일단 남겨둔다" — 효과가 없으면 되돌린다, 근거 없는 코드를 쌓지 않는다
- 회귀를 막을 장치(모니터링·벤치마크 테스트) 없이 "이제 빠르다"로 끝낸다

## 최적화할 가치가 있는가

측정했는데 병목이 전체 경로에서 무시할 수준이면, 그건 최적화 대상이 아니라 **넘어갈 대상**이다. 성능은 예산이다 — 실제로 느낀다는 증거가 있는 곳에만 쓴다.
