# 비디오 엔진 오디오 트랙 보존 (ffmpeg 도입)

## 배경 / 문제

`tools/video_engine.py`(v1, `docs/superpowers/specs/2026-07-26-video-engine-design.md`)는
`cv2.VideoCapture`/`cv2.VideoWriter`만 써서 비디오를 프레임 단위로 처리한다.
이 환경에 오디오 트랙을 다룰 도구가 전혀 없어서(v1 설계 단계 확인 사항)
입력의 오디오는 출력에서 완전히 사라진다 - v1의 명시된 한계였다.

이 스펙은 그 한계를 메운다: 색보정된 비디오 프레임에 원본의 오디오
트랙을 다시 입혀서 최종 출력에 오디오가 보존되도록 한다.

## 환경 제약 (설계 단계에서 확인)

- `apt-get install ffmpeg`는 root 권한으로 가능하지만, 이 환경은 세션마다
  새로 빌드되고 이 프로젝트는 `requirements.txt`(pip)만으로 의존성을
  관리한다 - apt로 설치한 건 재현 가능한 의존성 선언이 아니라서 채택하지
  않는다.
- `imageio-ffmpeg`(pip 패키지)는 설치 시점에 정적 ffmpeg 바이너리를
  휠에 담아 받아온다(설계 단계 실측: 7.0.2, `manylinux2014_x86_64`,
  29.5MB) - 런타임에 추가로 다운로드하지 않고, `requirements.txt`
  한 줄로 어디서든 재현된다. `hybrid_engine/utils/exif.py`가 이미
  `exiftool`을 subprocess로 부르는 것과 동일한 패턴이라 프로젝트 관례와
  일치한다.
- **설계 단계에서 실제로 mux 동작을 검증했다**: 받아온 ffmpeg 바이너리로
  (1) 오디오 있는 원본 + 오디오 없는 "색보정본" 두 파일을 `-map 0:v:0
  -map 1:a:0? -c:v copy -c:a copy`로 합치면 비디오+오디오 스트림이 정상
  포함된 출력이 나오고(exit 0), (2) 원본에 오디오가 아예 없는 경우도
  `-map 1:a:0?`(물음표 = 선택적 매핑)가 에러 없이 비디오만 있는 출력을
  낸다(exit 0) - `ffprobe`로 오디오 스트림 유무를 먼저 검사하는 별도
  단계 없이 ffmpeg 자체의 optional-map 기능 하나로 두 경우를 다 처리할
  수 있음을 확인했다.

## 목표

1. `tools/video_engine.py`의 출력 비디오에 입력의 오디오 트랙을
   보존한다(입력에 오디오가 없으면 출력도 무음 - 에러 아님).
2. 오디오 보존을 CLI의 **기본 동작**으로 만든다(opt-in 플래그 없음,
   v1 설계 결정 - 사용자 확인 완료).
3. `requirements.txt`에 `imageio-ffmpeg` 의존성을 추가하고, ffmpeg
   자체는 이 패키지가 제공하는 바이너리만 쓴다(시스템 ffmpeg에 의존하지
   않음).

## 범위 밖

- **`--no-audio` 같은 opt-out 플래그** - YAGNI, v1은 항상 오디오를
  보존한다(있으면). 필요해지면 나중에 별도로 추가.
- **오디오 자체의 편집/처리(볼륨 정규화, 코덱 변환 등)** - 원본 오디오
  스트림을 무손실로 그대로 옮기기만 한다(`-c:a copy`, 재인코딩 없음).
- **다중 오디오 트랙/언어 트랙 선택** - 첫 번째 오디오 스트림(`1:a:0`)만
  다룬다.
- **`process_video()`(기존 함수) 수정** - 이미 리뷰를 통과한 프레임 처리
  로직은 건드리지 않는다. 새 오케스트레이터 함수가 그 위에 얹힌다.
- **가변 프레임레이트(VFR) 소스의 오디오-비디오 동기화 미세조정** - v1
  비디오 엔진 설계 스펙이 이미 VFR을 범위 밖으로 뒀고, 이 스펙도 동일한
  전제를 따른다.

## 설계

### 왜 "cv2 그대로 + ffmpeg remux 후처리"인가 (대안: 전체를 ffmpeg 파이프로 교체)

두 가지 아키텍처를 검토했다:

1. **(채택) 2단계**: `process_video()`(cv2 기반, 프레임별 색보정, 오디오 없음)는
   손대지 않고 그대로 두고, 그 출력을 임시 파일에 쓴 뒤 ffmpeg
   subprocess 한 번으로 원본의 오디오를 그 위에 무손실 remux한다.
2. **(기각) 전체 파이프 교체**: `cv2.VideoCapture`/`VideoWriter`를 걷어내고
   ffmpeg에 프레임을 stdin/stdout으로 직접 파이프해서 비디오+오디오를
   한 번에 처리한다.

2안이 아키텍처적으로 더 "깔끔"해 보일 수 있지만, 방금 최종 리뷰(Opus)를
통과하고 병합 준비가 끝난 `process_video()`의 핵심 루프를 다시 뜯어고쳐
재검증해야 한다 - 이 프로젝트가 이번 세션 내내 지켜온 "이미 검증된 코드는
추가만 하고 재작성하지 않는다"는 원칙과 정면으로 충돌한다. 1안은
`process_video()`를 단 한 줄도 건드리지 않고, 새 기능을 그 위에 얹는
순수 추가라 위험이 훨씬 낮다. remux 자체도 `-c:v copy -c:a copy`(스트림
복사, 재인코딩 없음)라 색보정된 픽셀이 손실 없이 그대로 옮겨진다.

### 모듈 구조

`tools/video_engine.py`에 함수 2개 추가(기존 `process_video()`/`main()`은
시그니처 변경 없이 그대로 둔다는 것에 주의 - `main()`의 **내부 호출 대상만**
바뀐다):

```python
def mux_audio(video_only_path, audio_source_path, final_output_path):
    """video_only_path(오디오 없는 색보정 비디오)에 audio_source_path의
    오디오 트랙을 무손실로 입혀 final_output_path에 쓴다.
    audio_source_path에 오디오가 없으면 final_output_path도 무음(에러
    아님) - ffmpeg의 optional map(`?`)이 처리한다."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run(
        [ffmpeg_exe, "-y",
         "-i", video_only_path, "-i", audio_source_path,
         "-map", "0:v:0", "-map", "1:a:0?",
         "-c:v", "copy", "-c:a", "copy",
         final_output_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise IOError(f"오디오 remux 실패 (ffmpeg exit {result.returncode}): "
                       f"{result.stderr[-500:]}")


def process_video_with_audio(input_path, output_path, brand_name, progress_every=100):
    """process_video()로 색보정한 뒤 input_path의 오디오를 다시 입혀서
    output_path에 쓴다 - CLI의 기본 진입점. process_video() 자체는
    수정하지 않는다."""
    tmp_dir = tempfile.mkdtemp()
    tmp_video_only = os.path.join(tmp_dir, "video_only.mp4")
    try:
        frame_count = process_video(input_path, tmp_video_only, brand_name, progress_every)
        mux_audio(tmp_video_only, input_path, output_path)
        return frame_count
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

`main()`은 기존에 `process_video(args.input, args.output, args.brand)`를
호출하던 자리를 `process_video_with_audio(args.input, args.output,
args.brand)` 호출로 바꾼다(다른 부분은 무변경). CLI 사용법 자체는
바뀌지 않는다(`--brand` 인자만 그대로, 새 플래그 없음).

`requirements.txt`에 `imageio-ffmpeg` 한 줄 추가. `tools/video_engine.py`의
현재 import는 `argparse`/`inspect`/`sys`/`cv2`/10개 브랜드 함수/
`apply_population_fit_look_video_frame`뿐이다(`os`/`tempfile`/`subprocess`/
`shutil`이 전부 없음 - v1은 임시 파일을 안 썼다). 이 스펙 구현 시
`import os`, `import shutil`, `import subprocess`, `import tempfile`,
`import imageio_ffmpeg`를 상단에 추가한다.

### 에러 처리

- ffmpeg가 non-zero exit로 끝나면(예: 손상된 중간 파일) `mux_audio()`가
  `IOError`를 던진다 - 기존 `process_video()`의 `IOError`/`ValueError`
  계약과 일관됨.
- `imageio_ffmpeg`가 설치돼 있지 않으면(즉 `requirements.txt`를 안 지킨
  환경) `import imageio_ffmpeg` 시점에 일반 `ImportError` - 이 프로젝트의
  다른 하드 의존성(`rawpy`/`opencv-python` 등)과 동일한 취급, 별도 폴백
  없음.
- `process_video()` 자체가 던지는 에러(입력 못 엶, 브랜드 미지원 등)는
  `process_video_with_audio()`에서 그대로 전파된다(오디오 mux 단계까지
  가지 않음).
- 임시 디렉터리는 성공/실패 관계없이 `finally`에서 정리한다.

### v1이 남긴, 이제 틀린 문서 주장들 (전부 이 스펙에서 고쳐야 함)

v1(`2026-07-26-video-engine-design.md`)이 "오디오 미보존"을 명시적
한계로 문서화해뒀다 - grep으로 확인한 결과 다음 5개 파일이 전부 그
문구를 담고 있고, 이 스펙 구현 시 전부 고쳐야 한다(README/docstring
일반론이 아니라 구체적으로 이 5곳):

- `tools/video_engine.py` 모듈 docstring - "오디오 트랙은 보존하지
  않는다"는 문장을 새 기본 동작에 맞게 수정.
- `README.md`의 "Video engine" 섹션 - "Known limitations"의 오디오
  미보존 항목 제거(또는 "첫 번째 트랙만, 재인코딩 없이 그대로"로 수정).
- `README.ko.md`의 대응 섹션 - 동일하게 수정.
- `docs/project_structure.md`의 `tools/video_engine.py` 테이블 행 -
  "오디오 미보존" 문구 제거/수정.
- `docs/project_structure.en.md`의 대응 행 - 동일하게 수정.

`process_video()`(저수준 프레임 처리 함수) 자체의 docstring("오디오
트랙은 보존하지 않는다")은 **그대로 둔다** - 그 함수 자체는 실제로 여전히
오디오를 안 다루는 게 맞다(오디오는 `process_video_with_audio()`가
얹는다). 헷갈리지 않게, 구현 단계에서 이 함수의 docstring에 "(오디오는
`process_video_with_audio()`가 별도로 처리)"를 한 문장 추가하는 걸
권장.

### 테스트

`tests/test_video_engine.py`에 추가(레포에 아직 `imageio-ffmpeg`가 없으므로
이 스펙의 구현 단계에서 `pip install`도 함께 필요):

1. ffmpeg의 `lavfi` 소스(`testsrc`/`sine`)로 오디오 있는 합성 mp4와
   오디오 없는 합성 mp4를 각각 만들어 테스트 픽스처로 사용(설계 단계
   검증에 쓴 것과 동일한 방식) - `cv2.VideoWriter`로 만드는 기존 v1
   픽스처와는 별도로, 오디오 트랙이 필요한 테스트에서만 이 방식을 쓴다.
2. `mux_audio()`: 오디오 있는 소스로 mux한 출력에 오디오 스트림이
   있는지, 오디오 없는 소스로 mux한 출력엔 오디오 스트림이 없지만
   에러 없이 성공하는지 - `imageio_ffmpeg`가 제공하는 동일 바이너리로
   출력을 다시 읽어 스트림 목록을 확인(`ffprobe`가 별도로 없으므로
   `ffmpeg -i output.mp4` 실행 후 stderr에서 `Stream #`/`Audio` 문자열
   존재 여부로 판별, 설계 단계 검증과 동일한 방법).
3. `process_video_with_audio()`: 오디오 있는 입력 → 출력에 오디오 보존
   확인 + 프레임이 실제로 색보정됐는지(v1의 `process_video()` 테스트와
   동일한 방식으로 프레임 차이 확인) + 임시 디렉터리가 정리됐는지.
4. `process_video_with_audio()`: 오디오 없는 입력 → 에러 없이 성공,
   출력도 무음.
5. `main()`(CLI)이 이제 `process_video_with_audio()`를 호출하는지 - 기존
   Task 2의 수동 스모크 테스트를 오디오 있는 합성 파일로 재실행해서
   실제 출력에 오디오가 들어갔는지 확인(자동 테스트가 아니라 구현 단계의
   수동 확인 스텝으로 진행).

## 한계 (문서화 대상: README.md/README.ko.md, 모듈 docstring)

- **오디오는 무손실로 그대로 옮겨질 뿐, 편집되지 않는다** - 볼륨 정규화,
  코덱 변환 등은 하지 않는다.
- **첫 번째 오디오 트랙만** - 다중 오디오/언어 트랙이 있는 파일은 첫
  번째만 보존된다.
- **VFR(가변 프레임레이트) 동기화는 v1과 동일하게 미검증** - v1 비디오
  엔진 스펙의 기존 한계를 그대로 상속.
- **`imageio-ffmpeg`가 새 하드 의존성으로 추가됨** - 이 패키지가 없으면
  `tools/video_engine.py`를 아예 쓸 수 없다(이전엔 `cv2`만으로 충분했음).
