# HNCS

*[English README](README.md)*

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

![Before/After - apply_hncs 적용 예시](docs/images/before_after_hncs.jpg)

![HNCS 프리셋 데모 - 사진 한 장에 apply_* 25개 전부 적용](docs/images/preset_demo.jpg)

*동일한 소스 사진(Nikon D5300 야경샷, 데모용으로 제공받음) 한 장에
`brands/*.py`의 `apply_*` 함수 24개(+원본)를 그대로 돌린 결과. 공식
캘리브레이션 소스 사진이 아니라 단순 데모용 - 실제 population 수치의
근거는 [지원 브랜드](#지원-브랜드) 표에 링크된 문서를 참고.*

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

## RAW → Log 색공간 파이프라인 (전문가용)

브랜드별 `apply_*` 엔진과는 목적이 다른 별도 모듈. "이 카메라가 실제로
찍는 JPEG 색을 근사"하는 게 아니라, **카메라 종류에 무관하게** RAW를
표준 중간 색공간(ProPhoto RGB Linear)으로 통일한 뒤 원하는 영상 카메라의
Log 커브/색역(F-Log2, S-Log3, V-Log, ARRI LogC3/4 등)으로 인코딩해서
그 카메라용 크리에이티브 `.cube` LUT를 RAW 사진에도 색 어긋남 없이 적용할
수 있게 한다 ([raw-alchemy](https://github.com/shenmintao/raw-alchemy)에서
아이디어를 참고, `colour-science` 기반으로 재구현).

```
python3 -m tools.raw_pipeline photo.CR3 photo.tiff --log-space S-Log3
python3 -m tools.raw_pipeline photo.ARW photo.tiff --log-space V-Log --lut looks/my_look.cube
python3 -m tools.raw_pipeline photo.NEF photo.tiff --log-space F-Log2 --exposure 1.0
```

![RAW -> Log 색공간 데모 - sRGB 디코드 vs V-Log 인코딩](docs/images/raw_pipeline_demo.jpg)

*동일 RAW(Fujifilm X-T1) 한 장을 표준 sRGB로 디코드한 것(왼쪽)과
`tools.raw_pipeline --log-space V-Log`로 인코딩한 것(오른쪽) 비교. 오른쪽의
밋밋한 저대비/저채도 모습은 정상 - 그레이딩되지 않은 Log 상태 그대로다.*

지원 Log 색공간: `core/log_pipeline.py`의 `LOG_SPACES` 참고(F-Log/F-Log2/
V-Log/N-Log/Canon Log 2·3/S-Log3/S-Log3.Cine/Arri LogC3·4/Log3G10/D-Log).
Log 커브-색역 페어링은 `colour-science`가 제공하는 정의를 그대로 쓴
것으로, 각 제조사 공식 스펙과 전수 대조 검증까지는 안 됐다는 게 이
프로젝트의 다른 "미검증" 항목들과 같은 성격의 caveat.

## 렌즈 왜곡 보정

위의 색감 렌더링 엔진들과 무관한 순수 기하 연산 도구 - [lensfun](https://lensfun.github.io/)에
번들된 카메라+렌즈 프로파일 DB(`lensfunpy` 경유, 카메라 948종/렌즈 1304종,
`pip install -r requirements.txt` 외에 별도 시스템 패키지 불필요)로 배럴/핀쿠션
왜곡을 되돌린다. EXIF(`exiftool`)에서 Make/Model/LensModel/FocalLength/FNumber를
읽어 자동으로 매칭되는 프로파일을 찾고, RAW와 이미 렌더링된 JPEG/TIFF/PNG
입력 둘 다 받는다.

```
python3 -m tools.lens_correction photo.RAF corrected.jpg
python3 -m tools.lens_correction photo.jpg corrected.jpg --lens "XF10-24mmF4 R OIS" --focal-length 10 --aperture 8
```

DB에 카메라/렌즈가 없거나 매칭된 렌즈 프로파일에 왜곡 보정 데이터가 없으면
조용히 원본을 그대로 통과시키지 않고 명확하게 실패한다(`camera_not_found`
/ `lens_not_found` / `no_distortion_data`) - `core/lens_correction.py`의
`correct_from_exif()` 참고. 비네팅/색수차 보정은 지금 범위 밖(`ModifyFlags.DISTORTION`만 적용).

## hybrid_engine/ - EXIF 기반 카메라 간 색감 변환 (V0.1)

리포 루트의 `hybrid_engine/`는 위 두 엔진과도 목적이 다른 세 번째 독립
모듈. "카메라 A로 찍은 완성 JPEG을 카메라 B가 찍은 것처럼 재렌더링"하는
게 목표 - RAW 입력용(`HybridCameraEngine`, Phase 0 색정제 + Gray World
정규화 + LAB 톤/채도 커브)과 JPEG 입력용(`preset_inverse`, EXIF로 소스
브랜드를 인식해서 `brands/*.py`의 population-fit 톤커브를 역산한 뒤
타깃 브랜드의 실제 `apply_*` 함수를 그대로 재적용) 두 경로가 있다.

```
# JPEG만 있는 경우 - EXIF 자동인식
python3 -m hybrid_engine.convert photo.jpg out.jpg --target hasselblad

# RAW가 있는 경우
python3 -m hybrid_engine.main photo.CR3 out.tiff --profile hasselblad
```

![hybrid_engine 데모 - Nikon JPEG을 Hasselblad 룩으로 변환](docs/images/hybrid_engine_demo.jpg)

*Nikon D5300으로 찍은 부다페스트 국회의사당 야경 JPEG(왼쪽, 데모용으로
제공받음 - `docs/images/preset_demo.jpg`/`before_after_hncs.jpg`와 같은
소스 사진)을 `hybrid_engine.convert --target hasselblad`로 변환한
결과(오른쪽) - EXIF로 Nikon을 자동인식해서 그 톤커브를 역산해 근사 중립
상태로 되돌린 뒤 `apply_hncs`를 재적용했다.*

![hybrid_engine 데모 추가 4장 - 성당 내부/국기/거리 사진](docs/images/hybrid_engine_demo_more.jpg)

*같은 여행에서 찍은 추가 사진 4장(전부 데모용으로 제공받음) - 성당 내부
2장은 EXIF가 아예 없어(메신저 전송 과정에서 소실로 추정) `--source
nikon`을 직접 지정했고, 전부 세로 촬영이라 `PIL.ImageOps.exif_transpose()`로
방향을 먼저 바로잡은 뒤 변환했다.*

**알려진 한계** (각 모듈 docstring에도 명시):
- `core/color_matrix.py`: 카메라 고유 색매트릭스로 정규화해도 센서
  분광감도가 CIE 표준관측자와 정확히 비례하지 않아(메타메리즘) 완벽한
  카메라 무관 색공간은 물리적으로 불가능 - 잔차는 ΔE 루프로만 줄일 수 있음
- `core/preset_inverse.py`: population-fit 브랜드의 L채널 톤커브만
  역산 가능(닫힌 형태 역함수 존재) - CLAHE(지각보상 대비)는 적응형
  연산이라 역산 안 함, raw+jpeg 페어가 없는 브랜드(Fuji 등)는 애초에
  이 구조가 아니라서 지원 대상 자체가 아님
- `calibrate_profile.py`가 실제 핫셀블라드 raw+jpeg 페어 13쌍으로
  CIEDE2000 ΔE 루프를 돌린다. 아래 실험 전부 **교차검증 ΔE 기준으로
  판단**했다(in-sample만으로는 안 됨) - 몇몇은 in-sample에서 좋아 보였다가
  교차검증에서 뒤집혔는데, 그 자체가 반복되는 발견이라 표로 같이 남긴다:

  | 실험 | 방법 | in-sample | 교차검증 | 결론 |
  |---|---|---|---|---|
  | v1.1 기준선 | `tone_core`/`color_core` 파라미터 좌표하강 | ΔE00 15.01 | - | 출발점 |
  | 학습 톤 LUT | 1D LUT, 256 bin, L채널 | +4.9% | 미실시(이후부터 CV 필수화) | 기각(기준 미달) |
  | 학습 hue LUT(v1.1) | 1D 순환 LUT, 36 bin | +2.1% | 미실시 | 기각(기준 미달) |
  | 3D 잔차 LUT | L/a/b 결합 격자, 729칸 | +11.1% | **-5.7%** | 기각(순수 과적합) |
  | 2D 잔차 LUT | a/b 결합 격자, 81칸 | +1.4% | -2.7% | 기각 |
  | 공간 연산(v1.1) | 언샤프 마스크 L채널 로컬 콘트라스트 | +0.0% | +2.0%(노이즈) | 기각(무신호) |
  | **raw_baseline 3x3 매트릭스(단독)** | 색차트 없는 전역 최소자승 컬러 매트릭스(이슈 #4) | +42.4% | **+32.6%** | **첫 성공** |
  | 매트릭스 파이프라인 통합(1차) | 매트릭스 + 기존 Phase 0/1/2 | - | +0.0% | 버그: 강제 노출 정규화가 매트릭스 이득을 지움 |
  | 매트릭스 + 톤/채도 재학습(수정 후) | `--mode raw_baseline_pipeline`, nested CV | +34.8% | **+29.7%** | **v1.2로 배포** |
  | hue LUT을 v1.2 기준 재시도 | 같은 1D 순환 LUT, 새 기준선 | +4.6% | +1.4% | 기각(기준 미달) |
  | 공간 연산을 v1.2 기준 재시도 | 같은 로컬 콘트라스트, 새 기준선 | +0.3% | -1.6% | 기각 |
  | robust(percentile) Gray World | 채도 상위 픽셀을 색치우침 추정에서 제외 | +0.0%(최선 후보=미적용) | -3.4% | 기각 - 야경 하늘 과보정을 겨냥했지만 도움 안 됨 |
  | hue별 chroma 배율 LUT | 36-bin 순환, hue 회전 LUT과 별개 축 | **-2.0%** | -4.0% | 기각 - in-sample부터 이미 마이너스인 첫 LUT 실험 |
  | Gray World 완전 제거 | 카메라 자체 WB(`unify_to_d65`)만 사용, 픽셀 기반 추정 없음 | - | **-90.3%**(ΔE00 9.69→18.43) | 강하게 기각 - Gray World가 13쌍 전부에서 필수적인 역할을 하고 있었음 |
  | 밝기 구간별(zoned) Gray World | 밝기 구간마다 독립 추정, 가우시안 블렌딩(2~5구간) | +0.0%(최선=1구간) | +0.0%, 구간이 늘수록 단조 악화, 13-fold 전부 기준선 선택 | 기각 - 이 표본 크기에서는 자유도를 늘리는 게 노이즈만 키움 |

  배포된 v1.2 프로파일은 공식 평가 하네스 기준 ΔE00 15.01 → **9.82**
  (-34.6%, CIE 2000 등급이 "완전히 다른 색"에서 "한눈에 다름"으로
  바뀜). 전체 방법론과 실패→진단→수정 과정, 남은 한계(미드톤 잔차,
  거의 안 바뀐 hue)는 `hybrid_engine/EVALUATION.md`에, 기각된 LUT
  실험들의 상세 기록은 `hybrid_engine/assets/luts/README.md`에 있다.
  픽셀 단위 진단(`EVALUATION.md` 후속 실측 10)으로 남은 최악의 실패
  사례를 구체적인 메커니즘까지 짚었다 - Gray World의 전역 스칼라
  하나로는 야경의 하늘과 가로등이 압도하는 전경을 동시에 만족시킬 수
  없다는 것. 이걸 고치려는 세 가지 다른 시도(위 표) 모두 교차검증에서
  기각돼서, 배포판에 우회 처리를 넣지 않고 문서화된 미해결 한계로
  남겨뒀다.

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
- [x] RAW -> Log 색공간(F-Log2/S-Log3/V-Log 등) + `.cube` LUT 적용
      파이프라인(`tools/raw_pipeline.py`, 브랜드 엔진과 별도)
- [x] EXIF 기반 카메라 간 색감 변환 엔진 V0.1(`hybrid_engine/`, RAW/JPEG
      입력 둘 다 지원, 브랜드 톤커브 역산 + ΔE 평가 루프)

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
재발 방지 가드레일)/`core/lut.py`/`core/denoise.py`/`tools/iso_noise.py`
(패치 그리드 off-by-one 회귀 테스트 포함)/`core/log_pipeline.py`(노출
보정, Log 인코딩, `.cube` LUT 적용, 지원하는 모든 `LOG_SPACES` 검증)/
`hybrid_engine/`(정규화/톤/색/색매트릭스/파이프라인/ΔE 평가/EXIF 브랜드
인식·프리셋 역산 전체, 32개 테스트) 커버.
`.github/workflows/tests.yml`이 push/PR마다 자동으로 이 스위트를 돌린다.

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
