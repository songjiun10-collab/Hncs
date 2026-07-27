# 비디오 엔진에 Fujifilm/Hasselblad 브랜드 추가 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `tools/video_engine.py`의 지원 브랜드를 기존 10개(population-fit)에서 Fujifilm 10개 프리셋 + Hasselblad `apply_hncs`까지 21개로 확장한다.

**Architecture:** Fuji 프리셋 10개 중 CLAHE를 쓰는 건 `apply_pro_neg_hi` 하나뿐이라 나머지 9개는 수정 없이 그대로 재사용한다. `apply_pro_neg_hi`와 Hasselblad의 `apply_hncs`에는 CLAHE를 생략한 비디오 전용 변형을 새로 추가한다(v1의 `apply_population_fit_look_video_frame()`과 같은 패턴). 이미 리뷰를 통과한 `process_video()`/`process_video_with_audio()`는 한 줄도 건드리지 않고, 같은 I/O 구조를 가진 `process_video_v2()`/`process_video_v2_with_audio()`를 나란히 추가해서 확장 브랜드를 처리한다(사용자가 명시적으로 이 방향을 선택 - 코드 중복을 감수하고 이미 검증된 코드를 보존).

**Tech Stack:** 기존 의존성만 사용(`cv2`, `numpy`, `imageio-ffmpeg`) - 새 의존성 없음.

## Global Constraints

- **`process_video()`, `process_video_with_audio()`, `brand_video_params()`, `_BRAND_FUNCTIONS`, `SUPPORTED_BRANDS`(전부 `tools/video_engine.py`, 기존)는 수정 금지.** 새 기능은 나란히 추가하는 새 함수/딕셔너리로만 구현한다.
- **`brands/fuji.py`의 기존 10개 함수, `brands/hasselblad.py`의 기존 `apply_hncs`는 수정 금지.** 각 파일에 새 `*_video_frame()` 함수를 추가만 한다.
- **Fuji 9개(CLAHE 없는 프리셋)는 새 video_frame 변형 없이 원본 함수를 그대로 쓴다** - `apply_astia`/`apply_pro_neg_std`/`apply_eterna_cinema`/`apply_eterna_bleach_bypass`/`apply_nostalgic_neg`/`apply_reala_ace`/`apply_classic_negative`/`apply_acros`/`apply_monochrome`.
- **CLAHE 생략 변형이 필요한 건 `apply_pro_neg_hi_video_frame()`(`brands/fuji.py`)과 `apply_hncs_video_frame()`(`brands/hasselblad.py`) 2개뿐** - 각각 원본 함수에서 `cv2.createCLAHE(...)` / `clahe.apply(...)` 두 줄만 뺀 것, 나머지 로직은 원본과 동일해야 한다.
- **그레이스케일 반환 함수(`apply_acros`/`apply_monochrome`)는 비디오 프레임으로 쓰기 전에 3채널 BGR로 변환한다** - `cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)`.
- **Hasselblad는 `apply_hncs`(Stable) 하나만 지원한다** - day/night/learned 프리셋은 범위 밖.
- **`apply_acros`의 `filter_type` 파라미터는 노출하지 않는다** - 항상 기본값(`'none'`)만 사용, CLI에 새 옵션 추가 안 함.
- **브랜드 이름은 플랫 네임스페이스**: `fuji_astia`, `fuji_pro_neg_std`, `fuji_pro_neg_hi`, `fuji_eterna_cinema`, `fuji_eterna_bleach_bypass`, `fuji_nostalgic_neg`, `fuji_reala_ace`, `fuji_classic_negative`, `fuji_acros`, `fuji_monochrome`, `hasselblad` (11개, 정확히 이 이름).
- **`process_video_v2_with_audio()`는 `process_video_with_audio()`와 동일하게 `.mp4` 아닌 출력 확장자를 `ValueError`로 즉시 거부한다**(전체 그레이딩 후 mux 단계에서야 실패하는 낭비를 막기 위해 - 오디오 보존 플랜의 최종 리뷰에서 확정된 것과 동일한 방어).
- 테스트는 `unittest.TestCase` 스타일(프로젝트 관례, pytest 미사용).
- 각 태스크 종료 시 `python3 -m unittest discover -s tests`가 그린이어야 한다(현재 400개 - 태스크가 늘려간다).
- 문서는 README.md/README.ko.md 둘 다 갱신(이중언어 동시 유지 관례).

---

### Task 1: `apply_pro_neg_hi_video_frame()` + `apply_hncs_video_frame()`

**Files:**
- Modify: `brands/fuji.py` (추가만 - 기존 10개 함수 수정 금지)
- Modify: `brands/hasselblad.py` (추가만 - 기존 `apply_hncs` 수정 금지)
- Test: `tests/test_video_engine.py` (기존 파일에 추가)
- Test: `tests/test_brands.py` (기존 `BRAND_LOOKS`/`FUJI_COLOR_PRESETS` 등 회귀 스윕에 2개 함수 이름 추가)

**Interfaces:**
- Consumes: `brands.fuji.apply_pro_neg_hi(img_bgr, sat_mult=1.10, contrast_n=1.7, clahe_clip=1.5)`(기존, 참고용 - CLAHE 유무 비교 테스트에서 사용), `brands.hasselblad.apply_hncs(img_bgr, toe_lift=0.001, shoulder_start=0.78, white_point=1.0, clahe_clip=1.25, exposure_gamma=0.7)`(기존, 동일)
- Produces: `apply_pro_neg_hi_video_frame(img_bgr, sat_mult=1.10, contrast_n=1.7) -> np.ndarray`(`brands/fuji.py`), `apply_hncs_video_frame(img_bgr, toe_lift=0.001, shoulder_start=0.78, white_point=1.0, exposure_gamma=0.7) -> np.ndarray`(`brands/hasselblad.py`) - Task 2가 이 두 함수를 프레임마다 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_video_engine.py` 상단 import 블록(기존 `from tools.video_engine import (...)` 다음)에 추가:

```python
from brands.fuji import apply_pro_neg_hi, apply_pro_neg_hi_video_frame
from brands.hasselblad import apply_hncs, apply_hncs_video_frame
from core.curve import film_curve, s_curve
from core.lut import ensure_uint8
```

파일 끝의 `if __name__ == "__main__":` **바로 위**에 새 테스트 클래스 2개 추가:

```python
class TestApplyProNegHiVideoFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_pro_neg_hi_video_frame(self.img)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_pro_neg_hi_video_frame(self.img)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_differs_from_photo_mode_with_clahe(self):
        photo_out = apply_pro_neg_hi(self.img)
        video_out = apply_pro_neg_hi_video_frame(self.img)
        self.assertFalse(np.array_equal(photo_out, video_out))

    def test_matches_manual_reconstruction_without_clahe(self):
        img = ensure_uint8(self.img)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        y = s_curve(x, n=1.7)
        lut = np.clip(y * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)
        img_u8 = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        hsv = cv2.cvtColor(img_u8, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.10, 0, 255)
        expected = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

        out = apply_pro_neg_hi_video_frame(self.img)
        np.testing.assert_array_equal(out, expected)


class TestApplyHncsVideoFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(42)
        self.img = rng.integers(0, 255, (128, 128, 3), dtype=np.uint8)

    def test_preserves_shape_and_dtype(self):
        out = apply_hncs_video_frame(self.img)
        self.assertEqual(out.shape, self.img.shape)
        self.assertEqual(out.dtype, self.img.dtype)

    def test_does_not_mutate_input(self):
        img_copy = self.img.copy()
        apply_hncs_video_frame(self.img)
        np.testing.assert_array_equal(self.img, img_copy)

    def test_differs_from_photo_mode_with_clahe(self):
        photo_out = apply_hncs(self.img)
        video_out = apply_hncs_video_frame(self.img)
        self.assertFalse(np.array_equal(photo_out, video_out))

    def test_matches_manual_reconstruction_without_clahe(self):
        lab = cv2.cvtColor(self.img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        x = np.arange(256, dtype=np.float32) / 255.0
        exp_lut = np.clip((x ** 0.7) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, exp_lut)
        x2 = np.arange(256, dtype=np.float32) / 255.0
        lut = np.clip(film_curve(x2, 0.001, 0.78, 1.0) * 255, 0, 255).astype(np.uint8)
        l = cv2.LUT(l, lut)
        expected = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        out = apply_hncs_video_frame(self.img)
        np.testing.assert_array_equal(out, expected)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: `ImportError: cannot import name 'apply_pro_neg_hi_video_frame' from 'brands.fuji'` 로 FAIL

- [ ] **Step 3: 최소 구현 작성**

`brands/fuji.py` 맨 끝(파일 마지막 줄, `apply_classic_negative()` 정의 다음)에 추가:

```python


# ==========================================
# 10. PRO Neg. Hi 비디오 전용 변형 (CLAHE 생략) - tools/video_engine.py가 사용
# ==========================================
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

`brands/hasselblad.py` 맨 끝(파일 마지막 줄, `apply_hncs()` 정의 다음)에 추가:

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

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: 전부 PASS (기존 26개 + 새 8개, 총 34개)

- [ ] **Step 5: `tests/test_brands.py`의 회귀 스윕에 두 함수 추가**

`tests/test_brands.py`의 `BRAND_LOOKS` 리스트(파일 상단)에 다음 항목 추가(다른 항목들과 같은 위치, 리스트 어디든 - 마지막에 추가):

```python
    ("brands.hasselblad", "apply_hncs_video_frame"),
```

`FUJI_COLOR_PRESETS` 리스트 끝에 추가:

```python
    "apply_pro_neg_hi_video_frame",
```

이 파일이 `FUJI_COLOR_PRESETS`를 순회하는 방식(예: `getattr(self.fuji, name)`)을 그대로 타므로 새 함수도 자동으로 shape/dtype 회귀 테스트 대상이 된다 - 추가 코드 불필요.

- [ ] **Step 6: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_brands -v`
Expected: 전부 PASS (새로 추가된 2개 이름이 기존 순회 로직에 걸려 통과)

- [ ] **Step 7: 전체 테스트 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 총 408개(기존 400 + `test_video_engine.py` 8개 - `test_brands.py`는 기존 순회 테스트 메서드 수 자체는 안 늘어나고 순회 대상만 늘어남, 새 assert 실행이지 새 테스트 메서드가 아님)

- [ ] **Step 8: 커밋**

```bash
git add brands/fuji.py brands/hasselblad.py tests/test_video_engine.py tests/test_brands.py
git commit -m "Add CLAHE-free video-frame variants for Fuji Pro Neg Hi and Hasselblad HNCS"
```

---

### Task 2: `process_video_v2()`/`process_video_v2_with_audio()` + 11개 브랜드 CLI 확장

**Files:**
- Modify: `tools/video_engine.py` (추가 + `main()`의 분기 로직만 수정 - `process_video`/`process_video_with_audio`/`brand_video_params`/`_BRAND_FUNCTIONS`/`SUPPORTED_BRANDS`는 수정 금지)
- Test: `tests/test_video_engine.py` (기존 파일에 추가)

**Interfaces:**
- Consumes: `apply_astia`, `apply_pro_neg_std`, `apply_eterna_cinema`, `apply_eterna_bleach_bypass`, `apply_nostalgic_neg`, `apply_reala_ace`, `apply_classic_negative`, `apply_acros`, `apply_monochrome`(전부 `brands/fuji.py`, 기존, 시그니처 `(img_bgr) -> np.ndarray`, `apply_acros`/`apply_monochrome`만 1채널 반환), `apply_pro_neg_hi_video_frame`(`brands/fuji.py`, Task 1), `apply_hncs_video_frame`(`brands/hasselblad.py`, Task 1), `mux_audio(video_only_path, audio_source_path, final_output_path) -> None`(`tools/video_engine.py`, 기존, 수정 없음)
- Produces: `EXPANDED_SUPPORTED_BRANDS: frozenset`(11개), `process_video_v2(input_path, output_path, brand_name, progress_every=100) -> int`, `process_video_v2_with_audio(input_path, output_path, brand_name, progress_every=100) -> int` - Task 3의 `main()` 분기가 이 두 함수를 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_video_engine.py`의 `from tools.video_engine import (...)` import 줄을 다음으로 교체:

```python
from tools.video_engine import (
    EXPANDED_SUPPORTED_BRANDS, SUPPORTED_BRANDS, brand_video_params,
    mux_audio, process_video, process_video_v2, process_video_v2_with_audio,
    process_video_with_audio,
)
```

`tools.video_engine`에서 `_grayscale_to_bgr_frame`도 테스트가 직접 써야 하므로, 같은 import 블록 **다음 줄**에 추가:

```python
from tools.video_engine import _grayscale_to_bgr_frame
```

`TestApplyHncsVideoFrame` 클래스(Task 1에서 추가) **바로 다음**, `if __name__ == "__main__":` **바로 위**에 새 테스트 클래스들 추가:

```python
class TestGrayscaleToBgrFrame(unittest.TestCase):
    def test_wraps_grayscale_output_as_three_channel_bgr(self):
        def fake_gray_func(img_bgr):
            return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        wrapped = _grayscale_to_bgr_frame(fake_gray_func)
        rng = np.random.default_rng(1)
        img = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
        out = wrapped(img)

        self.assertEqual(out.ndim, 3)
        self.assertEqual(out.shape, (32, 32, 3))
        expected_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np.testing.assert_array_equal(out[:, :, 0], expected_gray)
        np.testing.assert_array_equal(out[:, :, 1], expected_gray)
        np.testing.assert_array_equal(out[:, :, 2], expected_gray)


class TestExpandedBrandNames(unittest.TestCase):
    def test_expanded_supported_brands_has_exactly_eleven(self):
        self.assertEqual(len(EXPANDED_SUPPORTED_BRANDS), 11)
        self.assertEqual(EXPANDED_SUPPORTED_BRANDS, frozenset({
            "fuji_astia", "fuji_pro_neg_std", "fuji_pro_neg_hi",
            "fuji_eterna_cinema", "fuji_eterna_bleach_bypass",
            "fuji_nostalgic_neg", "fuji_reala_ace", "fuji_classic_negative",
            "fuji_acros", "fuji_monochrome", "hasselblad",
        }))

    def test_no_overlap_with_original_supported_brands(self):
        self.assertEqual(SUPPORTED_BRANDS & EXPANDED_SUPPORTED_BRANDS, frozenset())

    def test_all_brands_union_has_21(self):
        self.assertEqual(len(SUPPORTED_BRANDS | EXPANDED_SUPPORTED_BRANDS), 21)


class TestProcessVideoV2AllBrands(unittest.TestCase):
    """11개 확장 브랜드 전부에 대해 가벼운 스모크(출력 생성+열림)만
    확인 - 깊은 검증은 TestProcessVideoV2Representative에서 대표
    브랜드 4개(fuji_astia/fuji_pro_neg_hi/fuji_acros/hasselblad)만."""
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.input_path = os.path.join(self.tmpdir, "input.mp4")
        _make_synthetic_video(self.input_path)

    def test_every_expanded_brand_produces_readable_output(self):
        for brand in EXPANDED_SUPPORTED_BRANDS:
            with self.subTest(brand=brand):
                output_path = os.path.join(self.tmpdir, f"output_{brand}.mp4")
                frame_count = process_video_v2(self.input_path, output_path, brand)
                self.assertEqual(frame_count, 10)
                cap = cv2.VideoCapture(output_path)
                self.assertTrue(cap.isOpened())
                cap.release()


class TestProcessVideoV2Representative(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)
        self.input_path = os.path.join(self.tmpdir, "input.mp4")
        self.output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video(self.input_path)

    def test_fuji_astia_matches_input_resolution_and_frame_count(self):
        process_video_v2(self.input_path, self.output_path, "fuji_astia")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_WIDTH),
                          cap_out.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_HEIGHT),
                          cap_out.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FRAME_COUNT),
                          cap_out.get(cv2.CAP_PROP_FRAME_COUNT))
        self.assertEqual(cap_in.get(cv2.CAP_PROP_FPS), cap_out.get(cv2.CAP_PROP_FPS))
        cap_in.release()
        cap_out.release()

    def test_fuji_astia_output_frames_differ_from_input(self):
        process_video_v2(self.input_path, self.output_path, "fuji_astia")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        ok_in, frame_in = cap_in.read()
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_in)
        self.assertTrue(ok_out)
        self.assertFalse(np.array_equal(frame_in, frame_out))
        cap_in.release()
        cap_out.release()

    def test_fuji_pro_neg_hi_output_frames_differ_from_input(self):
        process_video_v2(self.input_path, self.output_path, "fuji_pro_neg_hi")
        cap_in = cv2.VideoCapture(self.input_path)
        cap_out = cv2.VideoCapture(self.output_path)
        ok_in, frame_in = cap_in.read()
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_in)
        self.assertTrue(ok_out)
        self.assertFalse(np.array_equal(frame_in, frame_out))
        cap_in.release()
        cap_out.release()

    def test_fuji_acros_output_is_three_channel_bgr(self):
        process_video_v2(self.input_path, self.output_path, "fuji_acros")
        cap_out = cv2.VideoCapture(self.output_path)
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_out)
        self.assertEqual(frame_out.ndim, 3)
        self.assertEqual(frame_out.shape[2], 3)
        cap_out.release()

    def test_fuji_acros_output_channels_are_equal(self):
        process_video_v2(self.input_path, self.output_path, "fuji_acros")
        cap_out = cv2.VideoCapture(self.output_path)
        ok_out, frame_out = cap_out.read()
        self.assertTrue(ok_out)
        np.testing.assert_array_equal(frame_out[:, :, 0], frame_out[:, :, 1])
        np.testing.assert_array_equal(frame_out[:, :, 1], frame_out[:, :, 2])
        cap_out.release()

    def test_hasselblad_output_frames_differ_from_input(self):
        process_video_v2(self.input_path, self.output_path, "hasselblad")
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
            process_video_v2(self.input_path, self.output_path, "fuji_provia")

    def test_missing_input_file_raises_io_error(self):
        missing_path = os.path.join(self.tmpdir, "does_not_exist.mp4")
        with self.assertRaises(IOError):
            process_video_v2(missing_path, self.output_path, "fuji_astia")

    def test_output_in_nonexistent_directory_raises_io_error(self):
        bad_output_path = os.path.join(self.tmpdir, "no_such_subdir", "output.mp4")
        with self.assertRaises(IOError):
            process_video_v2(self.input_path, bad_output_path, "fuji_astia")


class TestProcessVideoV2WithAudio(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

    def test_input_with_audio_preserves_audio_in_output(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        frame_count = process_video_v2_with_audio(input_path, output_path, "fuji_astia")

        self.assertGreater(frame_count, 0)
        self.assertTrue(_has_audio_stream(output_path))

    def test_output_video_matches_direct_process_video_v2_output(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        direct_output_path = os.path.join(self.tmpdir, "direct_output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        process_video_v2_with_audio(input_path, output_path, "hasselblad")
        process_video_v2(input_path, direct_output_path, "hasselblad")

        cap_out = cv2.VideoCapture(output_path)
        cap_direct = cv2.VideoCapture(direct_output_path)
        ok_out, frame_out = cap_out.read()
        ok_direct, frame_direct = cap_direct.read()
        self.assertTrue(ok_out)
        self.assertTrue(ok_direct)
        np.testing.assert_array_equal(frame_out, frame_direct)
        cap_out.release()
        cap_direct.release()

    def test_no_leftover_temp_directories(self):
        scratch_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch_root, ignore_errors=True)
        original_tempdir = tempfile.tempdir
        tempfile.tempdir = scratch_root
        self.addCleanup(setattr, tempfile, "tempdir", original_tempdir)

        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        process_video_v2_with_audio(input_path, output_path, "fuji_astia")
        self.assertEqual(os.listdir(scratch_root), [])

    def test_non_mp4_output_extension_raises_value_error(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.webm")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        with self.assertRaises(ValueError):
            process_video_v2_with_audio(input_path, output_path, "fuji_astia")
        self.assertFalse(os.path.exists(output_path))

    def test_unsupported_brand_raises_value_error(self):
        input_path = os.path.join(self.tmpdir, "input.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        _make_synthetic_video_with_audio(input_path, duration=1, fps=24)

        with self.assertRaises(ValueError):
            process_video_v2_with_audio(input_path, output_path, "fuji_provia")

    def test_missing_input_raises_io_error(self):
        missing_path = os.path.join(self.tmpdir, "does_not_exist.mp4")
        output_path = os.path.join(self.tmpdir, "output.mp4")
        with self.assertRaises(IOError):
            process_video_v2_with_audio(missing_path, output_path, "fuji_astia")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: `ImportError: cannot import name 'EXPANDED_SUPPORTED_BRANDS' from 'tools.video_engine'` 로 FAIL

- [ ] **Step 3: 최소 구현 작성**

`tools/video_engine.py`의 기존 import 블록에서 `from brands.sony import apply_sony_look` **다음 줄**에 추가(Fuji/Hasselblad import):

```python
from brands.fuji import (
    apply_astia, apply_pro_neg_std, apply_pro_neg_hi_video_frame,
    apply_eterna_cinema, apply_eterna_bleach_bypass, apply_nostalgic_neg,
    apply_reala_ace, apply_classic_negative, apply_acros, apply_monochrome,
)
from brands.hasselblad import apply_hncs_video_frame
```

`SUPPORTED_BRANDS = frozenset(_BRAND_FUNCTIONS)` 줄 **바로 다음**(즉 `def brand_video_params(brand_name):` **바로 앞**)에 추가:

```python
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
```

`process_video_with_audio()` 함수 정의 **바로 다음**, `def main():` **바로 앞**에 추가:

```python
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
        raise ValueError(
            f"출력 파일은 .mp4만 지원함: {output_path!r}"
        )
    tmp_dir = tempfile.mkdtemp()
    tmp_video_only = os.path.join(tmp_dir, "video_only.mp4")
    try:
        frame_count = process_video_v2(input_path, tmp_video_only, brand_name, progress_every)
        mux_audio(tmp_video_only, input_path, output_path)
        return frame_count
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_video_engine -v`
Expected: 전부 PASS (Task 1까지 34개 + 이 태스크의 새 테스트 - `TestGrayscaleToBgrFrame` 1 + `TestExpandedBrandNames` 3 + `TestProcessVideoV2AllBrands` 1 + `TestProcessVideoV2Representative` 9 + `TestProcessVideoV2WithAudio` 6 = 20개, 총 54개)

- [ ] **Step 5: 전체 테스트 스위트 확인**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 총 428개(기존 400 + Task 1의 8 + 이 태스크의 20)

- [ ] **Step 6: 커밋**

```bash
git add tools/video_engine.py tests/test_video_engine.py
git commit -m "Add process_video_v2()/process_video_v2_with_audio() for 11 expanded brands"
```

---

### Task 3: `main()` CLI 분기 + 문서화 + 전체 테스트 스위트 확인 + 푸시

**Files:**
- Modify: `tools/video_engine.py` (`main()`의 분기 로직 + 모듈 docstring)
- Modify: `README.md`
- Modify: `README.ko.md`

**Interfaces:**
- Consumes: `SUPPORTED_BRANDS`(기존), `EXPANDED_SUPPORTED_BRANDS`(Task 2), `process_video_with_audio`(기존), `process_video_v2_with_audio`(Task 2)

- [ ] **Step 1: `main()`의 분기 로직 수정**

현재(`tools/video_engine.py`의 `main()` 함수):
```python
def main():
    parser = argparse.ArgumentParser(
        description="비디오 파일에 population-fit 브랜드 룩 적용 (오디오 트랙 기본 보존)")
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

다음으로 교체:
```python
def main():
    parser = argparse.ArgumentParser(
        description="비디오 파일에 브랜드 룩 적용 (오디오 트랙 기본 보존)")
    parser.add_argument("input", help="입력 비디오 파일 경로")
    parser.add_argument("output", help="출력 비디오 파일 경로 (.mp4)")
    all_brands = sorted(SUPPORTED_BRANDS | EXPANDED_SUPPORTED_BRANDS)
    parser.add_argument("--brand", required=True, choices=all_brands,
                         help="적용할 브랜드 룩")
    args = parser.parse_args()

    try:
        if args.brand in SUPPORTED_BRANDS:
            frame_count = process_video_with_audio(args.input, args.output, args.brand)
        else:
            frame_count = process_video_v2_with_audio(args.input, args.output, args.brand)
    except (IOError, ValueError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"완료: {frame_count}프레임 -> {args.output}")
```

(바뀐 것: `description=`에서 "population-fit " 삭제, `choices=`가 21개 합집합으로 확장, `try` 블록 안에서 브랜드 소속에 따라 두 함수 중 하나를 호출하도록 분기 - 그 외 argparse 인자 정의/`except`/출력 메시지는 무변경.)

- [ ] **Step 2: `tools/video_engine.py` 모듈 docstring 수정**

현재(파일 맨 위):
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
```

두 번째 문단(지원 브랜드 10개뿐)을 다음으로 교체:

```python
지원 브랜드는 21개: population-fit 10개(canon/leica/nikon/olympus/
panasonic/pentax/phaseone/ricoh_gr/sigma/sony, core.engine.
apply_population_fit_look()을 공유, process_video()/
process_video_with_audio()가 처리) + Fuji/Hasselblad 11개(fuji_astia/
fuji_pro_neg_std/fuji_pro_neg_hi/fuji_eterna_cinema/
fuji_eterna_bleach_bypass/fuji_nostalgic_neg/fuji_reala_ace/
fuji_classic_negative/fuji_acros/fuji_monochrome/hasselblad,
process_video_v2()/process_video_v2_with_audio()가 처리 - Fuji 10개
프리셋 중 CLAHE를 쓰는 건 apply_pro_neg_hi 하나뿐이라 나머지 9개는
수정 없이 재사용하고, apply_pro_neg_hi와 Hasselblad apply_hncs만 CLAHE
생략 변형을 추가했다. 자세한 조사 내용은
docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md
참고). Hasselblad는 apply_hncs(Stable)만 지원 - day/night/learned
프리셋은 범위 밖.
```

(첫 번째 문단, 세 번째 문단(비디오 모드 vs 사진 모드 차이), 네 번째 문단(오디오 보존)은 그대로 유지.)

- [ ] **Step 3: `README.md` "Video engine" 섹션 수정**

현재 문단(`## Video engine ...` 섹션의 첫 문단):
```
`tools/video_engine.py` applies an already-measured population-fit brand look to an actual video file (mp4), frame by frame - it does not add any new color-science measurement, it reuses the 10 brands' measured tone-curve parameters (the default arguments of their `apply_*_look()`) (Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony; Fujifilm and Hasselblad use different pipelines and are out of scope for this CLI - see [docs/superpowers/specs/2026-07-26-video-engine-design.md](docs/superpowers/specs/2026-07-26-video-engine-design.md)).
```

다음으로 교체:
```
`tools/video_engine.py` applies an already-measured brand look to an actual video file (mp4), frame by frame - it does not add any new color-science measurement. 21 brands are supported: the 10 population-fit brands' measured tone-curve parameters (Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony), plus Fujifilm's 10 film-simulation presets and Hasselblad's `apply_hncs` (`fuji_astia`/`fuji_pro_neg_std`/`fuji_pro_neg_hi`/`fuji_eterna_cinema`/`fuji_eterna_bleach_bypass`/`fuji_nostalgic_neg`/`fuji_reala_ace`/`fuji_classic_negative`/`fuji_acros`/`fuji_monochrome`/`hasselblad`) - see [docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md](docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md) for which presets needed a CLAHE-free variant and which didn't.
```

- [ ] **Step 4: `README.ko.md` 대응 섹션 수정**

현재 문단(`## 비디오 엔진 ...` 섹션의 첫 문단):
```
`tools/video_engine.py`는 이미 측정된 population-fit 브랜드 룩을 실제 비디오 파일(mp4)에 프레임 단위로 적용한다 - 새 색과학 측정을 하지 않고 10개 population-fit 브랜드(Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony) `apply_*_look()`의 측정된 톤커브 파라미터(기본 인자값)를 재사용한다(Fujifilm/Hasselblad는 별도 파이프라인이라 이 CLI 범위 밖 - [docs/superpowers/specs/2026-07-26-video-engine-design.md](docs/superpowers/specs/2026-07-26-video-engine-design.md) 참고).
```

다음으로 교체:
```
`tools/video_engine.py`는 이미 측정된 브랜드 룩을 실제 비디오 파일(mp4)에 프레임 단위로 적용한다 - 새 색과학 측정을 하지 않는다. 21개 브랜드를 지원: 10개 population-fit 브랜드(Canon/Leica/Nikon/Olympus/Panasonic/Pentax/Phase One/Ricoh GR/Sigma/Sony)의 측정된 톤커브 파라미터에 더해, Fujifilm 필름 시뮬레이션 프리셋 10종과 Hasselblad `apply_hncs`(`fuji_astia`/`fuji_pro_neg_std`/`fuji_pro_neg_hi`/`fuji_eterna_cinema`/`fuji_eterna_bleach_bypass`/`fuji_nostalgic_neg`/`fuji_reala_ace`/`fuji_classic_negative`/`fuji_acros`/`fuji_monochrome`/`hasselblad`) - 어떤 프리셋이 CLAHE 생략 변형을 필요로 했고 어떤 건 그대로 재사용했는지는 [docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md](docs/superpowers/specs/2026-07-26-video-engine-fuji-hasselblad-design.md) 참고.
```

- [ ] **Step 5: 전체 테스트 스위트 실행**

Run: `python3 -m unittest discover -s tests`
Expected: 전부 PASS, 428개(Task 1/2에서 늘어난 개수 그대로 - 이 태스크는 `main()`의 분기 로직 + 문서만 바꿔 자동 테스트 개수는 불변. 단, `main()`을 CLI로 실제 실행하는 수동 스모크는 Step 6에서 진행)

- [ ] **Step 6: 합성 비디오로 CLI 수동 스모크 테스트 (확장 브랜드 + 기존 브랜드 둘 다)**

Run:
```bash
python3 -c "
from tests.test_video_engine import _make_synthetic_video_with_audio
_make_synthetic_video_with_audio('/tmp/smoke_input2.mp4', duration=1, fps=24)
"
python3 -m tools.video_engine /tmp/smoke_input2.mp4 /tmp/smoke_out_fuji.mp4 --brand fuji_astia
python3 -m tools.video_engine /tmp/smoke_input2.mp4 /tmp/smoke_out_hasselblad.mp4 --brand hasselblad
python3 -m tools.video_engine /tmp/smoke_input2.mp4 /tmp/smoke_out_canon.mp4 --brand canon
```

Expected: 세 명령 모두 `완료: 24프레임 -> ...` 출력 후 exit code 0 (확장 브랜드 2개 + 기존 브랜드 1개 모두 정상 동작 확인 - `main()`의 분기 로직이 두 경로 다 올바르게 타는지 실측 확인).

- [ ] **Step 7: 커밋 + 푸시**

```bash
git add tools/video_engine.py README.md README.ko.md
git commit -m "Wire main() to route 21 brands between the original and expanded video pipelines"
git push -u origin claude/unknown-character-0x48vp
```
