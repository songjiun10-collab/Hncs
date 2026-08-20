# 비디오 엔진 오디오 트랙 보존 (ffmpeg 도입) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tools/video_engine.py`가 출력 비디오에 입력의 오디오 트랙을 기본으로 보존하게 만든다 - `imageio-ffmpeg`가 제공하는 정적 ffmpeg 바이너리로 색보정된 무음 비디오에 원본 오디오를 무손실 remux하는 후처리 단계를 추가한다.

**Architecture:** 이미 리뷰를 통과한 `process_video()`(cv2 기반 프레임 처리, 오디오 없음)는 한 줄도 건드리지 않는다. 새 함수 `mux_audio()`가 ffmpeg subprocess로 무손실 스트림 복사(`-c:v copy -c:a copy`) remux를 수행하고, 새 함수 `process_video_with_audio()`가 `process_video()` → 임시 파일 → `mux_audio()` 순서로 오케스트레이션한다. `main()`은 이제 `process_video_with_audio()`를 기본으로 호출한다(opt-out 플래그 없음).

**Tech Stack:** `imageio-ffmpeg`(신규, pip - 정적 ffmpeg 바이너리 번들), 표준 라이브러리 `subprocess`/`tempfile`/`shutil`/`os`. 기존 `cv2`/`numpy`는 그대로.

## Global Constraints

- **`process_video()`(`tools/video_engine.py`, 기존 함수)는 수정 금지.** 이미 최종 리뷰(Opus)를 통과한 코드 - 새 기능은 그 위에 얹는 순수 추가로만 구현한다.
- **오디오는 항상 보존을 시도한다(입력에 있으면) - opt-out 플래그(`--no-audio` 등)는 만들지 않는다.** v1은 이 스펙에서 opt-in/opt-out 둘 다 없이 단일 기본 동작으로 확정됐다(사용자 확인 완료).
- **ffmpeg는 오직 `imageio_ffmpeg.get_ffmpeg_exe()`가 반환하는 번들 바이너리만 쓴다** - 시스템 `ffmpeg`(PATH 검색 등)에 의존하지 않는다.
- **오디오 재인코딩 금지** - `-c:v copy -c:a copy`(스트림 복사)만 쓴다. 볼륨 정규화, 코덱 변환 등 일절 안 함.
- **오디오 매핑은 `-map 0:v:0 -map 1:a:0?`(비디오는 필수, 오디오는 선택)만 쓴다** - `?`가 없으면 오디오 없는 입력에서 ffmpeg가 에러를 낸다(설계 단계에서 실측 확인). 첫 번째 오디오 트랙(`1:a:0`)만 다룬다 - 다중 트랙 선택 로직은 만들지 않는다.
- **`requirements.txt`에 `imageio-ffmpeg` 한 줄만 추가** - 다른 오디오/비디오 라이브러리(`moviepy`, `ffmpeg-python`, `av` 등)는 도입하지 않는다.
- **다음 6곳의 "오디오 미보존" 관련 문구를 전부 새 기본 동작에 맞게 고친다**(스펙이 지목한 5곳 + 구현 단계에서 추가로 발견된 1곳):
  1. `tools/video_engine.py` 모듈 docstring
  2. `tools/video_engine.py`의 `main()` 함수 안 `argparse.ArgumentParser(description=...)` 문자열 (스펙엔 명시 안 됐지만 동일한 "오디오 미보존" 주장을 담고 있어 이 계획에서 추가로 포함)
  3. `README.md`의 "Video engine" 섹션 "Known limitations"
  4. `README.ko.md`의 대응 섹션 "알려진 한계"
  5. `docs/project_structure.md`의 `tools/video_engine.py` 테이블 행
  6. `docs/project_structure.en.md`의 대응 행
- **`process_video()` 자체의 docstring은 유지하되 한 문장만 추가** - "오디오 트랙은 보존하지 않는다"는 문장은 그 함수 자체에 대해선 여전히 사실이므로 지우지 않고, "(오디오는 `process_video_with_audio()`가 별도로 처리)"를 덧붙인다.
- 테스트는 `unittest.TestCase` 스타일(프로젝트 관례, pytest 미사용).
- 각 태스크 종료 시 `python3 -m unittest discover -s tests`가 그린이어야 한다(현재 386개 - 태스크가 늘려간다).
- `ffprobe`는 이 환경에 없다(imageio-ffmpeg는 ffmpeg만 번들) - 오디오 스트림 유무 판별은 `ffmpeg -i <path>`를 실행해 stderr에 `"Audio:"` 문자열이 있는지로 한다(설계 단계 검증과 동일한 방법).

---

### Task 1: `mux_audio()` + `imageio-ffmpeg` 의존성

**Files:**
- Modify: `requirements.txt` (끝에 `imageio-ffmpeg` 한 줄 추가)
- Modify: `tools/video_engine.py` (import 4개 추가 + `mux_audio()` 함수 추가 - `process_video()`/`main()`은 이 태스크에서 변경 없음)
- Test: `tests/test_video_engine.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: 없음(이 태스크는 순수 추가 - 기존 `process_video()`/`brand_video_params()`/`SUPPORTED_BRANDS` 등 아무것도 안 씀)
- Produces: `mux_audio(video_only_path: str, audio_source_path: str, final_output_path: str) -> None` - `video_only_path`의 비디오 스트림과 `audio_source_path`의 첫 번째 오디오 스트림(없으면 오디오 없이)을 무손실로 합쳐 `final_output_path`에 쓴다. ffmpeg가 non-zero exit로 끝나면 `IOError`. Task 2가 이 함수를 오케스트레이션에 사용한다.

- [ ] **Step 1: `requirements.txt`에 의존성 추가**

`requirements.txt` 현재 내용(8줄, 끝에 개행 하나):
```
opencv-python
numpy
rawpy
requests
gdown
colour-science
lensfunpy
OpenEXR
```

끝에 `imageio-ffmpeg` 추가:
```
opencv-python
numpy
rawpy
requests
gdown
colour-science
lensfunpy
OpenEXR
imageio-ffmpeg
```

- [ ] **Step 2: 의존성 설치 확인**

Run: `pip3 install imageio-ffmpeg -q && python3 -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"`
Expected: 에러 없이 종료하고, `.../imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-...` 형태의 실제 파일 경로가 출력됨.

- [ ] **Step 3: 실패하는 테스트 작성**

`tests/test_video_engine.py` 맨 위 import 블록을 다음으로 교체(기존 `import inspect`/`import os`/`import shutil`/`import tempfile`/`import unittest`/`import cv2`/`import numpy as np`에 `import subprocess`와 `import imageio_ffmpeg` 추가):

```python
import inspect
import os
import shutil
import subprocess
import tempfile
import unittest

import cv2
import imageio_ffmpeg
import numpy as np

from tools.video_engine import SUPPORTED_BRANDS, brand_video_params, mux_audio, process_video
```

(마지막 줄의 `from tools.video_engine import ...`가 기존엔 `mux_audio` 없이 3개였던 것에 `mux_audio`를 추가한 것 - 나머지 기존 import는 그대로 유지.)

기존 `_make_synthetic_video()` 헬퍼 함수 **바로 다음**에 새 헬퍼 3개 추가:

```python
def _make_synthetic_video_with_audio(path, duration=1, width=64, height=48, fps=24):
    """testsrc(그라디언트 패턴 비디오) + sine(440Hz 톤 오디오)을 ffmpeg
    lavfi 소스로 직접 만든 합성 비디오 - cv2.VideoWriter는 오디오를 못
    쓰므로 오디오 트랙이 필요한 테스트에서만 이 헬퍼를 쓴다."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg_exe, "-y",
         "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
         "-c:v", "libx264", "-c:a", "aac", path],
        capture_output=True, text=True, check=True,
    )


def _make_synthetic_video_without_audio(path, duration=1, width=64, height=48, fps=24):
    """testsrc만 있는(오디오 트랙 없는) 합성 비디오."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg_exe, "-y",
         "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate={fps}:duration={duration}",
         "-c:v", "libx264", path],
        capture_output=True, text=True, check=True,
    )


def _has_audio_stream(path):
    """ffprobe가 이 환경에 없으므로 ffmpeg -i 출력(stderr)에 "Audio:"
    문자열이 있는지로 오디오 스트림 존재 여부를 판별한다(설계 단계
    검증과 동일한 방법)."""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    result = subprocess.run([ffmpeg_exe, "-i", path], capture_output=True, text=True)
    return "Audio:" in result.stderr
```

파일 끝의 `if __name__ == "__main__": unittest.main()` **바로 위**에 새 테스트 클래스 추가:

```python
class TestMuxAudio(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_mux_with_audio_source_produces_audio_output(self):
        video_only = os.path.join(self.tmpdir, "video_only.mp4")
        audio_source = os.path.join(self.tmpdir, "audio_source.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(video_only)
        _make_synthetic_video_with_audio(audio_source)

        mux_audio(video_only, audio_source, output)

        self.assertTrue(os.path.exists(output))
        self.assertTrue(_has_audio_stream(output))

    def test_mux_with_silent_source_produces_silent_output_no_error(self):
        video_only = os.path.join(self.tmpdir, "video_only.mp4")
        audio_source = os.path.join(self.tmpdir, "audio_source.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(video_only)
        _make_synthetic_video_without_audio(audio_source)

        mux_audio(video_only, audio_source, output)  # must not raise

        self.assertTrue(os.path.exists(output))
        self.assertFalse(_has_audio_stream(output))

    def test_mux_preserves_video_stream(self):
        video_only = os.path.join(self.tmpdir, "video_only.mp4")
        audio_source = os.path.join(self.tmpdir, "audio_source.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(video_only)
        _make_synthetic_video_with_audio(audio_source)

        mux_audio(video_only, audio_source, output)

        cap = cv2.VideoCapture(output)
        self.assertTrue(cap.isOpened())
        self.assertGreater(cap.get(cv2.CAP_PROP_FRAME_COUNT), 0)
        cap.release()

    def test_mux_failure_raises_io_error(self):
        video_only = os.path.join(self.tmpdir, "does_not_exist.mp4")
        audio_source = os.path.join(self.tmpdir, "also_does_not_exist.mp4")
        output = os.path.join(self.tmpdir, "output.mp4")
        with self.assertRaises(IOError):
            mux_audio(video_only, audio_source, output)
```

- [ ] **Step 4: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: `ImportError: cannot import name 'mux_audio' from 'tools.video_engine'` 로 FAIL

- [ ] **Step 5: 최소 구현 작성**

`tools/video_engine.py` 상단 import 블록(`import argparse` / `import inspect` / `import sys` 다음, `import cv2` 앞)에 추가:

```python
import argparse
import inspect
import subprocess
import sys

import cv2
import imageio_ffmpeg
```

(`import subprocess`와 `import imageio_ffmpeg` 2개가 신규 - `argparse`/`inspect`/`sys`/`cv2`는 기존 그대로 알파벳 순서 유지.)

`_BRAND_FUNCTIONS`/`SUPPORTED_BRANDS`/`brand_video_params()`/`process_video()` 정의부는 그대로 두고, `process_video()` 함수 **바로 다음**(즉 `def main():` **바로 앞**)에 추가:

```python
def mux_audio(video_only_path, audio_source_path, final_output_path):
    """video_only_path(오디오 없는 색보정 비디오)에 audio_source_path의
    첫 번째 오디오 트랙을 무손실로 입혀 final_output_path에 쓴다.
    audio_source_path에 오디오가 없으면 final_output_path도 무음(에러
    아님) - ffmpeg의 optional map(`?`)이 처리한다. 재인코딩 없음
    (-c:v copy -c:a copy)."""
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
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: 전부 PASS (기존 12개 + 새 `TestMuxAudio` 4개, 총 16개)

- [ ] **Step 7: 전체 테스트 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 총 390개(기존 386 + 4)

- [ ] **Step 8: 커밋**

```bash
git add requirements.txt tools/video_engine.py tests/test_video_engine.py
git commit -m "Add mux_audio(): lossless ffmpeg remux via imageio-ffmpeg"
```

---

### Task 2: `process_video_with_audio()` + CLI를 오디오 보존 기본값으로 전환

**Files:**
- Modify: `tools/video_engine.py` (import 5개 추가 + `process_video_with_audio()` 함수 추가 + `main()`이 이 함수를 호출하도록 변경 + `process_video()` docstring 한 문장 추가)
- Test: `tests/test_video_engine.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: `process_video(input_path, output_path, brand_name, progress_every=100) -> int`(Task 1 이전부터 존재, 수정 없음), `mux_audio(video_only_path, audio_source_path, final_output_path) -> None`(Task 1에서 생성)
- Produces: `process_video_with_audio(input_path: str, output_path: str, brand_name: str, progress_every: int = 100) -> int` - 처리한 프레임 수를 반환. `process_video()`가 던지는 `IOError`/`ValueError`, `mux_audio()`가 던지는 `IOError`를 그대로 전파. `main()`이 이 함수를 CLI의 기본 진입점으로 사용한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_video_engine.py`의 import 줄을 갱신 - 기존:
```python
from tools.video_engine import SUPPORTED_BRANDS, brand_video_params, mux_audio, process_video
```
다음으로 교체:
```python
from tools.video_engine import (
    SUPPORTED_BRANDS, brand_video_params, mux_audio, process_video,
    process_video_with_audio,
)
```

`TestMuxAudio` 클래스 **바로 다음**(`if __name__ == "__main__":` **바로 위**)에 새 테스트 클래스 추가:

```python
class TestProcessVideoWithAudio(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_input_with_audio_preserves_audio_in_output(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        frame_count = process_video_with_audio(input_path, output_path, "canon")

        self.assertGreater(frame_count, 0)
        self.assertTrue(_has_audio_stream(output_path))

    def test_input_without_audio_produces_silent_output_no_error(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_without_audio(input_path, duration=1, fps=24)

        frame_count = process_video_with_audio(input_path, output_path, "canon")

        self.assertGreater(frame_count, 0)
        self.assertFalse(_has_audio_stream(output_path))

    def test_output_frames_are_color_graded(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        process_video_with_audio(input_path, output_path, "canon")

        cap_in = cv2.VideoCapture(input_path)
        cap_out = cv2.VideoCapture(output_path)
        ok_in, frame_in = cap_in.read()
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_in)
        self.assertTrue(ok_out)
        self.assertFalse(np.array_equal(frame_in, frame_out))
        cap_in.release()
        cap_out.release()

    def test_no_leftover_temp_directories(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        before = set(os.listdir(tempfile.gettempdir()))
        process_video_with_audio(input_path, output_path, "canon")
        after = set(os.listdir(tempfile.gettempdir()))

        self.assertEqual(before, after)

    def test_unsupported_brand_raises_value_error(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        with self.assertRaises(ValueError):
            process_video_with_audio(input_path, output_path, "fuji")

    def test_missing_input_raises_io_error(self):
        missing_path = os.path.join(self.tmpdir, "does_not_exist.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")

        with self.assertRaises(IOError):
            process_video_with_audio(missing_path, output_path, "canon")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: `ImportError: cannot import name 'process_video_with_audio' from 'tools.video_engine'` 로 FAIL

- [ ] **Step 3: 최소 구현 작성**

`tools/video_engine.py` 상단 import 블록에 4개 추가(Task 1에서 `import subprocess`/`import imageio_ffmpeg`는 이미 추가돼 있음 - 이번엔 `os`/`shutil`/`tempfile` 추가):

```python
import argparse
import inspect
import os
import shutil
import subprocess
import sys
import tempfile

import cv2
import imageio_ffmpeg
```

`mux_audio()` 함수(Task 1에서 생성) **바로 다음**, `def main():` **바로 앞**에 추가:

```python
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

`process_video()`의 docstring을 다음으로 교체(기존 3문장에 4번째 문장 추가):

```python
def process_video(input_path, output_path, brand_name, progress_every=100):
    """input_path의 비디오를 읽어 brand_name 룩(CLAHE 생략, 톤 LUT만)을
    프레임마다 적용해 output_path에 쓴다. 처리한 프레임 수를 반환한다.
    오디오 트랙은 보존하지 않는다(오디오는 process_video_with_audio()가
    별도로 처리)."""
```

`main()`의 `process_video(args.input, args.output, args.brand)` 호출을 `process_video_with_audio(args.input, args.output, args.brand)`로 교체 - `main()`의 나머지 부분(argparse 인자 정의, `except (IOError, ValueError)` 처리, 출력 메시지)은 이 스텝에서 변경하지 않는다(Task 3에서 `description=` 문구만 별도로 수정):

```python
def main():
    parser = argparse.ArgumentParser(
        description="비디오 파일에 population-fit 브랜드 룩 적용 (오디오 미보존)")
    parser.add_argument("input", help="입력 비디오 파일 경로")
    parser.add_argument("output", help="출력 비디오 파일 경로 (.mp4)")
    parser.add_argument("--brand", required=True, choices=sorted(SUPPORTED_BRANDS),
                         help="적용할 브랜드 룩")
    args = parser.parse_args()

    try:
        frame_count = process_video_with_audio(args.input, args.output, args.brand)
    except (IOError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"완료: {frame_count}프레임 -> {args.output}")
```

(위 블록에서 바뀐 건 `process_video(...)` → `process_video_with_audio(...)` 호출 한 줄뿐 - `description=`의 "오디오 미보존" 문구는 아직 그대로 - Task 3에서 고친다.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: 전부 PASS (기존 16개 + 새 `TestProcessVideoWithAudio` 6개, 총 22개)

- [ ] **Step 5: 합성 비디오로 CLI 수동 스모크 테스트**

Run:
```bash
python3 -c "
from tests.test_video_engine import _make_synthetic_video_with_audio
_make_synthetic_video_with_audio('/tmp/smoke_input_audio.mp4', duration=2, fps=24)
"
python3 -m tools.video_engine /tmp/smoke_input_audio.mp4 /tmp/smoke_output_audio.mp4 --brand sigma
python3 -c "
from tests.test_video_engine import _has_audio_stream
print('has audio:', _has_audio_stream('/tmp/smoke_output_audio.mp4'))
"
```

Expected: 첫 명령은 `완료: 48프레임 -> /tmp/smoke_output_audio.mp4`(2초*24fps) 출력 후 exit 0. 두 번째 명령은 `has audio: True`를 출력.

- [ ] **Step 6: 전체 테스트 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 총 396개(기존 390 + 6)

- [ ] **Step 7: 커밋**

```bash
git add tools/video_engine.py tests/test_video_engine.py
git commit -m "Wire process_video_with_audio() as the CLI's default entry point"
```

---

### Task 3: 문서화(6곳) + 전체 테스트 스위트 확인 + 푸시

**Files:**
- Modify: `tools/video_engine.py` (모듈 docstring + `main()`의 `description=` 문자열)
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `docs/project_structure.md`
- Modify: `docs/project_structure.en.md`

**Interfaces:**
- Consumes: Task 1/2에서 만든 `mux_audio`/`process_video_with_audio` (이름만 문서에 인용, 코드 변경 없음 - `tools/video_engine.py`의 docstring/description 문자열 2곳만 예외)

- [ ] **Step 1: `tools/video_engine.py` 모듈 docstring 수정**

현재(파일 맨 위, 1~24번째 줄 부근):
```python
"""비디오 파일(mp4)에 population-fit 브랜드 룩을 프레임 단위로 적용하는
CLI. brands/*.py의 apply_*_look()은 이미 각 브랜드의 population 측정을
마쳤지만 정지 이미지 한 장만 다룬다 - 이 모듈은 새 색과학 측정 없이
그 결과를 비디오 프레임 시퀀스에 반복 적용하는 순수 엔지니어링이다.

지원 브랜드는 core.engine.apply_population_fit_look()을 공유하는 10개뿐
(canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony).
Fujifilm(프리셋마다 CLAHE 사용이 제각각)과 Hasselblad(별도 파이프라인,
자체 CLAHE)는 각자 다른 코드 경로라 이 모듈 하나로 묶을 수 없어 범위
밖이다 - 지원 대상 확장은 docs/superpowers/specs/2026-07-26-video-engine-design.md
참고.

비디오 모드는 사진 모드(apply_*_look())와 동일한 출력이 아니다 - CLAHE
(프레임별 적응형 로컬 대비 보정)를 생략한다. CLAHE를 프레임마다 그대로
쓰면 인접 프레임의 미세한 내용 차이만으로도 타일 히스토그램이 달라져
비디오에서 눈에 띄는 밝기/대비 깜빡임(flicker)이 생기기 때문이다
(core.engine.apply_population_fit_look_video_frame() 참고).

오디오 트랙은 보존하지 않는다 - 이 환경에 ffmpeg CLI/moviepy 등 오디오
mux 도구가 없다(cv2가 FFmpeg를 내장 빌드했지만 파이썬에서 오디오
스트림을 다루는 경로는 별도로 없음).

  python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
"""
```

마지막 두 번째 문단(오디오 관련)을 다음으로 교체(나머지 문단은 그대로 유지):
```python
오디오 트랙은 기본으로 보존된다 - process_video_with_audio()가
imageio-ffmpeg(정적 ffmpeg 바이너리를 pip로 받아옴)로 색보정된 무음
비디오에 원본의 첫 번째 오디오 트랙을 무손실 remux한다(입력에 오디오가
없으면 출력도 무음, 에러 아님). 재인코딩·다중 트랙 선택은 하지 않는다.
프레임 색보정 자체는 process_video()가 그대로 담당한다(오디오와 무관).
```

- [ ] **Step 2: `main()`의 `description=` 문구 수정**

현재:
```python
    parser = argparse.ArgumentParser(
        description="비디오 파일에 population-fit 브랜드 룩 적용 (오디오 미보존)")
```

다음으로 교체:
```python
    parser = argparse.ArgumentParser(
        description="비디오 파일에 population-fit 브랜드 룩 적용 (오디오 트랙 기본 보존)")
```

- [ ] **Step 3: `README.md` "Video engine" 섹션 수정**

현재(250번째 줄 부근, "## Video engine..." 섹션의 "Known limitations" 문단):
```
**Known limitations**: (1) audio tracks are not preserved (this environment has no `ffmpeg` CLI/`moviepy`/audio-mux tooling - `cv2`'s built-in FFmpeg only covers video frames); (2) the video path skips CLAHE (per-frame adaptive local-contrast correction) to avoid inter-frame flicker, so its output is not identical to the photo-mode `apply_*_look()`; (3) this is not a video-specific color-science measurement - whether a camera brand actually renders video differently from its still JPEGs (different tone curve, sharpening, etc.) is unverified; (4) only validated against synthetic test video in this environment - no real camera mp4/mov sample was available for a smoke test.
```

다음으로 교체:
```
**Known limitations**: (1) audio is preserved by default via a lossless remux step (`imageio-ffmpeg`'s bundled static ffmpeg binary, `-c:v copy -c:a copy` - no re-encoding, first audio track only, no opt-out flag); (2) the video path skips CLAHE (per-frame adaptive local-contrast correction) to avoid inter-frame flicker, so its output is not identical to the photo-mode `apply_*_look()`; (3) this is not a video-specific color-science measurement - whether a camera brand actually renders video differently from its still JPEGs (different tone curve, sharpening, etc.) is unverified; (4) only validated against synthetic test video in this environment - no real camera mp4/mov sample was available for a smoke test.
```

- [ ] **Step 4: `README.ko.md` 대응 섹션 수정**

현재(361번째 줄 부근, "## 비디오 엔진..." 섹션의 "알려진 한계" 문단):
```
**알려진 한계**: (1) 오디오 트랙 미보존(이 환경에 `ffmpeg` CLI/`moviepy` 등 오디오 mux 도구가 없음 - `cv2` 내장 FFmpeg는 비디오 프레임만 다룸); (2) 비디오 경로는 프레임 간 깜빡임을 피하려고 CLAHE(프레임별 적응형 로컬 대비 보정)를 생략해서 사진 모드 `apply_*_look()`과 동일한 출력이 아님; (3) 비디오 전용 색과학 측정이 아님 - 카메라 브랜드가 정지 JPEG와 실제 영상에서 다른 색처리(톤커브/샤프닝 등)를 쓸 수 있다는 점은 검증되지 않음; (4) 이 환경에 실제 카메라 mp4/mov 샘플이 없어 합성 테스트 비디오로만 검증됨.
```

다음으로 교체:
```
**알려진 한계**: (1) 오디오는 기본으로 보존됨 - `imageio-ffmpeg`가 받아온 정적 ffmpeg 바이너리로 무손실 remux(`-c:v copy -c:a copy`, 재인코딩 없음, 첫 번째 오디오 트랙만, opt-out 플래그 없음); (2) 비디오 경로는 프레임 간 깜빡임을 피하려고 CLAHE(프레임별 적응형 로컬 대비 보정)를 생략해서 사진 모드 `apply_*_look()`과 동일한 출력이 아님; (3) 비디오 전용 색과학 측정이 아님 - 카메라 브랜드가 정지 JPEG와 실제 영상에서 다른 색처리(톤커브/샤프닝 등)를 쓸 수 있다는 점은 검증되지 않음; (4) 이 환경에 실제 카메라 mp4/mov 샘플이 없어 합성 테스트 비디오로만 검증됨.
```

- [ ] **Step 5: `docs/project_structure.md` 테이블 행 수정**

현재(56번째 줄):
```
| `tools/video_engine.py` | 비디오 파일(mp4)에 population-fit 브랜드 룩(10개: canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony) 프레임 단위 적용 CLI - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (오디오 미보존, CLAHE 생략 - 사진 모드와 동일 출력 아님) |
```

다음으로 교체:
```
| `tools/video_engine.py` | 비디오 파일(mp4)에 population-fit 브랜드 룩(10개: canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony) 프레임 단위 적용 CLI - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (오디오 기본 보존 - imageio-ffmpeg 무손실 remux, CLAHE 생략 - 사진 모드와 동일 출력 아님) |
```

- [ ] **Step 6: `docs/project_structure.en.md` 대응 행 수정**

현재(56번째 줄):
```
| `tools/video_engine.py` | Applies a population-fit brand look to a video file (mp4) frame-by-frame, CLI - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (10 brands: canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony; audio not preserved; skips CLAHE - not identical output to photo mode) |
```

다음으로 교체:
```
| `tools/video_engine.py` | Applies a population-fit brand look to a video file (mp4) frame-by-frame, CLI - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (10 brands: canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony; audio preserved by default via imageio-ffmpeg lossless remux; skips CLAHE - not identical output to photo mode) |
```

- [ ] **Step 7: 전체 테스트 스위트 실행**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 396개(Task 1/2에서 늘어난 개수 그대로 - 이 태스크는 문서/문자열만 바꿔 테스트 개수 불변)

- [ ] **Step 8: 커밋 + 푸시**

```bash
git add tools/video_engine.py README.md README.ko.md docs/project_structure.md docs/project_structure.en.md
git commit -m "Document audio-preservation as video_engine's new default behavior"
git push -u origin claude/unknown-character-0x48vp
```
