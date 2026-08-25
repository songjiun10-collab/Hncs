---
name: record-the-why
description: Capture the reasoning behind a decision permanently, not just the decision itself — 결정의 이유를 영구 기록으로 남긴다 (ADR). Use when making an architectural choice, changing a public API or data format, choosing between libraries, or reversing an earlier decision. Also use when a comment would just restate the code instead of explaining a non-obvious constraint. Skip for self-explanatory code or decisions that are trivially reversible.
---

# 이유를 기록한다

코드는 **무엇을 했는지**는 보여주지만 **왜 그렇게 했는지**는 안 보여준다. 6개월 뒤 그 결정을 다시 마주친 사람(대개 자기 자신)은 코드만 보고는 "이걸 왜 이렇게?"에 답할 수 없다.

## 언제 남기는가

- 아키텍처 선택, 공개 API/데이터 포맷 변경, 라이브러리 선택처럼 **되돌리기 비싼 결정**을 내렸을 때
- 이전 결정을 뒤집었을 때 — 특히 왜 예전 방식이 더 이상 안 맞는지
- 비직관적인 제약을 우회하려고 부자연스러운 코드를 썼을 때 (그 코드만 보면 "왜 이렇게 짰지" 싶은 지점)

코드가 스스로 설명되는 곳(변수명, 함수 분리로 충분한 곳)에는 남기지 않는다 — 코드를 그대로 되풀이하는 주석은 소음이다.

## 어디에 남기는가

- 이 저장소에 이미 있는 관례(ADR 디렉터리, 설계 문서, 커밋 메시지 컨벤션)를 먼저 확인하고 맞춘다 — 새 형식을 만들지 않는다
- 관례가 없으면 최소한 커밋 메시지나 코드 근처 주석에: **결정 + 기각한 대안 + 이유**
- `weigh-tradeoffs`로 이미 대안을 비교했다면 그 결과를 그대로 옮긴다 — 다시 쓰지 않는다

## 기록은 지우지 않는다

- 결정이 바뀌면 예전 기록을 지우고 다시 쓰지 않는다 — **새 기록으로 뒤집는다.** 왜 바뀌었는지가 그 자체로 정보다
- "나중에 정리하겠다"며 미루면 그 시점의 맥락(왜 그때 이게 최선이었는지)은 영영 사라진다 — 결정 직후가 가장 싸다
