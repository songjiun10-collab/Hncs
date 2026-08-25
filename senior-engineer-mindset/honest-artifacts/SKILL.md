---
name: honest-artifacts
description: Make outputs honest and re-derivable — 미검증 라벨·재현 가능성·지표의 함정. Use when committing constants, thresholds, or tuned parameters; when reporting a number or a benchmark result; when a result came from a manual one-off process; or when optimizing against a metric. Also use when tempted to present an estimate as if it were verified.
---

# 정직한 산출물

## 아는 것과 추정한 것을 구분한다

가장 위험한 코드는 틀린 코드가 아니라 **어디까지가 검증된 것인지 알 수 없는 코드**다. 검증된 값과 대충 넣은 값이 나란히 있으면 다음 사람은 둘 다 믿거나 둘 다 의심한다.

- 이 상수·파라미터·기본값은 근거가 있는가, "일단 이 정도면 되겠지"인가?
- 근거가 없다면 그 사실을 **코드나 문서에 명시적으로** 남겼는가? (`# 미검증: X에서 가져온 값, 독립 검증 안 됨`)
- 추정치를 확신하는 것처럼 쓰지 않았는가?
- 잘 안 됐던 시도도 기록으로 남기면 다음 사람이 같은 벽에 다시 부딪히지 않는다. **실패는 숨길 대상이 아니라 데이터다**

## 재현 가능성

"동작한다"와 "다시 만들 수 있다"는 다르다. 한 번의 수동 작업으로 나온 결과는 그 사람이 사라지는 순간 블랙박스다.

- 이 결과물(수치·데이터·산출물)을 백지에서 다시 만드는 절차가 있는가?
- 그 절차가 **명령어 한 줄**로 실행되는가, 머릿속에만 있는가?
- 지금 커밋하는 숫자가 6개월 뒤 같은 입력에서 같은 값으로 나오는가? (랜덤 시드, 외부 데이터 변동, 버전 차이)

## 지표의 함정

점수를 최적화하다 보면 점수만 좋아지고 실제 목적은 멀어진다.

- 이 개선이 **측정 대상**을 좋게 만들었는가, **측정 방식**에 맞췄는가? (과적합)
- 표본·사례가 충분한가? 부족하면 점수가 더 좋은 복잡한 안보다 **보수적인 안**이 낫다
- 이 지표가 좋아지면서 대신 나빠진 게 없는가? (속도↑ 정확도↓ 같은 숨은 교환)
- **"좋아졌다"는 결과가 아니다.** 숫자를 댄다
