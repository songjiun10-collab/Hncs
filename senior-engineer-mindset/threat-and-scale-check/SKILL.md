---
name: threat-and-scale-check
description: Check trust boundaries, scale behavior, and layered safety — 신뢰 경계·규모·다층 방어. Use when handling user input, external API responses, files, or auth; when designing permissions, validation, or any safety mechanism; when data volume could grow; or when writing loops that touch I/O. Also use when reviewing whether a single safeguard is the only thing standing between a mistake and a disaster.
---

# 신뢰 경계 · 규모 · 다층 방어

## 신뢰 경계 — 어디부터가 외부인가

"내가 통제하는 영역"과 "외부"의 선을 그린다.

- 사용자 입력·외부 API 응답·파일 내용을 그대로 신뢰하고 있지 않은가? SQL·셸 명령·파일 경로·HTML에 그대로 꽂히는가?
- 비밀번호·API 키·토큰이 코드·로그·에러 메시지에 노출되지 않는가?
- 권한 확인이 필요한 동작인가? 클라이언트가 보낸 "나는 관리자다"를 믿고 있지 않은가?
- 검증이 **한 지점에만** 있지 않은가? (클라이언트만, 혹은 DB 제약만)

## 규모 — 10배 / 1000배

지금 데이터 100건에서 잘 도는 것은 아무것도 증명하지 않는다.

- 데이터가 10배, 1000배가 되면 이 방식이 여전히 괜찮은가?
- 반복문 안에서 DB 쿼리나 네트워크 호출을 하고 있지 않은가? (N+1)
- 전부 메모리에 올리는가? 스트리밍·배치로 나눌 수 있는가?
- 다만 **측정 없는 최적화는 하지 않는다** — 병목이 실제로 여기인지부터 확인한다

## 다층 방어

완벽한 단일 방어선보다, 하나가 실패해도 다음 겹이 받아주는 구조가 현실적이다.

- 이 안전장치가 실패하면 곧바로 사고인가, 다음 겹이 있는가?
- **무의식적 실수는 막고, 의식적 선택은 허용하되 흔적을 남긴다** — 좋은 안전장치의 형태다. 전부 막으면 우회하게 되고, 전부 열면 사고가 난다
- 성공했을 때도 검증한다. "막혔다"에서 멈추지 말고 **왜** 막혔는지, 다른 상황에서도 재현되는지 확인한다
