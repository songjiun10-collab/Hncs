# HNCS

*[English README](README.en.md)*

[![tests](https://github.com/songjiun10-collab/Hncs/actions/workflows/tests.yml/badge.svg)](https://github.com/songjiun10-collab/Hncs/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

카메라/디지털백 제조사별 공식(또는 공식에 준하는) 샘플 이미지를 실측
분석해서 각 브랜드의 색과학을 코드로 근사하는 프로젝트. 원래 핫셀블라드
HNCS(Hasselblad Natural Colour Solution) 하나만 다뤘는데, 같은 방법론을
11개 브랜드로 확장했다.

## TL;DR

- **12개 브랜드** 색감 근사: Hasselblad/Fujifilm/Leica/Phase One/Pentax/
  Ricoh GR/Canon/Nikon/Sony/Panasonic/Olympus/Sigma
- 전부 **공식 샘플 이미지 실측**에 근거 - population-fit 10개 브랜드
  총 834장 + 핫셀블라드 raw+jpeg 페어 캘리브레이션(124장, RMSE 15.4)
- 픽셀 단위 **5종 시그니처 분석**(tone/color/texture/gamut/joint
  distribution)으로 브랜드별 색과학을 데이터로 기록
- **population 통계 재현성 감사 10/10 일치** - 커밋된 모든 수치가
  캐시 이미지로 처음부터 재계산해도 그대로 나옴을 확인함(2026-07)
- `unittest` 테스트 스위트 + GitHub Actions CI로 push/PR마다 자동 검증

## 지원 브랜드

| 브랜드 | 검증 방식 | 근거 |
|---|---|---|
| ✅ Hasselblad | raw+jpeg 페어 캘리브레이션(그리드서치 + 학습 LUT) | [docs/measurements.md](docs/measurements.md) |
| ✅ Fujifilm | 필름시뮬레이션 프리셋 10종, population + 동일장면 비교차트 | [docs/brands.md](docs/brands.md#후지필름-brandsfujipy) |
| ✅ Leica | population-fit (SOOC JPEG 45장) | [docs/brands.md](docs/brands.md#라이카-brandsleicapy) |
| ✅ Phase One | population-fit (Capture One 렌더링 기준) | [docs/brands.md](docs/brands.md#phase-one-brandsphaseonepy) |
| ✅ Pentax | population-fit (645Z + K-1, 40장) | [docs/brands.md](docs/brands.md#pentax-brandspentaxpy) |
| ✅ Ricoh GR | population-fit (GR III/IIIx/II) | [docs/brands.md](docs/brands.md#ricoh-gr-brandsricoh_grpy) |
| ✅ Canon | population-fit (EOS R5/R6/R8/R3/R, n=115) | `brands/canon.py` docstring |
| ✅ Nikon | population-fit (Z6/Z6 II/D780, n=69) | `brands/nikon.py` docstring |
| ✅ Sony | population-fit (A7/A7R/A7S/A7 III/A7 IV, n=115) | `brands/sony.py` docstring |
| ✅ Panasonic | population-fit (GH5/GH6/G9/S5/S1, n=120) | `brands/panasonic.py` docstring |
| ✅ Olympus | population-fit (OM-1/OM-5/E-M1 III/E-M1X/PEN-F, n=122) | `brands/olympus.py` docstring |
| ✅ Sigma | population-fit (Bayer + Foveon 5바디, n=83) | `brands/sigma.py` docstring |

population-fit 방식의 공통 한계(raw 기준선 없음, shoulder_start/
clahe_clip 등 일부 파라미터 핫셀블라드 값 차용·미검증)는
[docs/brands.md](docs/brands.md)와 각 `brands/*.py` docstring에 상세히
기록돼 있다.

## 빠른 예시

```python
import cv2
from brands.hasselblad import apply_hncs

img = cv2.imread("photo.jpg")
result = apply_hncs(img)
cv2.imwrite("photo_hncs.jpg", result)
```

`brands/*.py`의 각 `apply_*` 함수는 전부 동일하게 BGR `np.ndarray`를
받아 BGR `np.ndarray`를 반환한다. 리포 루트에서 실행해야 `core`/`brands`/
`tools` 임포트 경로가 맞다.

## 설치

```
pip install -r requirements.txt
```

`.claude/settings.json`은 이 리포에서 Claude Code로 분석 스크립트를 돌릴 때
`cdn.hasselblad.com`, `live.staticflickr.com` 등으로의 네트워크 접근을
자동 허용하는 샌드박스 설정입니다.

## 목표 / 철학

- 주관적인 "필감" 묘사가 아니라 population 통계, raw+jpeg 페어,
  동일장면 비교차트 같은 **실측 데이터**에 근거해서 파라미터를 정한다
- 검증 안 된 값은 숨기지 않고 **"미검증"이라고 코드·문서에 명시**한다
  (예: 일부 브랜드의 `shoulder_start`/`clahe_clip`은 핫셀블라드 값을
  검증 없이 차용했다고 docstring에 그대로 적음)
- **재현성**: 커밋된 population 수치는 캐시 이미지로 처음부터 다시
  계산해도 같은 값이 나와야 하고, 정기적으로 감사한다
- 표본이 작을 땐 RMSE가 더 낮아지더라도 **과적합보다 보수적인 선택**을
  우선한다(그리드서치로 더 나은 수치가 나와도 표본 부족을 이유로
  보류한 사례가 여러 브랜드에 기록돼 있음)
- 실패한 시도(raw 페어를 못 구함, 표본 오염, 사이트 차단 등)도 지우지
  않고 그대로 문서화한다

## 기능

- [x] 핫셀블라드 RAW 기반 파라메트릭/학습 캘리브레이션(`apply_hncs`,
      `apply_hncs_learned`)
- [x] 후지필름 필름시뮬레이션 프리셋 10종
- [x] 10개 브랜드 population-fit 색감 근사 엔진(`core/engine.py`)
- [x] 픽셀 단위 5종 시그니처 분석(tone/color/texture/gamut/
      joint_distribution)
- [x] 이미지 무결성 검증 파이프라인(`core/validation.py`, CDN 손상
      자동 필터링)
- [x] `unittest` 기반 자동 테스트 스위트
- [x] GitHub Actions CI(push/PR마다 자동 실행)
- [x] population 통계 재현성 감사 도구

## 구조

```
brands/       브랜드별 색감 근사 함수 (apply_*)
core/         브랜드 전체가 공유하는 톤커브/LUT/통계/검증 헬퍼
datasets/     커밋된 참조 CSV (공식 샘플 메타데이터, 스크레이핑한 갤러리 링크)
tools/        분석(analyze)/다운로드(download)/캘리브레이션(calibrate) 스크립트
models/       얼굴 검출 등에 쓰는 사전학습 모델
docs/         상세 문서 (방법론/실측 결론/브랜드별 기록/파일별 설명)
```

파일별 상세 설명은 [docs/project_structure.md](docs/project_structure.md)
참고.

## 테스트

`tests/` 아래 `unittest` 기반 테스트가 있다(pytest 등 외부 의존성 추가
없이 `requirements.txt` 최소 의존성 원칙 유지). `core/curve.py`(톤커브
수학, 경계조건/단조성/연속성)/`core/stats.py`(population 통계 계산)/
`core/validation.py`(무결성 검증, CDN 손상 패턴 재현)/`core/engine.py`
(population-fit 엔진)/`brands/*.py`(모든 `apply_*` 룩 함수의 shape/dtype
보존, 후지 프리셋 개수 일치)/`tools/fuji_chart_calibrate.py`(크롭박스
추출, delta 집계)/`tools/download.py`(imaging-resource.com HTML 파싱·
필터링·Google Drive URL 분류 - 네트워크 호출은 mock 처리)/
`datasets/*/texture_signature.json` 전체(sharpening/micro_contrast/noise가
브랜드 간 합리적 범위 안에 있는지 - Sony 스케일버그 같은 자릿수 오류
재발 방지 가드레일) 커버. `.github/workflows/tests.yml`이 push/PR마다
자동으로 이 스위트를 돌린다.

```
python3 -m unittest discover -s tests -v
```

## 실측 재현/재검증

```
python3 -m tools.analyze hasselblad       # 핫셀블라드 공식 샘플 전체 population 통계
python3 -m tools.analyze portrait         # 인물 서브셋 + 피부톤 hue 불변성 검증
python3 -m tools.analyze leica            # 라이카 imaging-resource.com population
python3 -m tools.analyze phaseone         # Phase One 〃
python3 -m tools.analyze pentax           # Pentax 〃
python3 -m tools.analyze ricoh_gr         # Ricoh GR 〃
python3 -m tools.analyze fuji_film_modes  # 후지 Film Mode별 population + 프리셋 방향 검증

python3 -m tools.download fuji-links      # 후지 RAW/JPEG Google Drive 링크 수집
python3 -m tools.download fuji-pairs      # 위 링크에서 RAW+JPEG 페어 다운로드 (gdown 필요)

python3 -m tools.calibrate grid_search    # 핫셀블라드 raw 기반 진짜 전/후 그리드서치 (rawpy 필요, 대용량 다운로드)
python3 -m tools.calibrate learn_curve    # raw+jpeg 픽셀 대응으로 톤커브 직접 학습 (rawpy 필요)
python3 -m tools.calibrate regularize     # 학습 LUT 정규화 + leave-one-out 교차검증
```

## 더 읽을거리

README는 훑어보는 용도로 짧게 유지하고, 자세한 실측 기록은 `docs/`에
따로 뒀다.

- [docs/methodology.md](docs/methodology.md) - 이미지 신뢰성 정책, 브랜드
  함수 QA 검증, population 통계 재현성 감사
- [docs/measurements.md](docs/measurements.md) - 핫셀블라드 실측 결론
  전체 기록(v8~v12, day/night 히스토리)
- [docs/brands.md](docs/brands.md) - 후지필름/라이카/Phase One/Pentax/
  Ricoh GR 브랜드별 상세 방법론
- [docs/project_structure.md](docs/project_structure.md) - 파일별 역할
  전체 목록

## 기여

이슈나 PR은 언제든 환영. 이 프로젝트는 "실측 데이터 없이 파라미터를
바꾸지 않는다"는 원칙이 있으니, 브랜드 파라미터를 조정하는 PR이라면
근거가 된 population 수치나 비교 방법을 함께 설명해주면 리뷰가 빠르다.

## 라이선스

[MIT](LICENSE)
