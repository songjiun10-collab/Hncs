---
name: search-first
description: Check current documentation and prior art before writing code against any external API, library, or framework — 코딩 전에 최신 문서부터. Use whenever the task touches a third-party library, SDK, API, CLI flag, config format, or language/framework version behavior. Especially when writing code from memory about how something works, when a version number is involved, or when an API "should" work a certain way but hasn't been verified.
---

# 검색 우선

훈련 데이터에 있는 API 지식은 **낡았다고 가정한다.** 라이브러리는 시그니처를 바꾸고, 플래그는 사라지고, 권장 방식은 뒤집힌다. 기억에서 꺼낸 코드는 그럴듯하게 틀리기 때문에 가장 발견하기 어렵다.

## 언제 반드시 확인하는가

- 외부 라이브러리·SDK·API를 호출하는 코드를 쓸 때
- CLI 플래그, 설정 파일 형식, 환경 변수 이름을 쓸 때
- 버전 번호가 걸린 동작 ("3.11부터", "v5에서는")
- "이렇게 하면 될 것이다"라고 생각했는데 **확인한 적은 없을** 때
- 에러 메시지가 문서와 다르게 나올 때 — 대개 문서가 아니라 내 기억이 낡은 것이다

## 확인 순서

1. **공식 문서·릴리스 노트** — 1차 출처. 블로그·Stack Overflow는 그다음
2. **설치된 실제 버전** — `package.json`, `requirements.txt`, lockfile을 본다. 최신 문서를 봐도 우리가 쓰는 버전이 아니면 소용없다
3. **코드베이스의 기존 사용례** — 같은 라이브러리를 이미 쓰고 있다면 그 방식이 이 프로젝트의 정답이다
4. **필요하면 실제로 실행해본다** — REPL 한 줄이 추측 열 줄보다 싸다

## 비용 감각

확인 비용이 **잘못 짚었을 때의 비용보다 싸면** 확인한다. 대개 훨씬 싸다. 반대로 널리 알려진 표준 라이브러리의 안정적인 API까지 매번 찾아보면 그건 낭비다.

찾아본 결과가 기억과 달랐다면 **그 사실을 남긴다** — 다음 사람도 같은 착각을 한다.
