# brands/

*[English README](README.md)*

브랜드별 색감 근사 함수(`apply_*`) - 실제 배포되는 결과물. 이 디렉토리
수정 규칙은 `CLAUDE.md`를 참고.

## 지원 브랜드

| 브랜드 | 검증 방식 | 상세 |
|---|---|---|
| ✅ 핫셀블라드 | raw+jpeg 페어 캘리브레이션(그리드서치 + 학습 LUT) | [docs/measurements.md](../docs/measurements.md) |
| ✅ 후지필름 | 필름 시뮬레이션 프리셋 11종, population + 동일장면 비교차트 + raw+jpeg(Provia) | [docs/brands.md](../docs/brands.md#fujifilm-brandsfujipy) |
| ✅ 라이카 | population-fit(SOOC JPEG 45장) | [docs/brands.md](../docs/brands.md#leica-brandsleicapy) |
| ✅ 페이즈원 | population-fit(Capture One 기본 렌더링) | [docs/brands.md](../docs/brands.md#phase-one-brandsphaseonepy) |
| ✅ 펜탁스 | population-fit(645Z + K-1, 40장) | [docs/brands.md](../docs/brands.md#pentax-brandspentaxpy) |
| ✅ 리코 GR | population-fit(GR III/IIIx/II) | [docs/brands.md](../docs/brands.md#ricoh-gr-brandsricoh_grpy) |
| ✅ 캐논 | population-fit(EOS R5/R6/R8/R3/R, n=115) | `canon.py` 독스트링 |
| ✅ 니콘 | population-fit(Z6/Z6 II/D780, n=69) | `nikon.py` 독스트링 |
| ✅ 소니 | population-fit(A7/A7R/A7S/A7 III/A7 IV, n=115) | `sony.py` 독스트링 |
| ✅ 파나소닉 | population-fit(GH5/GH6/G9/S5/S1, n=120) | `panasonic.py` 독스트링 |
| ✅ 올림푸스 | population-fit(OM-1/OM-5/E-M1 III/E-M1X/PEN-F, n=122) | `olympus.py` 독스트링 |
| ✅ 시그마 | population-fit(Bayer + Foveon, 5바디, n=83) | `sigma.py` 독스트링 |

population-fit 방식이 공통으로 가진 한계(raw 베이스라인 없음, shoulder_start/
clahe_clip 같은 일부 파라미터는 핫셀블라드 값을 빌려와 미검증 상태)는
[docs/brands.md](../docs/brands.md)와 이 디렉토리의 각 `*.py` 독스트링에
자세히 기록돼있다.

## 간단 예시

```python
import cv2
from brands.hasselblad import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

여기 있는 모든 `apply_*` 함수는 예외 없이 BGR `np.ndarray`를 받아 같은
shape의 `np.ndarray`를 반환한다. 흑백 필름 시뮬레이션 2종(`apply_acros`,
`apply_monochrome`)만 3채널 BGR이 아니라 단일 채널 2D 배열을
반환한다 - 의도된 동작이며 `tests/test_brands.py`가 이를 고정한다.
`core`/`brands`/`tools` import 경로가 제대로 풀리도록 저장소 루트에서
실행할 것.
