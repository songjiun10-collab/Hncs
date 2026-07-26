# 비디오 파일에 brand look 적용 (video engine)

## 배경 / 문제

지금까지 이 프로젝트의 모든 엔진(`brands/*.py`, `hybrid_engine/`,
`core/log_pipeline.py`)은 정지 이미지(RAW 또는 JPEG) 한 장을 입력으로
받는다. `brands/*.py`의 `apply_*_look(img_bgr)` 12개는 이미 각 브랜드의
population-fit 측정을 마쳤지만, 실제 비디오 파일(mp4/mov 같은 컨테이너)에
프레임 단위로 적용해서 "이 브랜드처럼 보이는 영상"을 만드는 경로가 없다.

이 스펙은 새 색과학 측정을 하지 않는다 - 이미 측정된 12개 브랜드의
`apply_*_look()`을 비디오 프레임 시퀀스에 반복 적용하는 **순수 엔지니어링
작업**이다.

## 환경 제약 (설계 단계에서 확인)

- `ffmpeg` CLI, `moviepy`, `imageio_ffmpeg`, `av` 파이썬 패키지 전부 이
  개발 환경에 없다.
- OpenCV(5.0.0)는 FFmpeg를 내장 빌드했다(`cv2.getBuildInformation()`의
  `Video I/O: FFMPEG: YES`) - `cv2.VideoCapture`/`cv2.VideoWriter`로
  비디오 읽기/쓰기 자체는 외부 의존성 추가 없이 가능하다.
- 오디오 트랙을 읽거나 다시 mux할 도구가 없다 - **v1은 무음 비디오만
  지원**한다(입력에 오디오가 있어도 버려짐, 문서화된 한계).
- 레포에 테스트용 샘플 비디오 파일이 없다 - 유닛 테스트는 합성 프레임(예:
  그라디언트 + 색 패치)으로 만든 짧은 비디오로 진행한다.

## 목표

1. 비디오 파일을 읽어 매 프레임에 선택된 브랜드의 `apply_*_look()`을
   적용하고, 같은 해상도/프레임레이트로 새 비디오 파일을 쓰는 CLI를
   만든다.
2. 프레임 단위 적응형 처리(CLAHE)가 비디오에서 일으키는 깜빡임(flicker)을
   피하도록 파이프라인을 조정한다.
3. 오디오 미보존, 사진 모드와의 처리 차이(CLAHE 생략) 등 한계를 명시적으로
   문서화한다.

## 브랜드 범위: 10개 (12개 전부가 아님)

`brands/*.py`를 조사한 결과 CLAHE 사용 방식이 브랜드마다 균일하지 않다:

- **Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/
  Sigma/Sony (10개)**: 전부 `core.engine.apply_population_fit_look()`
  하나를 그대로 호출한다 - CLAHE 호출 지점이 단 하나라 "비디오 모드에서
  이 지점만 생략"이 명확하고 일관되게 적용된다.
- **Fujifilm**: `apply_astia`/`apply_provia`/`apply_pro_neg_hi` 등 10개
  프리셋이 각자 다른 함수이고, CLAHE를 쓰는 프리셋과 안 쓰는 프리셋이
  섞여 있다(예: `apply_pro_neg_hi`는 자체 CLAHE 호출을 갖고 있음) -
  프리셋마다 개별적으로 비디오 변형을 설계/검증해야 해서 이번 스펙 하나로
  묶을 수 없다.
- **Hasselblad(`apply_hncs`)**: `apply_population_fit_look()`을 쓰지
  않는 별도 파이프라인이면서 자체 `cv2.createCLAHE` 호출을 갖고
  있다(`exposure_gamma` 등 population-fit 브랜드에 없는 파라미터도
  있음) - 같은 종류의 플리커 위험이 있지만 별도 분석이 필요하다.

**v1은 위 10개 population-fit 브랜드만 지원한다.** Fujifilm/Hasselblad(및
`hasselblad_day`/`hasselblad_night`/`hasselblad_learned`)는 범위 밖으로
명시하고, `--brand`에 이 10개 외의 이름을 주면 에러로 거부한다.

## 범위 밖

- **Fujifilm/Hasselblad 계열 비디오 지원** - 위 "브랜드 범위" 참고, 각자
  다른 파이프라인이라 개별 스펙이 필요하다.
- **오디오 트랙 보존/재인코딩** - mux 도구 부재로 v1 범위 밖. 필요해지면
  별도 스펙(예: `ffmpeg` 의존성 추가 여부부터 재논의).
- **시네마 카메라 브랜드(ARRI/RED 등) 추가** - 이건 새 population-fit
  브랜드 작업이고, 이 스펙은 기존 브랜드의 재사용만 다룬다.
- **실시간/스트리밍 처리** - 파일 입력 → 파일 출력의 배치 변환만 다룬다.
- **가변 프레임레이트, 회전 메타데이터, HDR 등 컨테이너 메타데이터 보존** -
  `cv2.VideoCapture`/`VideoWriter`가 기본 제공하는 것 이상은 다루지 않는다.
- **GPU 가속/실사용 성능 튜닝** - 정확성/올바름을 먼저 확보하고, 속도는
  이번 스펙에서 최적화 대상이 아니다.

## 설계

### 왜 CLAHE를 비디오 모드에서 생략하는가

`core/engine.py`의 `apply_population_fit_look()`은 다음 순서로 동작한다:

```python
clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
l = clahe.apply(l)          # 1) 프레임 데이터에 의존하는 로컬 대비 보정
...
l = cv2.LUT(l, lut)          # 2) 프레임 데이터에 독립적인 톤 커브(고정 LUT)
```

CLAHE는 각 8x8 타일의 로컬 히스토그램을 프레임마다 새로 계산한다. 인접
프레임이 시각적으로 거의 같아도 미세한 노이즈/모션 차이로 타일 히스토그램이
프레임마다 달라지고, 이게 출력 밝기/대비의 프레임 간 떨림(flicker)으로
드러난다 - 사진 한 장에서는 문제되지 않지만 비디오에서는 눈에 띄는 결함이다.

**확인된 사항**: `clahe_clip`을 인자로 낮춰서(예: `1e-6`) 사실상 CLAHE를
끄는 시도는 안 통한다 - 설계 단계에서 실측(무작위 64x64 이미지,
`clipLimit` 1.25/0.01/0.001/1e-6 비교) 결과 출력이 입력과 갖는 평균
절대 차이가 `clipLimit` 값과 무관하게 거의 동일했다(전부 ~6.34) - 즉
OpenCV의 CLAHE는 `clipLimit`이 0에 가까워져도 항등변환으로 수렴하지
않고 타일별 히스토그램 균등화 자체는 항상 수행한다. 그래서 "낮은
clip으로 우회"가 아니라 `clahe.apply()` 호출 자체를 건너뛰는 별도
코드 경로가 필요하다.

반면 `film_curve()` 기반 톤 LUT는 `toe_lift`/`shoulder_start`/
`white_point` 같은 브랜드 고정 파라미터로만 계산되고 프레임 내용과
무관하다 - 프레임마다 동일하게 적용되어 시간적으로 안정적이다.

**결정**: 비디오 모드에서는 CLAHE 단계를 건너뛰고 톤 LUT만 적용한다. 이건
"비디오 전용 룩 근사"이며 사진 모드의 `apply_*_look()`과 완전히 동일한
출력이 아니다 - 이 차이를 코드 주석과 문서에 명시한다.

`core/engine.py`의 `apply_population_fit_look()` 자체나 각
`brands/*.py`는 수정하지 않는다(사진 경로는 그대로 유지) - 새 함수
`apply_population_fit_look_video_frame(img_bgr, toe_lift, shoulder_start,
white_point)`를 `core/engine.py`에 추가한다. 시그니처는
`apply_population_fit_look()`에서 `clahe_clip` 인자만 뺀 형태(CLAHE를
아예 안 쓰므로)이고, 내부적으로 CLAHE 단계를 생략한 채 톤 LUT만 적용한다.

`tools/video_engine.py`가 브랜드별 `toe_lift`/`shoulder_start`/
`white_point` 값을 얻는 방법: 각 `brands/*.py`의 상수는
`_TOE_LIFT`처럼 밑줄 접두사(비공개 관례)라 다른 모듈에서 직접 import하지
않는다. 대신 `inspect.signature(apply_canon_look).parameters['toe_lift']
.default`처럼 이미 공개된 `apply_*_look()` 함수의 기본값을
`inspect`로 읽어온다 - 각 브랜드 모듈이 이미
`def apply_X_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START,
white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP)` 형태로 이 값들을
기본 인자에 그대로 노출하고 있음을 이용한다(10개 브랜드 전부 동일 패턴,
`brands/sigma.py` 확인됨). 브랜드 이름 → 함수 매핑은
`tools/video_engine.py` 안에 10개 항목짜리 딕셔너리로 명시한다.

### 모듈 구조

`tools/video_engine.py` - CLI 진입점, `hybrid_engine/main.py`와 동일한
패턴(입력 경로, 출력 경로, 옵션 인자):

```
python3 -m tools.video_engine input.mp4 output.mp4 --brand fuji
```

핵심 흐름:
1. `cv2.VideoCapture(input_path)`로 열고 실패 시 명확한 에러
2. 원본의 `fps`/`frame_width`/`frame_height`/총 프레임 수를 읽음
3. `cv2.VideoWriter(output_path, fourcc, fps, (width, height))`로 출력 준비
   (fourcc는 `mp4v` - OpenCV 내장 FFmpeg로 무난하게 쓰기 가능한 코덱)
4. 매 프레임을 읽어 `--brand`로 선택된 `apply_*_look_video_frame()`류
   함수를 적용하고 씀
5. 진행률 로그(예: 100프레임마다 stderr에 출력) - 긴 비디오에서 진행 확인용

**브랜드 선택은 EXIF 자동 감지를 하지 않는다** - 비디오 컨테이너
메타데이터에서 카메라 기종을 신뢰성 있게 뽑아낼 표준 경로가 없고,
`hybrid_engine.main`의 자동 감지는 정지 RAW의 EXIF에 의존하는데 이건
비디오에 그대로 적용할 근거가 없다. `--brand` 필수 인자로 명시적으로
받는다.

### 에러 처리

- 존재하지 않는 브랜드 이름 → 즉시 에러, 유효한 브랜드 목록 출력
- 입력 파일을 열 수 없음(`cv2.VideoCapture.isOpened() == False`) → 명확한
  에러 메시지로 중단
- 출력 파일 쓰기 실패 → 에러로 중단(부분적으로 쓰인 파일은 정리하지 않음 -
  실패 원인 진단이 우선이라는 기존 프로젝트 관례를 따름)

### 테스트

RAW 파일도 실제 비디오 샘플도 이 환경에 없으므로, 합성 데이터로 검증한다:

1. `tests/test_video_engine.py`에서 `cv2.VideoWriter`로 짧은 합성
   비디오(예: 10프레임, 64x48, 그라디언트+색 패치가 프레임마다 살짝
   달라지는 패턴)를 임시 파일로 생성
2. `tools.video_engine`의 핵심 처리 함수를 호출해 출력 비디오를 만들고:
   - 출력 파일이 존재하고 열리는지
   - 프레임 수/해상도/fps가 입력과 일치하는지
   - 출력 프레임이 입력과 실제로 달라졌는지(브랜드 룩이 적용됐는지 픽셀
     비교로 확인)
   - 동일 입력에 CLAHE 버전(`apply_*_look`)과 비디오 버전을 각각 돌렸을
     때 비디오 버전이 프레임 간 편차가 더 작은지(플리커 감소를 근사
     검증 - 완벽한 시각적 플리커 측정은 아니지만 CLAHE 생략의 효과를
     정량적으로 보여줌)
3. 존재하지 않는 브랜드 인자를 줬을 때 에러가 나는지
4. 존재하지 않는 입력 파일 경로를 줬을 때 에러가 나는지

## 한계 (문서화 대상: README.md/README.ko.md, 모듈 docstring)

- **오디오 트랙 미보존** - v1은 무음 비디오만 출력한다.
- **사진 모드와 동일한 룩이 아니다** - CLAHE(로컬 대비 보정)를 생략하므로
  `apply_*_look()`으로 만든 사진보다 로컬 대비가 약하다.
- **비디오 전용 색과학 측정이 아니다** - 시네마 카메라의 실제 영상
  렌더링을 측정한 게 아니라, 기존 스틸사진 population-fit 결과를 프레임에
  재사용한 것이다. 카메라 브랜드가 정지 JPEG와 동영상에서 실제로 다른
  색처리를 쓸 수 있다는 점(예: 다른 톤커브/샤프닝)은 검증되지 않았다.
- **실제 비디오 파일로 검증되지 않음** - 합성 프레임으로만 테스트했고,
  실제 카메라 mp4/mov 파일에 대한 스모크 테스트는 이 환경에 샘플이 없어
  수행하지 못했다.
