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
  총 834장 + 핫셀블라드 raw+jpeg 페어 캘리브레이션(2026-08 기준 카메라
  4세대 74쌍, 파라메트릭 RMSE 19.94 - [docs/measurements.md](docs/measurements.md#로컬-기여-데이터셋으로-세대-간-pooling-첫-실측-2026-08-local-mixed-2026-07)
  참고)
- 픽셀 단위 **5종 시그니처 분석**(tone/color/texture/gamut/joint
  distribution)으로 브랜드별 색과학을 데이터로 기록
- **population 통계 재현성 감사 10/10 일치** - 커밋된 모든 수치가
  캐시 이미지로 처음부터 재계산해도 그대로 나옴을 확인함(2026-07)
- `unittest` 테스트 스위트 + GitHub Actions CI로 push/PR마다 자동 검증

## 어디부터 읽을까

처음이라면 이 순서로: 이 README -> [docs/project_structure.md](docs/project_structure.md)로
파일 단위 지도 확인 -> 건드릴 영역의 `README.md`(사용법/예시)와
`CLAUDE.md`(기여 규칙) - [brands/README.ko.md](brands/README.ko.md),
[tools/README.ko.md](tools/README.ko.md),
[hybrid_engine/README.ko.md](hybrid_engine/README.ko.md),
[gui/README.ko.md](gui/README.ko.md), [tests/README.ko.md](tests/README.ko.md).
전체 디렉토리 지도 + "무엇을 하려면 어디를 읽어야 하는지" 표는
[docs/START_HERE.md](docs/START_HERE.md) 참고.

![Before/After - apply_hncs 적용 예시](docs/images/before_after_hncs.jpg)

*`apply_hncs`(Hasselblad 룩)를 Fuji GFX50S II로 찍은 서울 횡단보도
스냅샷(`DSCF9447.RAF`, 이 세션 Classic Chrome/Nostalgic Neg 캘리브레이션에
쓰인 것과 같은 raw+jpeg 라이브러리)에 적용한 결과. 사진 속 인물은
뒷모습/옆모습만 나와 특정할 수 없음.*

![HNCS 프리셋 데모 - 사진 한 장에 apply_* 44개(+원본) 전부 적용](docs/images/preset_demo.jpg)

*동일한 소스 사진(Fuji GFX50S II로 찍은 서울 이태원 거리 스냅샷,
`DSCF9556.RAF` - Classic Chrome/Nostalgic Neg 등 이 세션 캘리브레이션에
쓰인 것과 같은 raw+jpeg 라이브러리에서 고른 실제 사진, 특정 인물 클로즈업이
아니라 일반 거리 스냅샷) 한 장에 `brands/*.py`의 사진용 `apply_*` 룩
44개(+원본)를 그대로 돌린 결과. `tools/build_readme_demo.py`로 생성 -
새 룩이 추가될 때마다 재실행하면 됨.*

## 지원 브랜드

**12개 브랜드**: Hasselblad, Fujifilm, Leica, Phase One, Pentax, Ricoh
GR, Canon, Nikon, Sony, Panasonic, Olympus, Sigma. 검증 방식 표 전체,
브랜드별 근거 링크, 공통 한계, 빠른 예시 코드는
[brands/README.ko.md](brands/README.ko.md)에 있다.

## 설치

```
pip install -r requirements.txt
```

`.claude/settings.json`은 이 리포에서 Claude Code로 분석 스크립트를 돌릴 때
`cdn.hasselblad.com`, `live.staticflickr.com` 등으로의 네트워크 접근을
자동 허용하는 샌드박스 설정입니다.

## 그 외 모듈

브랜드별 `apply_*` 함수 말고도 각자 `README.md`를 가진 엔진 3개가 더
있다:

- [tools/README.ko.md](tools/README.ko.md) - RAW → Log 색공간 파이프라인
  (`raw_pipeline.py`), 렌즈 왜곡 보정, Photoshop/DaVinci용 `.cube` LUT
  내보내기, DCP 카메라 프로필 내보내기(X2D II), 브랜드 시그니처
  판별력 검증, 프레임 단위 비디오 엔진, 그리고 이 프로젝트의 모든
  실측을 재현/재검증하는 명령어
- [hybrid_engine/README.ko.md](hybrid_engine/README.ko.md) - EXIF 기반
  카메라 간 색감 변환(V0.1): 카메라 A로 찍은 JPEG/RAW를 카메라 B가
  찍은 것처럼 재렌더링, raw 기준선 캘리브레이션 실험 전체 기록 포함
- [gui/README.ko.md](gui/README.ko.md) - 위 전부를 클릭 몇 번으로 쓸 수 있게
  묶은 Tkinter 데스크톱 앱

[`docs/demo/hncs_convert_demo.html`](docs/demo/hncs_convert_demo.html)은
별도의 독립형 브라우저 데모 페이지다 - **브랜드별 파라미터는 시각적
효과를 위해 임의로 만든 값이며 이 저장소의 실측 데이터에서 나온 게
아니다**, 페이지 상단에 명시돼 있다. 빌드 없이 파일을 바로 열면 된다.

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
- [x] 후지필름 필름시뮬레이션 프리셋 13종
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
brands/       브랜드별 색감 근사 함수 (apply_*) - README.md, CLAUDE.md
core/         브랜드 전체가 공유하는 톤커브/LUT/통계/검증 헬퍼
datasets/     커밋된 참조 CSV (공식 샘플 메타데이터, 스크레이핑한 갤러리 링크) - CLAUDE.md
tools/        분석/다운로드/캘리브레이션 스크립트, RAW→Log, 렌즈 보정, DCP/LUT 내보내기 - README.md, CLAUDE.md
hybrid_engine/ 카메라 간 색감 변환 + 캘리브레이션 머신러리 - README.md, CLAUDE.md
gui/          Tkinter 데스크톱 앱 - README.md, CLAUDE.md
tests/        unittest 테스트 스위트 - README.md, CLAUDE.md
models/       얼굴 검출 등에 쓰는 사전학습 모델
docs/         상세 문서 (방법론/실측 결론/브랜드별 기록/파일별 설명) - CLAUDE.md
```

각 영역의 `README.md`(있는 경우)는 사용법/예시를, `CLAUDE.md`는 그
영역을 바꿀 때의 규칙을 다룬다. 파일별 상세 설명은
[docs/project_structure.md](docs/project_structure.md) 참고.

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
- [docs/hncs_structural_research.md](docs/hncs_structural_research.md) -
  HNCS 실제 4단계 구조 vs `apply_hncs()`의 3단계 단순화 비교(연구용),
  표본 크기별(13 -> 94 -> 364쌍) leave-one-out ΔE 실험 - 364쌍 결과는
  통계적으로 유의하며 `apply_hncs()`의 단순화가 이긴다는 결론을 확정함
- [docs/hncs_external_sources_analysis.md](docs/hncs_external_sources_analysis.md) -
  HNCS 실제 동작 방식에 대한 외부 문서 17건(핫셀블라드 관련 블로그 +
  포럼 스레드) 분석, 위 구조 실험들과 교차 대조

## 기여

이슈나 PR은 언제든 환영. 이 프로젝트는 "실측 데이터 없이 파라미터를
바꾸지 않는다"는 원칙이 있으니, 브랜드 파라미터를 조정하는 PR이라면
근거가 된 population 수치나 비교 방법을 함께 설명해주면 리뷰가 빠르다.

## 감사의 말

GitHub 사용자 **kmichels** (Reddit: Big_Rip4015) 님께 감사드립니다.
프로젝트를 꼼꼼히 읽고 방법론 관련 피드백과 함께
[이슈 #4](https://github.com/songjiun10-collab/Hncs/issues/4)를
제보해주셨고, 그 피드백이 실제 버그 수정(편집된 사진을 필터에 넣었던
문제)과 raw 베이스라인의 정확한 특성화로 이어졌습니다. 이후에는 직접
핫셀블라드 X2D II 100C로 ColorChecker Classic을 10장 촬영해서
제공해주셨고, 이 데이터 덕분에 `hybrid_engine/EVALUATION.md`의
차트 기반 raw 베이스라인 특성화가 가능했습니다. 진짜 외부 리뷰와 진짜
데이터, 그 공로를 정확히 기록합니다.

Chris Schmauch 님께도 감사드립니다. DCP 카메라 프로필 내보내기
(`core/dcp_export.py`)를 실제 Lightroom에서 직접 테스트해서 안 뜨는
원인을 헤더 매직 넘버와 `UniqueCameraModel` 값까지 정확히 짚어주셨습니다
- [tools/README.ko.md](tools/README.ko.md#dcp-카메라-프로필-색채측정-보정-x2d-ii-전용)
참고.

## 라이선스

[MIT](LICENSE)
