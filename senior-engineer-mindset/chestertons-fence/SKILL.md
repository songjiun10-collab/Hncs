---
name: chestertons-fence
description: Understand why existing code exists before removing, simplifying, or refactoring it — Chesterton's Fence. Use before deleting code that looks dead or unnecessary, before simplifying anything you didn't write, or when a "cleanup" urge shows up mid-task. Companion to surgical-change and simplicity-budget — this is the check that runs before either of those act.
---

# 체스터턴의 울타리

길을 가로막는 울타리를 보고 왜 있는지 모르면, **부수지 않는다.** 먼저 이유를 이해하고, 그 이유가 지금도 유효한지 판단한 뒤에 결정한다.

## 손대기 전에 답한다

- 이 코드의 책임은 무엇인가?
- 무엇이 이걸 호출하고, 이건 무엇을 호출하는가?
- 엣지 케이스와 에러 경로는 무엇인가?
- 기대 동작을 정의하는 테스트가 있는가?
- 왜 이렇게 짜여 있을까? (성능 때문에? 플랫폼 제약? 역사적 이유?)
- `git blame`을 본다 — 이 코드가 처음 생긴 맥락은 무엇이었는가?

**위 질문에 답할 수 없다면 아직 손댈 준비가 안 된 것이다.** 지우거나 단순화하기 전에 맥락을 더 읽는다.

## 이유를 알고 나면

이유가 지금도 유효한지 판단한다:

- 그 이유가 **지금도** 맞는가, 아니면 더 이상 적용되지 않는 상황(오래된 브라우저 지원, 없어진 제약)인가?
- 이유가 사라졌다면 안전하게 제거·단순화할 수 있다 — **다만 왜 안전한지를 남긴다** (커밋 메시지, 주석)
- 이유가 여전히 유효한데 코드가 복잡해 보인다면, 복잡함은 그 제약을 반영한 것일 수 있다. **더 단순한 형태로 같은 제약을 만족시킬 수 있는가**를 묻는다 — 제약을 무시하고 단순화하지 않는다

## 흔한 함정

- "이거 왜 있는지 모르겠지만 안 쓰이는 것 같으니 지운다" → 정말 안 쓰이는지는 대개 **밖에서** 확인해야 안다 (호출부 검색, 프로덕션 로그, 다른 서비스)
- "예전 방식이라 이제 필요 없겠지" → 확인 안 된 추측이다. `search-first`나 `root-cause-discipline`으로 확인한다
- 관련 없는 죽은 코드를 발견했다면 **지우지 말고 언급만** 한다. 그건 이 작업의 범위가 아니다 (`surgical-change` 참고)
