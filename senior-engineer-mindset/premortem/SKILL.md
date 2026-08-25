---
name: premortem
description: Map the failure scenarios before writing the happy path — 실패 시나리오 먼저 그리기. Use before implementing any feature that touches I/O, user input, external services, concurrency, or persisted state. Also use when adding error handling, when a bug report suggests an unhandled edge case, or when reviewing whether a design is production-ready. Covers both "what breaks" and "how would we even find out".
---

# 사전 부검

"정상 작동하는 경우"가 아니라 **"이게 언제 깨지는가"**를 먼저 묻는다. 나중에 하면 방어 코드가 덕지덕지 붙고, 미리 하면 구조 자체가 달라진다.

## 어디서 깨지는가

- 입력이 비었거나, null이거나, 예상보다 100배 크면?
- 네트워크·파일·외부 API가 실패하거나 **느리게** 응답하면? (타임아웃은 실패보다 다루기 어렵다)
- 같은 코드가 동시에 두 번 실행되면? 중복 요청이 들어오면?
- 중간에 프로세스가 죽으면 데이터가 **반쯤 쓰인 상태**로 남는가?
- 인코딩·타임존·부동소수점처럼 조용히 어긋나는 것들이 걸려 있는가?

모든 질문에 답할 필요는 없다. 이 작업에 물리는 것만 고르고, 실제로 방어할지 아니면 의도적으로 넘길지를 정한다. **넘기기로 했으면 넘겼다고 남긴다.**

## 실패를 어떻게 알아차리는가

조용히 실패하는 코드가 시끄럽게 실패하는 코드보다 훨씬 위험하다.

- 이게 프로덕션에서 실패하면 **누가, 어떻게** 알게 되는가?
- 예외를 삼키고 있지 않은가? (`except: pass`, 빈 catch 블록)
- 에러 메시지가 원인을 찾는 데 실제로 도움이 되는가? **어떤 값이 문제였는지** 담고 있는가?
- 실패했는데 성공한 것처럼 보이는 경로가 있는가? (부분 성공, 빈 결과 반환)
