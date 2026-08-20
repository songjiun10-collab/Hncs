# 비디오 파일에 brand look 적용 (video engine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 population-fit으로 측정된 10개 브랜드(Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony)의 `apply_*_look()`을 실제 비디오 파일(mp4)에 프레임 단위로 적용하는 CLI(`tools/video_engine.py`)를 만든다. 프레임 단위 CLAHE가 일으키는 시간적 깜빡임을 피하기 위해 비디오 전용 처리 경로는 톤 커브만 적용한다.

**Architecture:** `core/engine.py`에 CLAHE 없이 톤 LUT만 적용하는 `apply_population_fit_look_video_frame()`을 추가한다(기존 `apply_population_fit_look()`은 건드리지 않음). `tools/video_engine.py`는 `cv2.VideoCapture`/`cv2.VideoWriter`로 비디오를 프레임 단위로 순회하며 이 새 함수를 호출한다. 브랜드별 `toe_lift`/`shoulder_start`/`white_point` 값은 각 브랜드 모듈의 `apply_*_look()` 함수 기본 인자값을 `inspect.signature`로 읽어와서 얻는다(private 상수를 직접 import하지 않음).

**Tech Stack:** 기존 의존성만 사용 - `opencv-python`(cv2, 내장 FFmpeg 빌드), `numpy`. 새 의존성 추가 없음(`ffmpeg` CLI/`moviepy`/`imageio_ffmpeg`/`av`는 이 환경에 없고 추가하지 않는다).

## Global Constraints

- **지원 브랜드는 정확히 10개**: `canon`, `leica`, `nikon`, `olympus`, `panasonic`, `pentax`, `phaseone`, `ricoh_gr`, `sigma`, `sony`. Fujifilm/Hasselblad(및 `hasselblad_day`/`hasselblad_night`/`hasselblad_learned`)는 범위 밖 - `--brand`에 이 10개 외의 값을 주면 에러로 거부한다.
- **오디오 트랙 미지원**: v1은 무음 비디오만 출력한다. 오디오 mux 시도 금지(도구 없음).
- **비디오 모드는 CLAHE를 쓰지 않는다**: `apply_population_fit_look_video_frame()`은 톤 LUT만 적용한다. `clahe_clip`을 낮춰서 우회하는 방식은 쓰지 않는다(설계 단계 실측: `clipLimit`이 0에 가까워져도 CLAHE는 항등변환으로 수렴하지 않음 - `clahe.apply()` 호출 자체를 생략해야 함).
- **브랜드 파라미터는 `inspect.signature`로 읽는다**: `brands/*.py`의 `_TOE_LIFT`/`_SHOULDER_START`/`_WHITE_POINT`(밑줄 접두사, 비공개 관례)를 다른 모듈에서 직접 import하지 않는다. 각 브랜드의 `apply_*_look(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START, white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP)`의 기본 인자값을 읽어온다.
- **새 외부 의존성 추가 금지**: `cv2.VideoCapture`/`cv2.VideoWriter`만 사용. fourcc는 `"mp4v"` 고정.
- **기존 코드 보존**: `core/engine.py`의 `apply_population_fit_look()`, 각 `brands/*.py`는 수정하지 않는다(추가만).
- 테스트는 `unittest.TestCase` 스타일(프로젝트 관례, pytest 미사용).
- 각 태스크 종료 시 `python3 -m unittest discover -s tests`가 그린이어야 한다(현재 369개 - 태스크가 늘려간다).
- 문서는 README.md/README.ko.md 둘 다, `docs/project_structure.md`/`.en.md` 둘 다 갱신(이중언어 동시 유지 관례).

---

### Task 1: `apply_population_fit_look_video_frame()` (CLAHE 생략 톤 LUT 전용 경로)

**Files:**
- Modify: `core/engine.py` (추가만 - 기존 `apply_population_fit_look()` 수정 금지)
- Test: `tests/test_engine.py` (기존 파일에 테스트 클래스 추가)

**Interfaces:**
- Consumes: `core.curve.film_curve(x, toe_lift, shoulder_start, white_point)` (기존 함수, 시그니처 불변)
- Produces: `apply_population_fit_look_video_frame(img_bgr, toe_lift, shoulder_start, white_point) -> np.ndarray` (uint8, `img_bgr`와 동일 shape) - Task 2가 이 함수를 프레임마다 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_engine.py` 끝에 추가:

```python
from core.curve import film_curve
from core.engine import apply_population_fit_look, apply_population_fit_look_video_frame


class TestApplyPopulationFitLookVideoFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_different_toe_lift_changes_output(self):
        out_low = apply_population_fit_look_video_frame(
            self.img, toe_lift=1 / 255, shoulder_start=0.78, white_point=230 / 255)
        out_high = apply_population_fit_look_video_frame(
            self.img, toe_lift=20 / 255, shoulder_start=0.78, white_point=230 / 255)
        self.assertFalse(np.array_equal(out_low, out_high))

    def test_matches_tone_curve_only_no_clahe(self):
        # apply_population_fit_look()의 두 단계(CLAHE + 톤커브) 중 톤커브
        # 단계만 직접 재현해서 정확히 일치하는지 확인 - CLAHE가 정말
        # 생략됐는지를 결과값으로 못박는 테스트.
        lab = cv2.cvtColor(self.img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x, 10 / 255, 0.78, 230 / 255) * 255,
                       0, 255).astype(np.uint8)
        l_expected = cv2.LUT(l, lut)
        expected = cv2.cvtColor(cv2.merge((l_expected, a, b)), cv2.COLOR_LAB2BGR)

        out = apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        np.testing.assert_array_equal(out, expected)

    def test_differs_from_photo_mode_with_clahe(self):
        photo_out = apply_population_fit_look(
            self.img, toe_lift=10 / 255, shoulder_start=0.78,
            white_point=230 / 255, clahe_clip=1.25)
        video_out = apply_population_fit_look_video_frame(
            self.img, toe_lift=10 / 255, shoulder_start=0.78, white_point=230 / 255)
        self.assertFalse(np.array_equal(photo_out, video_out))
```

`tests/test_engine.py` 맨 위 import 블록도 `cv2`가 필요하므로 다음처럼 갱신:

```python
import unittest

import cv2
import numpy as np

from core.curve import film_curve
from core.engine import apply_population_fit_look, apply_population_fit_look_video_frame
```

(기존 `from core.engine import apply_population_fit_look` 한 줄짜리 import는 위 블록으로 대체 - 나머지 기존 테스트 클래스/메서드는 그대로 둔다.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_engine -v`
Expected: `ImportError: cannot import name 'apply_population_fit_look_video_frame'` 로 FAIL

- [ ] **Step 3: 최소 구현 작성**

`core/engine.py`에 추가(기존 `apply_population_fit_look()` 아래):

```python
def apply_population_fit_look_video_frame(img_bgr, toe_lift, shoulder_start, white_point):
    """apply_population_fit_look()의 비디오 전용 변형 - CLAHE(프레임별
    적응형 로컬 대비 보정)를 생략하고 톤 LUT만 적용한다. CLAHE는 프레임마다
    로컬 히스토그램을 새로 계산해서 비디오에서 깜빡임을 유발하지만, 이
    함수가 쓰는 film_curve() 기반 톤 LUT는 브랜드 고정 파라미터로만
    계산되고 프레임 내용과 무관해 시간적으로 안정적이다. 사진 모드
    apply_population_fit_look()과 동일한 출력이 아니다(로컬 대비가 약함)."""
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)

    x = np.arange(256, dtype=np.float32) / 255.0
    lut = np.clip(film_curve(x, toe_lift, shoulder_start, white_point) * 255,
                  0, 255).astype(np.uint8)
    l = cv2.LUT(l, lut)

    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_engine -v`
Expected: 전부 PASS (기존 `TestApplyPopulationFitLook` 5개 + 새 `TestApplyPopulationFitLookVideoFrame` 5개, 총 10개)

- [ ] **Step 5: 커밋**

```bash
git add core/engine.py tests/test_engine.py
git commit -m "Add CLAHE-free video-frame variant of apply_population_fit_look"
```

---

### Task 2: `tools/video_engine.py` CLI (브랜드 파라미터 조회 + 비디오 처리 + argparse)

**Files:**
- Create: `tools/video_engine.py`
- Test: `tests/test_video_engine.py`

**Interfaces:**
- Consumes: `core.engine.apply_population_fit_look_video_frame(img_bgr, toe_lift, shoulder_start, white_point)` (Task 1에서 생성)
- Consumes: `brands.canon.apply_canon_look`, `brands.leica.apply_leica_look`, `brands.nikon.apply_nikon_look`, `brands.olympus.apply_olympus_look`, `brands.panasonic.apply_panasonic_look`, `brands.pentax.apply_pentax_look`, `brands.phaseone.apply_phaseone_look`, `brands.ricoh_gr.apply_ricoh_gr_look`, `brands.sigma.apply_sigma_look`, `brands.sony.apply_sony_look` (기존 함수, 전부 시그니처 `(img_bgr, toe_lift=_TOE_LIFT, shoulder_start=_SHOULDER_START, white_point=_WHITE_POINT, clahe_clip=_CLAHE_CLIP)`)
- Produces: `SUPPORTED_BRANDS: frozenset` - 지원 브랜드 이름 10개.
- Produces: `brand_video_params(brand_name: str) -> tuple[float, float, float]` - `(toe_lift, shoulder_start, white_point)`, 미지원 브랜드면 `ValueError`.
- Produces: `process_video(input_path: str, output_path: str, brand_name: str, progress_every: int = 100) -> int` - 처리한 프레임 수를 반환. 입력을 못 열면 `IOError`, 출력을 못 열면 `IOError`, 브랜드가 미지원이면 `ValueError`.
- Produces: `main()` - argparse CLI 엔트리 포인트.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_video_engine.py` 신규 작성:

```python
import os
import tempfile
import unittest

import cv2
import numpy as np

from tools.video_engine import SUPPORTED_BRANDS, brand_video_params, process_video


def _make_synthetic_video(path, num_frames=10, width=64, height=48, fps=24.0, seed=0):
    """그라디언트 배경 + 색 패치, 프레임마다 노이즈를 섞어 CLAHE 타일
    히스토그램이 프레임마다 달라지게 만든 합성 비디오 (레포에 실제
    카메라 비디오 샘플이 없어 유닛 테스트는 합성 데이터로 진행)."""
    rng = np.random.default_rng(seed)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    x = np.linspace(0, 255, width, dtype=np.uint8)
    gradient_row = np.tile(x, (height, 1))
    base = np.stack([gradient_row, gradient_row, gradient_row], axis=-1).astype(np.int16)
    for _ in range(num_frames):
        noise = rng.integers(-15, 16, base.shape, dtype=np.int16)
        frame = np.clip(base + noise, 0, 255).astype(np.uint8)
        frame[10:20, 10:20] = (200, 50, 50)  # BGR 색 패치
        writer.write(frame)
    writer.release()


class TestBrandVideoParams(unittest.TestCase):
    def test_supported_brands_has_exactly_ten(self):
        self.assertEqual(len(SUPPORTED_BRANDS), 10)
        self.assertEqual(SUPPORTED_BRANDS, frozenset({
            "canon", "leica", "nikon", "olympus", "panasonic",
            "pentax", "phaseone", "ricoh_gr", "sigma", "sony",
        }))

    def test_canon_params_match_brands_canon_defaults(self):
        toe_lift, shoulder_start, white_point = brand_video_params("canon")
        self.assertAlmostEqual(toe_lift, 15.0 / 255)
        self.assertAlmostEqual(shoulder_start, 0.78)
        self.assertAlmostEqual(white_point, 239.1 / 255)

    def test_unsupported_brand_raises_value_error(self):
        with self.assertRaises(ValueError):
            brand_video_params("fuji")

    def test_unsupported_brand_error_lists_supported_names(self):
        with self.assertRaises(ValueError) as ctx:
            brand_video_params("hasselblad")
        message = str(ctx.exception)
        for name in SUPPORTED_BRANDS:
            self.assertIn(name, message)


class TestProcessVideo(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.input_path = os.path.join(self.tmpdir, "input.mp4")
        self.output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video(self.input_path)

    def test_output_file_created_and_readable(self):
        frame_count = process_video(self.input_path, self.output_path, "canon")
        self.assertEqual(frame_count, 10)
        self.assertTrue(os.path.exists(self.output_path))
        cap = cv2.VideoCapture(self.output_path)
        self.assertTrue(cap.isOpened())
        cap.release()

    def test_output_matches_input_resolution_and_frame_count(self):
        process_video(self.input_path, self.output_path, "sony")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_WIDTH),
                          cap_out.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_HEIGHT),
                          cap_out.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_COUNT),
                          cap_out.get(cv2.CAP_PROP_FRAME_COUNT))
        cap_in.release()
        cap_out.release()

    def test_output_frames_differ_from_input(self):
        process_video(self.input_path, self.output_path, "nikon")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        ok_in, frame_in = cap_in.read()
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_in)
        self.assertTrue(ok_out)
        self.assertFalse(np.array_equal(frame_in, frame_out))
        cap_in.release()
        cap_out.release()

    def test_unsupported_brand_raises_before_writing_output(self):
        with self.assertRaises(ValueError):
            process_video(self.input_path, self.output_path, "fuji")

    def test_missing_input_file_raises_io_error(self):
        missing_path = os.path.join(self.tmpdir, "does_not_exist.mp4")
        with self.assertRaises(IOError):
            process_video(missing_path, self.output_path, "canon")

    def test_output_in_nonexistent_directory_raises_io_error(self):
        bad_output_path = os.path.join(self.tmpdir, "no_such_subdir", "output.mp4")
        with self.assertRaises(IOError):
            process_video(self.input_path, bad_output_path, "canon")


class TestVideoModeReducesFlickerVsPhotoMode(unittest.TestCase):
    def test_frame_to_frame_variation_lower_without_clahe(self):
        from brands.canon import apply_canon_look
        from core.engine import apply_population_fit_look_video_frame
        from tools.video_engine import brand_video_params

        rng = np.random.default_rng(7)
        width, height = 64, 48
        x = np.linspace(0, 255, width, dtype=np.uint8)
        gradient_row = np.tile(x, (height, 1))
        base = np.stack([gradient_row, gradient_row, gradient_row], axis=-1).astype(np.int16)
        frames = []
        for _ in range(10):
            noise = rng.integers(-15, 16, base.shape, dtype=np.int16)
            frames.append(np.clip(base + noise, 0, 255).astype(np.uint8))

        toe_lift, shoulder_start, white_point = brand_video_params("canon")

        def frame_to_frame_variation(processed_frames):
            means = [f[:, :, 0].astype(np.float64).mean() for f in processed_frames]
            diffs = [abs(means[i + 1] - means[i]) for i in range(len(means) - 1)]
            return float(np.mean(diffs))

        photo_outputs = [apply_canon_look(f) for f in frames]
        video_outputs = [
            apply_population_fit_look_video_frame(f, toe_lift, shoulder_start, white_point)
            for f in frames
        ]

        self.assertLess(frame_to_frame_variation(video_outputs),
                         frame_to_frame_variation(photo_outputs))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: `ModuleNotFoundError: No module named 'tools.video_engine'` 로 FAIL

- [ ] **Step 3: 최소 구현 작성**

`tools/video_engine.py` 신규 작성:

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
import argparse
import inspect
import sys

import cv2

from brands.canon import apply_canon_look
from brands.leica import apply_leica_look
from brands.nikon import apply_nikon_look
from brands.olympus import apply_olympus_look
from brands.panasonic import apply_panasonic_look
from brands.pentax import apply_pentax_look
from brands.phaseone import apply_phaseone_look
from brands.ricoh_gr import apply_ricoh_gr_look
from brands.sigma import apply_sigma_look
from brands.sony import apply_sony_look
from core.engine import apply_population_fit_look_video_frame

_BRAND_FUNCTIONS = {
    "canon": apply_canon_look,
    "leica": apply_leica_look,
    "nikon": apply_nikon_look,
    "olympus": apply_olympus_look,
    "panasonic": apply_panasonic_look,
    "pentax": apply_pentax_look,
    "phaseone": apply_phaseone_look,
    "ricoh_gr": apply_ricoh_gr_look,
    "sigma": apply_sigma_look,
    "sony": apply_sony_look,
}

SUPPORTED_BRANDS = frozenset(_BRAND_FUNCTIONS)


def brand_video_params(brand_name):
    """brand_name -> (toe_lift, shoulder_start, white_point). 각
    apply_*_look()의 공개 기본 인자값을 inspect로 읽어온다 - brands/*.py의
    비공개 _TOE_LIFT류 상수를 직접 import하지 않는다."""
    if brand_name not in _BRAND_FUNCTIONS:
        raise ValueError(
            f"지원하지 않는 브랜드: {brand_name!r} "
            f"(지원: {', '.join(sorted(SUPPORTED_BRANDS))})"
        )
    sig = inspect.signature(_BRAND_FUNCTIONS[brand_name])
    return (
        sig.parameters["toe_lift"].default,
        sig.parameters["shoulder_start"].default,
        sig.parameters["white_point"].default,
    )


def process_video(input_path, output_path, brand_name, progress_every=100):
    """input_path의 비디오를 읽어 brand_name 룩(CLAHE 생략, 톤 LUT만)을
    프레임마다 적용해 output_path에 쓴다. 처리한 프레임 수를 반환한다.
    오디오 트랙은 보존하지 않는다."""
    toe_lift, shoulder_start, white_point = brand_video_params(brand_name)

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
            out_frame = apply_population_fit_look_video_frame(
                frame, toe_lift, shoulder_start, white_point)
            writer.write(out_frame)
            frame_count += 1
            if frame_count % progress_every == 0:
                print(f"{frame_count}프레임 처리됨...", file=sys.stderr)
    finally:
        cap.release()
        writer.release()

    return frame_count


def main():
    parser = argparse.ArgumentParser(
        description="비디오 파일에 population-fit 브랜드 룩 적용 (오디오 미보존)")
    parser.add_argument("input", help="입력 비디오 파일 경로")
    parser.add_argument("output", help="출력 비디오 파일 경로 (.mp4)")
    parser.add_argument("--brand", required=True, choices=sorted(SUPPORTED_BRANDS),
                         help="적용할 브랜드 룩")
    args = parser.parse_args()

    try:
        frame_count = process_video(args.input, args.output, args.brand)
    except (IOError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"완료: {frame_count}프레임 -> {args.output}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: 전부 PASS (`TestBrandVideoParams` 4개 + `TestProcessVideo` 6개 + `TestVideoModeReducesFlickerVsPhotoMode` 1개, 총 11개)

- [ ] **Step 5: 합성 비디오로 CLI 자체를 수동 스모크 테스트**

Run:
```bash
python3 -c "
from tests.test_video_engine import _make_synthetic_video
_make_synthetic_video('/tmp/smoke_input.mp4', num_frames=15)
"
python3 -m tools.video_engine /tmp/smoke_input.mp4 /tmp/smoke_output.mp4 --brand sigma
python3 -m tools.video_engine /tmp/smoke_input.mp4 /tmp/smoke_output.mp4 --brand not_a_brand
```

Expected: 첫 번째 명령은 `완료: 15프레임 -> /tmp/smoke_output.mp4` 출력 후 exit code 0. 두 번째 명령은 argparse가 `--brand`를 `choices`로 검증하므로 `invalid choice: 'not_a_brand'` 에러와 함께 exit code 2.

- [ ] **Step 6: 커밋**

```bash
git add tools/video_engine.py tests/test_video_engine.py
git commit -m "Add video_engine CLI: apply population-fit brand looks to video files"
```

---

### Task 3: 문서화 (README, project_structure) + 전체 테스트 스위트 확인

**Files:**
- Modify: `README.md`
- Modify: `README.ko.md`
- Modify: `docs/project_structure.md`
- Modify: `docs/project_structure.en.md`

**Interfaces:**
- Consumes: Task 1/2에서 만든 `tools/video_engine.py`, `core.engine.apply_population_fit_look_video_frame` (이름만 문서에 인용, 코드 변경 없음)

- [ ] **Step 1: `docs/project_structure.md`에 테이블 행 추가**

`| `tools/raw_pipeline.py` | ... |` 행 바로 다음 줄에 추가:

```
| `tools/video_engine.py` | 비디오 파일(mp4)에 population-fit 브랜드 룩(10개: canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony) 프레임 단위 적용 CLI - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (오디오 미보존, CLAHE 생략 - 사진 모드와 동일 출력 아님) |
```

`| `core/log_pipeline.py` | ... |` 행 바로 다음 줄에 추가:

```
| `core/engine.py`의 `apply_population_fit_look_video_frame()` | population-fit 브랜드 엔진의 비디오 전용 변형 - CLAHE(프레임별 적응형 로컬 대비 보정)를 생략해 프레임 간 깜빡임을 피한다. `tools/video_engine.py`가 사용 |
```

- [ ] **Step 2: `docs/project_structure.en.md`에 대응 영문 행 추가**

`| `tools/raw_pipeline.py` | ... |` 행 바로 다음 줄에 추가:

```
| `tools/video_engine.py` | Applies a population-fit brand look to a video file (mp4) frame-by-frame, CLI - `python3 -m tools.video_engine input.mp4 output.mp4 --brand canon` (10 brands: canon/leica/nikon/olympus/panasonic/pentax/phaseone/ricoh_gr/sigma/sony; audio not preserved; skips CLAHE - not identical output to photo mode) |
```

`| `core/log_pipeline.py` | ... |` 행 바로 다음 줄에 추가:

```
| `core/engine.py`'s `apply_population_fit_look_video_frame()` | Video-only variant of the population-fit brand engine - skips CLAHE (per-frame adaptive local-contrast correction) to avoid inter-frame flicker. Used by `tools/video_engine.py` |
```

- [ ] **Step 3: `README.md`에 섹션 추가**

"## Browser demo (not measured data)" 섹션 바로 앞에 새 섹션 삽입:

```markdown
## Video engine (frame-by-frame, engineering reuse - not a new measurement)

`tools/video_engine.py` applies an already-measured population-fit brand look to an actual video file (mp4), frame by frame - it does not add any new color-science measurement, it reuses the 10 population-fit brands' `apply_*_look()` (Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony; Fujifilm and Hasselblad use different pipelines and are out of scope for this CLI - see [docs/superpowers/specs/2026-07-26-video-engine-design.md](docs/superpowers/specs/2026-07-26-video-engine-design.md)).

```
python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
```

**Known limitations**: (1) audio tracks are not preserved (this environment has no `ffmpeg` CLI/`moviepy`/audio-mux tooling - `cv2`'s built-in FFmpeg only covers video frames); (2) the video path skips CLAHE (per-frame adaptive local-contrast correction) to avoid inter-frame flicker, so its output is not identical to the photo-mode `apply_*_look()`; (3) this is not a video-specific color-science measurement - whether a camera brand actually renders video differently from its still JPEGs (different tone curve, sharpening, etc.) is unverified; (4) only validated against synthetic test video in this environment - no real camera mp4/mov sample was available for a smoke test.
```

- [ ] **Step 4: `README.ko.md`에 대응 한국어 섹션 추가**

"## 브라우저 데모 (실측 데이터 아님)" 섹션(또는 그에 대응하는 한국어 제목) 바로 앞에 삽입:

```markdown
## 비디오 엔진 (프레임 단위, 기존 측정 재사용 - 새 측정 아님)

`tools/video_engine.py`는 이미 측정된 population-fit 브랜드 룩을 실제 비디오 파일(mp4)에 프레임 단위로 적용한다 - 새 색과학 측정을 하지 않고 10개 population-fit 브랜드(Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony)의 `apply_*_look()`을 재사용한다(Fujifilm/Hasselblad는 별도 파이프라인이라 이 CLI 범위 밖 - [docs/superpowers/specs/2026-07-26-video-engine-design.md](docs/superpowers/specs/2026-07-26-video-engine-design.md) 참고).

```
python3 -m tools.video_engine input.mp4 output.mp4 --brand canon
```

**알려진 한계**: (1) 오디오 트랙 미보존(이 환경에 `ffmpeg` CLI/`moviepy` 등 오디오 mux 도구가 없음 - `cv2` 내장 FFmpeg는 비디오 프레임만 다룸); (2) 비디오 경로는 프레임 간 깜빡임을 피하려고 CLAHE(프레임별 적응형 로컬 대비 보정)를 생략해서 사진 모드 `apply_*_look()`과 동일한 출력이 아님; (3) 비디오 전용 색과학 측정이 아님 - 카메라 브랜드가 정지 JPEG와 실제 영상에서 다른 색처리(톤커브/샤프닝 등)를 쓸 수 있다는 점은 검증되지 않음; (4) 이 환경에 실제 카메라 mp4/mov 샘플이 없어 합성 테스트 비디오로만 검증됨.
```

- [ ] **Step 5: 전체 테스트 스위트 실행**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 총 개수가 Task 1/2에서 추가한 16개(엔진 5 + 비디오엔진 11)만큼 늘어나 있음(369 + 16 = 385 이상 - 다른 미완료 작업이 없다면 정확히 385)

- [ ] **Step 6: 커밋 + 푸시**

```bash
git add README.md README.ko.md docs/project_structure.md docs/project_structure.en.md
git commit -m "Document video_engine CLI in README/project_structure (ko+en)"
git push -u origin claude/unknown-character-0x48vp
```
