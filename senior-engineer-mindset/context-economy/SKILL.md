---
name: context-economy
description: Decide what information goes where — in context, in a file, or dropped — 컨텍스트 경제. Use when handing work off (to another session, agent, or person), when a task involves large files or long outputs, when writing a plan or spec that must outlive the conversation, or when the conversation is getting long enough that earlier details are at risk. Also use when deciding whether an answer should be chat text or a durable artifact.
---

# 컨텍스트 경제

**컨텍스트 창은 최적화하고, 나머지는 전부 영속화한다.**

대화에 붙여넣은 것은 그 세션 내내 자리를 차지하고, 대화가 끝나면 사라진다. 최악의 조합이다 — 비싸면서 휘발성이다. 파일은 반대다: 필요할 때만 읽고, 끝나도 남는다.

## 무엇을 어디에 두는가

| 성격 | 어디에 |
|---|---|
| 이번 판단에만 필요한 것 | 컨텍스트 (그리고 버린다) |
| 다시 볼 것 / 남아야 할 것 | 파일 |
| 다른 사람·세션이 이어받을 것 | 파일 + 위치를 알려주는 포인터 |
| 크고 대부분 안 쓰이는 것 | 파일에 두고 **필요한 부분만** 읽는다 |

## 실전 규칙

- **텍스트가 아니라 파일을 넘긴다.** 긴 로그·전체 파일·대량 출력을 대화에 붙여넣지 말고, 경로를 넘기고 필요한 부분만 읽게 한다
- **결과물을 요청받았으면 파일로 낸다.** 분석·이력·기록 요청은 대개 파일(또는 커밋)을 뜻한다. 대화에 뿌린 산문은 세션이 끝나면 전달되지 않은 것과 같다
- **핸드오프는 작업 하나만 담는다** — 할 일 + 건드리는 인터페이스 + 제약. 세션 히스토리 전체가 아니다
- 대화가 길어지면 **지금까지의 결정을 파일에 고정**한다. 나중에 기억보다 그 파일을 믿는다

## 요약이 아니라 포인터

"이 파일에는 A, B, C가 있습니다"라고 요약해서 컨텍스트를 채우는 대신, **어디를 보면 되는지**를 남긴다. 요약은 낡고 원본은 안 낡는다.
