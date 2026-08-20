# 비디오 엔진에 Fujifilm/Hasselblad 브랜드 추가

## 배경 / 문제

`tools/video_engine.py`(v1, `docs/superpowers/specs/2026-07-26-video-engine-design.md`)는
`core.engine.apply_population_fit_look()`을 공유하는 10개 브랜드(Canon/
Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony)만
지원한다. Fujifilm(`brands/fuji.py`, 프리셋 10종)과 Hasselblad
(`brands/hasselblad.py`의 `apply_hncs`)는 "각자 다른 파이프라인이라
CLAHE 사용 여부가 제각각"이라는 이유로 명시적으로 범위 밖이었다.

이 스펙은 그 갭을 메운다: 실제로 CLAHE를 쓰는 함수가 몇 개인지, 무엇이
정말 문제인지를 코드 조사로 확인하고, 필요한 만큼만 CLAHE 생략 변형을
추가한다.

## 조사 결과 (설계 단계에서 확인)

- **Fuji 10개 프리셋 중 CLAHE를 쓰는 건 `apply_pro_neg_hi` 1개뿐**
  (`clahe_clip=1.5`). 나머지 9개(`apply_astia`/`apply_pro_neg_std`/
  `apply_eterna_cinema`/`apply_eterna_bleach_bypass`/
  `apply_nostalgic_neg`/`apply_reala_ace`/`apply_classic_negative`/
  `apply_acros`/`apply_monochrome`)는 전부 고정 파라미터 기반 결정론적
  픽셀 연산(채널 배율, 고정 LUT, HSV 채도 배율 등)이라 프레임 내용에
  의존하는 단계가 없다 - 비디오에서 CLAHE가 일으키는 종류의 플리커
  위험이 원래 없다. **수정 없이 그대로 비디오 프레임에 재사용 가능.**
- **`apply_acros`/`apply_monochrome`은 1채널 그레이스케일을 반환한다**
  (`tests/test_brands.py`에 이미 `FUJI_MONO_PRESETS`로 분리돼 있는 기존
  구분). `cv2.VideoWriter`는 컬러 프레임(3채널)을 가정하므로(v1의
  `process_video()`가 `mp4v` fourcc + 기본 `isColor=True`로 열림) 이
  둘은 3채널로 복제해서 써야 한다.
- **`apply_hncs`(Hasselblad)는 CLAHE를 쓴다**(`clahe_clip=1.25`) - 순서는
  노출 감마 LUT(`exposure_gamma`) → CLAHE → film curve LUT. CLAHE만
  빼면 v1의 `apply_population_fit_look_video_frame()`과 같은 패턴으로
  처리 가능.
- Hasselblad의 다른 프리셋(`brands/hasselblad_day.py`/`_night.py`/
  `_learned.py`)은 각 파일 docstring에서 "Legacy"/"Experimental"로 명시된
  것들이라 이 스펙에서 제외한다 - `apply_hncs`(Stable) 하나만 다룬다.

## 목표

1. Fuji 9개(CLAHE 없음) + 1개(`apply_pro_neg_hi`, CLAHE 생략 변형 신규) +
   Hasselblad 1개(`apply_hncs`, CLAHE 생략 변형 신규) = **11개 브랜드**를
   `tools/video_engine.py`의 `--brand`에 추가한다.
2. `apply_pro_neg_hi_video_frame()`(`brands/fuji.py`)과
   `apply_hncs_video_frame()`(`brands/hasselblad.py`) 2개 함수를
   신규 추가한다 - 각 파일의 기존 함수는 수정하지 않는다.
3. `apply_acros`/`apply_monochrome`의 그레이스케일 출력을 비디오
   프레임으로 쓰기 전에 3채널로 변환한다.
4. 오디오 보존(`mux_audio()`)은 이 11개 브랜드에도 동일하게 적용된다.

## 범위 밖

- **`process_video()`/`process_video_with_audio()`(기존 함수) 수정** -
  이미 리뷰를 통과한 코드는 건드리지 않는다(아래 "설계" 참고 - 대신
  나란히 새 함수를 추가한다, 사용자와 A안/B안 중 A안으로 합의).
- **Hasselblad의 day/night/learned 프리셋** - Legacy/Experimental이라
  제외.
- **Fuji의 `apply_acros`가 받는 `filter_type` 파라미터(red/green/yellow)
  노출** - CLI에 새 옵션을 추가하지 않는다(YAGNI, v1의 "새 플래그 안 만듦"
  관례를 따름) - 기본값(`'none'`)만 쓴다.
- **새로운 2단계 CLI 구조(`--brand fuji --preset astia` 등)** - 기존
  `SUPPORTED_BRANDS`/`_BRAND_FUNCTIONS` 플랫 딕셔너리 패턴을 그대로
  확장한다(브랜드 이름에 `fuji_` 접두사를 붙여 11개를 추가).
- **다른 시네마 카메라 브랜드 추가** - 별도 스펙(사용자와 이미 순서
  합의: 오디오 보존 → 이 스펙 → 새 시네마 브랜드).

## 설계

### 아키텍처: process_video()는 수정하지 않는다 (A안, 사용자 확정)

`process_video()`는 `apply_population_fit_look_video_frame(frame,
toe_lift, shoulder_start, white_point)`를 프레임마다 고정 호출하도록
하드코딩돼 있다. Fuji/Hasselblad 함수들은 전혀 다른 시그니처(자체
기본값을 가진 단일 인자 함수, 또는 그레이스케일 반환)라 이 고정 호출로는
디스패치할 수 없다.

두 가지를 검토했다:
1. **(채택) 나란히 추가**: `process_video()`/`process_video_with_audio()`는
   한 줄도 안 건드리고, 거의 동일한 I/O 루프를 가진 새 함수
   `process_video_v2()`/`process_video_v2_with_audio()`를 추가한다 -
   프레임 처리 부분만 브랜드별 단일 인자 콜백을 딕셔너리에서 조회해서
   쓴다는 점이 다르다. `cv2.VideoCapture`/`VideoWriter` 열기/닫기,
   진행률 로그, 에러 처리 등 ~25줄의 보일러플레이트가 두 함수 사이에
   중복된다.
2. **(기각) 일반화 리팩터**: `process_video()`를 "브랜드 → 콜백" 조회
   방식으로 리팩터해서 기존 10개 브랜드도 이 경로를 거치게 한다. 중복은
   없지만 이미 세 번의 철저한 리뷰(태스크별 2번 + 최종 whole-branch
   리뷰)를 통과한 함수의 소스 라인 자체를 건드리게 된다.

**사용자가 1안(나란히 추가)을 명시적으로 선택했다** - 이번 세션 내내
지켜온 "리뷰 끝난 코드는 재수정 금지" 원칙과 일관성을 위해 중복을
감수한다. 같은 논리로 `process_video_with_audio()`도 건드리지 않고
`process_video_v2_with_audio()`를 나란히 추가한다 - 단, `mux_audio()`
자체는 브랜드 무관(오디오 소스 파일 경로만 받음)이라 그대로 재사용하고,
새로 중복되는 건 "임시파일 만들기 → process_video_v2() 호출 → mux_audio()
호출 → 정리" 오케스트레이션 ~10줄뿐이다(전체 I/O 루프가 아님).

### 모듈 구조

**`brands/fuji.py`에 추가**(기존 10개 함수는 수정 없음):

```python
def apply_pro_neg_hi_video_frame(img_bgr, sat_mult=1.10, contrast_n=1.7):
    """apply_pro_neg_hi()의 비디오 전용 변형 - CLAHE(프레임별 적응형
    로컬 대비 보정)를 생략해 프레임 간 깜빡임을 피한다. 사진 모드와
    동일한 출력이 아니다(로컬 대비가 약함)."""
    img = ensure_uint8(img_bgr)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    y = s_curve(x, n=contrast_n)
    lut = np.clip(y * 255, 0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * sat_mult, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
```

(`apply_pro_neg_hi()`에서 `clahe = cv2.createCLAHE(...); l =
clahe.apply(l)` 두 줄만 빠진 것 - 나머지 로직은 동일.)

**`brands/hasselblad.py`에 추가**(기존 `apply_hncs`는 수정 없음):

```python
def apply_hncs_video_frame(img_bgr, toe_lift=0.001, shoulder_start=0.78,
                            white_point=1.0, exposure_gamma=0.7):
    """apply_hncs()의 비디오 전용 변형 - CLAHE를 생략해 프레임 간
    깜빡임을 피한다. 사진 모드와 동일한 출력이 아니다."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    if exposure_gamma != 1.0:
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** exposure_gamma) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
```

(`apply_hncs()`에서 CLAHE 두 줄만 빠짐, 나머지 동일 - `exposure_gamma`
LUT과 `film_curve` LUT 순서도 그대로 유지.)

**`tools/video_engine.py`에 추가**(기존 `process_video`/
`process_video_with_audio`/`SUPPORTED_BRANDS`/`_BRAND_FUNCTIONS`는
수정 없음):

```python
from brands.fuji import (
    apply_astia, apply_pro_neg_std, apply_pro_neg_hi_video_frame,
    apply_eterna_cinema, apply_eterna_bleach_bypass, apply_nostalgic_neg,
    apply_reala_ace, apply_classic_negative, apply_acros, apply_monochrome,
)
from brands.hasselblad import apply_hncs_video_frame


def _grayscale_to_bgr_frame(frame_func):
    """apply_acros/apply_monochrome처럼 1채널 그레이스케일을 반환하는
    함수를 3채널 BGR 프레임을 반환하도록 감싼다(cv2.VideoWriter가 컬러
    프레임을 가정하므로)."""
    def wrapped(img_bgr):
        gray = frame_func(img_bgr)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return wrapped


_EXPANDED_BRAND_FUNCTIONS = {
    "fuji_astia": apply_astia,
    "fuji_pro_neg_std": apply_pro_neg_std,
    "fuji_pro_neg_hi": apply_pro_neg_hi_video_frame,
    "fuji_eterna_cinema": apply_eterna_cinema,
    "fuji_eterna_bleach_bypass": apply_eterna_bleach_bypass,
    "fuji_nostalgic_neg": apply_nostalgic_neg,
    "fuji_reala_ace": apply_reala_ace,
    "fuji_classic_negative": apply_classic_negative,
    "fuji_acros": _grayscale_to_bgr_frame(apply_acros),
    "fuji_monochrome": _grayscale_to_bgr_frame(apply_monochrome),
    "hasselblad": apply_hncs_video_frame,
}

EXPANDED_SUPPORTED_BRANDS = frozenset(_EXPANDED_BRAND_FUNCTIONS)


def process_video_v2(input_path, output_path, brand_name, progress_every=100):
    """확장 브랜드(Fuji 9개 무수정 + apply_pro_neg_hi/apply_hncs CLAHE
    생략 변형) 전용 - process_video()와 거의 동일한 I/O 구조지만, 프레임
    처리 함수가 (toe_lift, shoulder_start, white_point) 3개 인자 대신
    단일 인자 콜백이라는 점이 다르다. process_video()는 수정하지 않는다
    (나란히 추가)."""
    if brand_name not in _EXPANDED_BRAND_FUNCTIONS:
        raise ValueError(
            f"지원하지 않는 확장 브랜드: {brand_name!r} "
            f"(지원: {', '.join(sorted(EXPANDED_SUPPORTED_BRANDS))})"
        )
    frame_func = _EXPANDED_BRAND_FUNCTIONS[brand_name]

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise IOError(f"입력 비디오를 열 수 없음: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise IOError(f"출력 비디오를 열 수 없음: {output_path}")

    frame_count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            out_frame = frame_func(frame)
            writer.write(out_frame)
            frame_count += 1
            if frame_count % progress_every == 0:
                print(f"{frame_count}프레임 처리됨...", file=sys.stderr)
    finally:
        cap.release()
        writer.release()

    return frame_count


def process_video_v2_with_audio(input_path, output_path, brand_name, progress_every=100):
    """process_video_v2()로 색보정한 뒤 mux_audio()로 원본 오디오를
    입힌다 - process_video_with_audio()와 같은 구조지만 process_video_v2()를
    쓴다는 점만 다르다. process_video_with_audio()는 수정하지 않는다."""
    if not output_path.lower().endswith(".mp4"):
        raise ValueError(f"출력 파일은 .mp4만 지원함: {output_path!r}")
    tmp_dir = tempfile.mkdtemp()
    tmp_video_only = os.path.join(tmp_dir, "video_only.mp4")
    try:
        frame_count = process_video_v2(input_path, tmp_video_only, brand_name, progress_every)
        mux_audio(tmp_video_only, input_path, output_path)
        return frame_count
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

`process_video_v2_with_audio()`는 감사 플랜의 `process_video_with_audio()`
(이미 리뷰 통과, 오디오 보존 최종 fix에서 `.mp4` 확장자 fail-fast 체크가
추가됨)와 동일한 확장자 체크를 넣는다 - 같은 이유(전체 그레이딩 후 mux
단계에서야 실패하는 낭비 방지)로 이 새 함수도 같은 문제가 생길 수 있으니
처음부터 같은 방어를 넣는다.

**`main()` 수정**(기존 `process_video_with_audio()` 호출 분기 추가 -
이건 CLI 글루 코드라 진화가 예상되는 부분, "리뷰 끝난 코드 재수정 금지"
원칙은 `process_video()`/`process_video_with_audio()` 본문에 적용되는
것이지 이들을 호출하는 `main()`에는 적용되지 않는다):

```python
    args = parser.parse_args()

    try:
        if args.brand in SUPPORTED_BRANDS:
            frame_count = process_video_with_audio(args.input, args.output, args.brand)
        else:
            frame_count = process_video_v2_with_audio(args.input, args.output, args.brand)
    except (IOError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
```

`argparse`의 `--brand` `choices`는 `sorted(SUPPORTED_BRANDS |
EXPANDED_SUPPORTED_BRANDS)`(21개)로 바뀐다.

### 에러 처리

- `process_video_v2()`의 에러 계약은 `process_video()`와 동일: 미지원
  브랜드 → `ValueError`(지원 목록 포함), 입력 못 엶 / 출력 못 엶 →
  `IOError`.
- `process_video_v2_with_audio()`도 `.mp4` 아닌 확장자 → `ValueError`
  (오디오 보존 최종 리뷰에서 확정된 것과 동일한 방어).

### 테스트

- `apply_pro_neg_hi_video_frame()`/`apply_hncs_video_frame()`: v1의
  `apply_population_fit_look_video_frame()` 테스트와 같은 패턴 -
  (1) shape/dtype 보존, (2) 입력 비변형, (3) CLAHE 없는 버전이 원본
  `apply_pro_neg_hi()`/`apply_hncs()`(CLAHE 있음)와 다른 출력을 내는지,
  (4) CLAHE만 뺀 나머지 로직이 원본과 정확히 일치하는지(원본 함수 안의
  CLAHE 두 줄을 제외한 나머지를 직접 재현해서 정확히 일치하는지 비교 -
  v1의 `test_matches_tone_curve_only_no_clahe`와 동일한 방법).
- `_grayscale_to_bgr_frame()`: 그레이스케일 반환 함수를 감쌌을 때 출력이
  3채널이고, 3채널 각각이 원본 그레이스케일 값과 동일한지.
- `process_video_v2()`: v1의 `TestProcessVideo`와 같은 테스트 세트를
  Fuji/Hasselblad 브랜드 몇 개(예: `fuji_astia`, `fuji_pro_neg_hi`,
  `fuji_acros`, `hasselblad`)로 반복 - 11개 전부를 개별 브랜드마다
  풀세트로 반복하진 않고, CLAHE 없음/CLAHE 생략/그레이스케일 3개 대표
  카테고리만 깊게 검증 + 나머지 7개는 "출력 파일 생성되고 열림" 정도의
  가벼운 스모크 테스트로 커버(11개 브랜드 * 6개 테스트 = 66개는 과함).
- `process_video_v2_with_audio()`: v1의 `TestProcessVideoWithAudio`와
  같은 패턴(오디오 있는/없는 입력, 프레임 실제로 그레이딩됐는지, 임시
  디렉터리 정리, 미지원 브랜드, `.mp4` 아닌 확장자 fail-fast) - 대표
  브랜드 1~2개로.
- 전체 21개 브랜드 이름이 `main()`의 `choices`에 다 들어있는지 확인하는
  테스트 1개.

## 한계 (문서화 대상: README.md/README.ko.md, 모듈 docstring)

- **`apply_acros`의 필터 종류(red/green/yellow) 선택 불가** - 항상 기본
  (`none`)만 쓴다.
- **Hasselblad는 `apply_hncs`(Stable)만 지원** - day/night/learned는
  범위 밖.
- 기존 v1의 한계(오디오는 기본 보존, CLAHE 생략, 비디오 전용 색과학
  측정 아님, 실제 카메라 샘플로 미검증)가 이 11개 브랜드에도 동일하게
  적용된다.
