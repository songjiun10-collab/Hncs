---
name: clarify-the-real-problem
description: Dig out the actual goal behind a request before building anything — 요청 뒤의 진짜 문제 찾기. Use when a request is ambiguous, when the literal ask smells like an X-Y problem (they asked for a solution, not a problem), or when a wrong interpretation would waste significant work. Also use when the user says "고민 중", "어떻게 하는 게 좋을까", or hands over a vague one-liner that implies hours of work.
---

# 진짜 문제 정의

요청받은 것과 필요한 것은 자주 다르다. "CSV 파서 만들어줘"의 진짜 문제가 "엑셀에서 데이터를 꺼내야 한다"라면 파서를 짤 필요조차 없다.

## 물어볼 것

- 이 요청 뒤에 있는 **실제 목적**은 무엇인가?
- 요청받은 대로 만들면 그 목적이 달성되는가, 아니면 더 짧은 경로가 있는가?
- 이 요청은 문제를 말하는가, 이미 정해둔 해법을 말하는가? 해법이라면 그 해법을 고른 이유는?
- 한 줄 요청이 실제로는 몇 시간짜리인가? **범위를 축소해서 이해하면 무시한 것으로 읽힌다** — 작게 해석하지 말고 크게 스코핑한 뒤 확인한다

## 모호할 때의 처리

- 해석이 여러 갈래고 결과가 크게 갈린다면 **갈래를 제시한다.** 조용히 하나 골라서 진행하지 않는다
- 되물을 때는 **한 번에 하나만.** 질문 폭탄은 진행을 막는 것과 같다
- 되돌릴 수 있는 일이면 묻지 말고 하고 결과를 보여준다. 되돌릴 수 없는 일만 먼저 확인한다
- 혼란스러우면 숨기지 말고 **무엇이 혼란스러운지 이름을 붙여서** 말한다

## 가정은 밖으로 꺼낸다

추측으로 채운 빈칸은 반드시 명시한다. "X라고 가정하고 진행했습니다"는 한 줄이 나중에 몇 시간을 아낀다.
