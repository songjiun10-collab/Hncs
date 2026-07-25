# 카메라 네이티브 색매트릭스 + DCP 프로필 내보내기 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카메라 네이티브 RGB 공간에서 ColorChecker 차트로 3×3 색매트릭스를 피팅해 libraw 내장 매트릭스와 교차검증으로 비교하고(Phase 1), 이겼을 때만 그 매트릭스를 담은 Adobe `.dcp` 카메라 프로필을 실제로 생성한다(Phase 2).

**Architecture:** libraw의 색매트릭스·WB를 우회하는 새 디코드 경로(`decode_raw_native`)를 추가하고, DCP의 기준 공간인 XYZ(D50) 참조값(`reference_patches_xyz_d50`)을 새로 만든 뒤, 기존 `raw_baseline.fit_color_matrix()`(소스/타깃 제네릭)를 그대로 재사용해 피팅한다. `.dcp`는 TIFF 구조 파일이라 Python `struct`로 직접 쓴다(새 의존성 0). 기존 `decode_raw()`/`raw_baseline_matrix`/`hasselblad.json`은 건드리지 않는다.

**Tech Stack:** 기존 의존성만 사용 - `rawpy`, `numpy`, `colour-science`, `opencv-python`(cv2.mcc), 그리고 `exiftool` 서브프로세스(프로젝트가 이미 `hybrid_engine/utils/exif.py`에서 쓰는 방식).

## Global Constraints

- **새 의존성 추가 금지.** `rawpy`/`numpy`/`colour`/`cv2`와 `exiftool` 서브프로세스만 사용. `.dcp` 쓰기는 표준 라이브러리 `struct`로 직접 구현한다(DNG SDK나 tifffile 등 도입 금지).
- **기존 코드 보존.** `hybrid_engine/utils/io.py`의 `decode_raw()`, `hybrid_engine/core/chart_baseline.py`의 `reference_patches_linear_srgb()`/`patch_delta_e()`, `hybrid_engine/core/raw_baseline.py`의 모든 함수, `hybrid_engine/assets/profiles/hasselblad.json`은 **수정하지 않는다** - 전부 추가만 한다. 기존 함수들은 "카메라 JPEG 룩 근사"라는 다른 목적을 정상 수행 중이다.
- **DCP 프로필 파일 생성은 Phase 1 결과에 게이트.** 차트 피팅 매트릭스가 leave-one-image-out 교차검증 기준으로 libraw 내장 매트릭스를 이기지 못하면 `.dcp` 파일을 생성/커밋하지 않는다. `core/dcp_export.py` writer 코드 자체는 결과와 무관하게 만들어 남긴다(매트릭스를 인자로 받는 범용 도구).
- **`ForwardMatrix1`은 기본적으로 넣지 않는다.** `write_dcp()`가 옵션 인자로 지원하되 기본값은 `None`. DNG 스펙상 ForwardMatrix는 카메라 중립점을 D50 백색점으로 정확히 매핑하는 정규화 제약이 있고 이 환경에서 Lightroom으로 확인할 방법이 없다. `ColorMatrix1`만 있는 프로필도 유효하므로, 추측해서 넣기보다 빼는 쪽을 택한다.
- **`CalibrationIlluminant1`은 추정값이며 그렇게 라벨링한다.** manifest의 `illuminant` 칼럼이 10장 전부 비어있어(측정 안 됨) `AsShotNeutral`에서 역산한 추정 CCT를 가장 가까운 EXIF LightSource enum으로 매핑한다.
- **Lightroom 실제 렌더링은 미검증으로 남는다.** 구조 검증(exiftool)과 수학 검증(라운드트립)만 가능. 코드 docstring과 문서에 "미검증" 명시(프로젝트 기존 관례).
- 테스트는 `unittest.TestCase` 스타일(프로젝트 관례, pytest 미사용).
- 각 태스크 종료 시 `python3 -m unittest discover -s tests`가 그린이어야 한다(현재 347개).
- 문서는 README.md/README.ko.md 둘 다, `docs/project_structure.md`/`.en.md` 둘 다 갱신(이중언어 동시 유지 관례).

---

### Task 1: XYZ(D50) 참조값 + D50 ΔE 헬퍼

**Files:**
- Modify: `hybrid_engine/core/chart_baseline.py` (추가만 - 기존 함수 수정 금지)
- Test: `tests/test_chart_baseline_native.py` (신규)

**Interfaces:**
- Consumes: 기존 `chart_baseline.PATCH_NAMES`(24개 패치 이름 리스트, row-major, dark skin이 첫 번째), 기존 `reference_patches_linear_srgb()`.
- Produces: `reference_patches_xyz_d50() -> np.ndarray` shape `(24, 3)`, XYZ(D50), PATCH_NAMES 순서.
- Produces: `patch_delta_e_xyz_d50(samples_xyz, reference_xyz=None, method="CIE 2000") -> np.ndarray` shape `(N,)`, 패치별 ΔE00.
- Produces: 모듈 상수 `D50_XY` - D50 백색점 xy 좌표 `array([0.3457, 0.3585])`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_chart_baseline_native.py` 신규 작성:

```python
import unittest

import numpy as np

from hybrid_engine.core.chart_baseline import (
    D50_XY, reference_patches_linear_srgb, reference_patches_xyz_d50,
    patch_delta_e_xyz_d50,
)


class TestReferencePatchesXyzD50(unittest.TestCase):
    def test_shape(self):
        ref = reference_patches_xyz_d50()
        self.assertEqual(ref.shape, (24, 3))

    def test_neutral_patches_cluster_at_d50_whitepoint(self):
        # PATCH_NAMES의 마지막 6개(인덱스 18~23)가 무채색 패치 - D50으로
        # 색순응했으면 이들의 xy 색도가 D50 백색점 근처로 모여야 한다.
        # (색순응이 안 걸렸으면 원본 Illuminant C 쪽에 남아있게 된다)
        ref = reference_patches_xyz_d50()
        neutrals = ref[18:24]
        xy = neutrals[:, :2] / neutrals.sum(axis=1, keepdims=True)
        mean_xy = xy.mean(axis=0)
        np.testing.assert_allclose(mean_xy, D50_XY, atol=0.002)

    def test_differs_from_linear_srgb_reference(self):
        # 같은 데이터셋이지만 최종 공간이 달라야 한다 - 값이 같으면
        # 변환이 안 걸린 것.
        xyz = reference_patches_xyz_d50()
        srgb = reference_patches_linear_srgb()
        self.assertFalse(np.allclose(xyz, srgb, atol=1e-6))


class TestPatchDeltaEXyzD50(unittest.TestCase):
    def test_identical_input_gives_zero(self):
        ref = reference_patches_xyz_d50()
        de = patch_delta_e_xyz_d50(ref, ref)
        self.assertEqual(de.shape, (24,))
        np.testing.assert_allclose(de, np.zeros(24), atol=1e-9)

    def test_perturbed_input_gives_nonzero(self):
        ref = reference_patches_xyz_d50()
        perturbed = ref * 1.2
        de = patch_delta_e_xyz_d50(perturbed, ref)
        self.assertTrue(np.all(de > 0.5))

    def test_defaults_to_official_reference(self):
        ref = reference_patches_xyz_d50()
        explicit = patch_delta_e_xyz_d50(ref, ref)
        implicit = patch_delta_e_xyz_d50(ref)
        np.testing.assert_allclose(explicit, implicit, atol=1e-12)


class TestFitRecoversKnownMatrix(unittest.TestCase):
    def test_fit_color_matrix_recovers_the_matrix_used_to_make_targets(self):
        # 피팅 경로 자체가 정상인지 확인 - 알려진 3x3으로 타깃을 만들면
        # fit_color_matrix()가 그 3x3을 되찾아야 한다. (24, 3) 패치 샘플
        # 형태로 검증하는 게 중요하다: 실제 사용처가 (H, W, 3) 이미지가
        # 아니라 차트 패치 배열이기 때문.
        from hybrid_engine.core.raw_baseline import fit_color_matrix

        rng = np.random.default_rng(0)
        known = np.array([
            [0.8123, -0.1456, 0.0321],
            [-0.2345, 1.1234, 0.0987],
            [0.0456, -0.1987, 0.9012],
        ])
        sources = [rng.uniform(0.02, 0.9, size=(24, 3)) for _ in range(3)]
        targets = [s @ known for s in sources]

        fitted = fit_color_matrix(sources, targets)

        self.assertEqual(fitted.shape, (3, 3))
        np.testing.assert_allclose(fitted, known, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_chart_baseline_native -v`
Expected: `ImportError: cannot import name 'D50_XY'` (또는 `reference_patches_xyz_d50`)

- [ ] **Step 3: 구현 작성**

`hybrid_engine/core/chart_baseline.py`의 `_SRGB = colour.RGB_COLOURSPACES["sRGB"]` 바로 다음 줄에 상수 추가:

```python
D50_XY = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]
```

그리고 기존 `reference_patches_linear_srgb()` 함수 **다음에** 두 함수를 추가(기존 함수는 수정하지 않는다):

```python
def reference_patches_xyz_d50():
    """ColorChecker Classic 24패치의 공식 참조값을 XYZ(D50)로 변환해서
    반환. (24, 3) ndarray, PATCH_NAMES와 같은 순서.

    reference_patches_linear_srgb()가 sRGB 프라이머리/D65로 가는 것과
    달리 이건 XYZ D50으로 간다 - Adobe DNG/DCP 프로필의 기준 공간이
    XYZ D50이기 때문(ColorMatrix1이 정의상 XYZ(D50) -> 카메라 네이티브
    RGB). colour-science 데이터셋은 CIE Illuminant C 기준이라 Bradford
    CAT으로 D50에 색순응시킨다."""
    cc = colour.CCS_COLOURCHECKERS["ColorChecker24 - After November 2014"]
    xyY = np.array([cc.data[name] for name in PATCH_NAMES])
    XYZ = colour.xyY_to_XYZ(xyY)
    return colour.chromatic_adaptation(
        XYZ,
        colour.xy_to_XYZ(cc.illuminant),
        colour.xy_to_XYZ(D50_XY),
        method="Von Kries",
        transform="Bradford",
    )


def patch_delta_e_xyz_d50(samples_xyz, reference_xyz=None, method="CIE 2000"):
    """XYZ(D50) 공간의 (N, 3) 샘플과 참조값 사이 패치별 ΔE00.
    reference 생략 시 reference_patches_xyz_d50()를 쓴다.

    patch_delta_e()와 별개 함수인 이유: 그쪽은 선형 sRGB 입력을 D65
    백색점 기준으로 Lab 변환하는데, 이쪽은 입력이 이미 XYZ이고 백색점도
    D50이라 변환 경로가 다르다."""
    if reference_xyz is None:
        reference_xyz = reference_patches_xyz_d50()
    lab_a = colour.XYZ_to_Lab(samples_xyz, illuminant=D50_XY)
    lab_b = colour.XYZ_to_Lab(reference_xyz, illuminant=D50_XY)
    return np.asarray(colour.delta_E(lab_a, lab_b, method=method))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_chart_baseline_native -v`
Expected: `OK` (7 tests)

- [ ] **Step 5: 전체 스위트 확인 + 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, 354 tests (기존 347 + 7)

```bash
git add hybrid_engine/core/chart_baseline.py tests/test_chart_baseline_native.py
git commit -m "Add XYZ(D50) chart reference + D50 delta-E helper for DCP-space fitting"
```

---

### Task 2: 카메라 네이티브 디코드 경로 + UniqueCameraModel 읽기

**Files:**
- Modify: `hybrid_engine/utils/io.py` (추가만 - `decode_raw()` 수정 금지)
- Modify: `hybrid_engine/utils/exif.py` (추가만 - `read_make_model()` 수정 금지)

**Interfaces:**
- Produces: `decode_raw_native(raw_path) -> np.ndarray` shape `(H, W, 3)`, float64, 카메라 네이티브 linear RGB(libraw 색매트릭스·WB 둘 다 미적용).
- Produces: `read_unique_camera_model(path) -> str | None` - exiftool의 `UniqueCameraModel` 태그(없으면 `Make` + `Model` 조합, 그것도 없으면 `None`).
- Produces: `read_as_shot_neutral(path) -> np.ndarray | None` shape `(3,)` - exiftool의 `AsShotNeutral` 태그를 파싱한 float 배열(없으면 `None`).

이 태스크는 실제 RAW 파일이 필요해서 자동 unittest 대상이 아니다(프로젝트의 다른 RAW 경로와 동일한 관례) - Step 3의 수동 스모크테스트로 검증한다.

- [ ] **Step 1: `decode_raw_native()` 구현**

`hybrid_engine/utils/io.py`의 기존 `decode_raw()` **다음에** 추가:

```python
def decode_raw_native(raw_path):
    """RAW -> 카메라 네이티브 linear RGB, float64 [0, 1] 근방,
    shape (H, W, 3), RGB 순서.

    decode_raw()와 결정적으로 다른 점: libraw의 카메라->출력 색매트릭스
    (output_color)와 화이트밸런스를 **둘 다 우회**한다. Adobe DCP
    프로필의 ColorMatrix1이 요구하는 공간이 바로 이 "카메라 네이티브
    RGB"(디모자이크는 됐지만 색변환/WB 이전)이기 때문 - decode_raw()의
    출력은 libraw가 이미 자기 매트릭스와 WB를 적용한 sRGB 프라이머리
    값이라 DCP에 그대로 쓸 수 없다.

    WB가 안 걸려서 초록 채널이 다른 채널의 약 2배로 치우친 이미지가
    나오는 게 정상이다(베이어 센서의 초록 화소가 2배 많고 초록 감도가
    높기 때문). 차트 검출에는 영향 없음 - chart_baseline.
    detect_and_sample()이 검출용 프리뷰를 만들 때 퍼센타일 정규화를
    거치므로 이 캐스트 상태에서도 검출된다(실측 확인)."""
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=False,
            use_auto_wb=False,
            user_wb=[1.0, 1.0, 1.0, 1.0],
            no_auto_bright=True,
            output_bps=16,
            output_color=rawpy.ColorSpace.raw,
            gamma=(1, 1),  # 순수 linear
        )
    return rgb16.astype(np.float64) / 65535.0
```

- [ ] **Step 2: exiftool 헬퍼 2개 구현**

`hybrid_engine/utils/exif.py`의 기존 `read_make_model()` **다음에** 추가(파일 상단 import는 이미 `json`, `subprocess`가 있어 추가 불필요):

```python
def read_unique_camera_model(path):
    """DNG/DCP의 UniqueCameraModel 태그를 읽는다 - DCP 프로필이 "이
    프로필은 어느 카메라용인가"를 선언하는 데 쓰는 값. 태그가 없으면
    Make + Model을 공백으로 이어 붙여 대체하고, 둘 다 없으면 None."""
    out = subprocess.run(
        ["exiftool", "-json", "-UniqueCameraModel", "-Make", "-Model", path],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    d = data[0] if data else {}
    unique = d.get("UniqueCameraModel")
    if unique:
        return unique
    make, model = d.get("Make"), d.get("Model")
    if make and model:
        return f"{make} {model}"
    return model or make or None


def read_as_shot_neutral(path):
    """AsShotNeutral 태그(촬영 당시 중립색의 카메라 네이티브 RGB 값,
    DNG 스펙 정의)를 (3,) float 배열로 읽는다. 없으면 None.

    exiftool은 이 값을 "0.3688 1 0.5917" 같은 공백 구분 문자열로
    준다."""
    out = subprocess.run(
        ["exiftool", "-json", "-AsShotNeutral", path],
        capture_output=True, text=True, timeout=30,
    )
    data = json.loads(out.stdout) if out.stdout.strip() else [{}]
    raw_value = (data[0] if data else {}).get("AsShotNeutral")
    if not raw_value:
        return None
    parts = str(raw_value).replace(",", " ").split()
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    return np.array(values[:3], dtype=np.float64) if len(values) >= 3 else None
```

`hybrid_engine/utils/exif.py` 상단에 `import numpy as np`를 추가해야 한다(현재 `json`, `subprocess`만 import함).

- [ ] **Step 3: 수동 스모크테스트 (실제 RAW)**

Run:
```bash
python3 -c "
from hybrid_engine.utils.io import decode_raw_native
from hybrid_engine.utils.exif import read_unique_camera_model, read_as_shot_neutral
p = 'datasets/hasselblad/contributed/kmichels-x2dii-2026-07/raw/B_31325.3FR'
img = decode_raw_native(p)
print('shape:', img.shape, 'dtype:', img.dtype)
print('channel means (R,G,B):', img.reshape(-1,3).mean(axis=0))
print('camera model:', read_unique_camera_model(p))
print('as-shot neutral:', read_as_shot_neutral(p))
"
```
Expected: shape `(8842, 11904, 3)`, dtype `float64`, 채널 평균이 대략 `[0.0498, 0.1068, 0.0496]`(초록이 약 2배 - WB 미적용 확인), camera model `Hasselblad X2D II 100C`, as-shot neutral `[0.3688 1. 0.5917]`.

**만약 채널 평균에서 초록이 2배가 아니면** WB가 어딘가에서 적용된 것이므로 멈추고 보고할 것(이 태스크의 핵심 전제가 깨진 것).

- [ ] **Step 4: 전체 스위트 확인 + 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, 354 tests (이 태스크는 테스트를 추가하지 않음 - 기존 개수 유지)

```bash
git add hybrid_engine/utils/io.py hybrid_engine/utils/exif.py
git commit -m "Add camera-native RAW decode path + UniqueCameraModel/AsShotNeutral readers"
```

---

### Task 3: 네이티브 매트릭스 피팅 실험 (Phase 1의 실제 결과)

**Files:**
- Create: `tools/analyze_camera_native_matrix.py`

**Interfaces:**
- Consumes: Task 1의 `chart_baseline.reference_patches_xyz_d50()` / `patch_delta_e_xyz_d50(samples_xyz, reference_xyz=None)`, Task 2의 `io.decode_raw_native(raw_path)` / `exif.read_as_shot_neutral(path)` / `exif.read_unique_camera_model(path)`.
- Consumes: 기존 `chart_baseline.detect_and_sample(linear_rgb)` -> `(24, 3)` 또는 `None`, 기존 `raw_baseline.fit_color_matrix(sources, targets)` -> `(3, 3)`, 기존 `raw_baseline.apply_color_matrix(rgb_linear, matrix)` -> 보정된 배열(내부적으로 `rgb @ matrix` 후 음수 clip).
- Produces: 리포트 JSON `datasets/hasselblad/contributed/kmichels-x2dii-2026-07/camera_native_matrix_report.json` - Task 5가 이 파일의 수치를 문서에 옮겨 적는다. 키: `libraw_direction_delta_e`, `libraw_direction_chosen`, `no_correction_delta_e_mean`, `libraw_matrix_delta_e_mean`, `chart_matrix_in_sample_delta_e_mean`, `chart_matrix_cv_delta_e_mean`, `improvement_vs_libraw_pct`, `chart_matrix_in_sample`, `libraw_cam_to_xyz`, `estimated_illuminant`.

- [ ] **Step 1: 도구 작성**

`tools/analyze_camera_native_matrix.py` 신규 작성:

```python
"""카메라 네이티브 공간에서 색매트릭스를 피팅해 libraw 내장 매트릭스와
비교한다 - DCP 프로필의 ColorMatrix1이 요구하는 공간이 기존
tools/analyze_colorchecker_matrix.py가 다루는 공간(libraw가 이미 자기
매트릭스를 적용한 sRGB)과 다르기 때문. 설계 근거:
docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md

  python3 -m tools.analyze_camera_native_matrix
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import rawpy

from hybrid_engine.core import chart_baseline, raw_baseline
from hybrid_engine.utils.exif import read_as_shot_neutral, read_unique_camera_model
from hybrid_engine.utils.io import decode_raw_native

SET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "datasets", "hasselblad", "contributed", "kmichels-x2dii-2026-07")

# EXIF LightSource enum 중 DCP의 CalibrationIlluminant로 흔히 쓰는 값과
# 그 대표 색온도. 추정 CCT에서 가장 가까운 것을 고른다.
LIGHT_SOURCE_ENUMS = [
    (17, "Standard light A", 2856.0),
    (23, "D50", 5003.0),
    (20, "D55", 5503.0),
    (21, "D65", 6504.0),
    (22, "D75", 7504.0),
]


def _load_native_chart_samples():
    """각 차트 RAW를 카메라 네이티브로 디코드해서 24패치를 샘플링.
    반환: {파일명: (24, 3) 네이티브 RGB}"""
    raw_paths = sorted(glob.glob(os.path.join(SET_DIR, "raw", "*.3FR")))
    per_image = {}
    for raw_path in raw_paths:
        name = os.path.basename(raw_path)
        print(f"  디코드+검출 중(네이티브): {name}", flush=True)
        native = decode_raw_native(raw_path)
        samples = chart_baseline.detect_and_sample(native)
        if samples is None:
            print(f"    차트 검출 실패, 제외: {name}")
            continue
        per_image[name] = samples
    return per_image


def _libraw_matrix(raw_path):
    """libraw 내장 rgb_xyz_matrix의 앞 3행. RGB 카메라는 4번째 행이
    전부 0이라 잘라낸다(4색 센서용 자리)."""
    with rawpy.imread(raw_path) as raw:
        return np.asarray(raw.rgb_xyz_matrix, dtype=np.float64)[:3, :3]


def _mean_de(samples_xyz, reference):
    return float(np.mean(chart_baseline.patch_delta_e_xyz_d50(samples_xyz, reference)))


def _estimate_illuminant(as_shot_neutral, cam_to_xyz):
    """AsShotNeutral(촬영 당시 중립색의 카메라 네이티브 RGB)을 피팅된
    매트릭스로 XYZ에 보내 그 색도의 CCT를 추정하고, 가장 가까운 EXIF
    LightSource enum을 고른다.

    주의: 이건 **추정**이다. 세 겹으로 그렇다.
      (a) 차트 촬영 당시의 조명이 실측되지 않았다(manifest의 illuminant
          칼럼이 10장 전부 비어있음).
      (b) AsShotNeutral 자체가 카메라의 자동 WB 판단 결과라 측정된
          조명값이 아니다.
      (c) AsShotNeutral은 DNG 스펙의 raw 값 스케일 기준인데 cam_to_xyz는
          decode_raw_native()가 낸 libraw 디모자이크 출력(/65535 정규화)
          기준으로 피팅된 것이라, 두 스케일이 채널별로 정확히 일치한다는
          보장이 없다. 다만 CCT는 색도(xy)에서만 나오고 xy는 전역 스케일에
          불변이므로, 채널별 스케일 차이가 없다면 이 추정은 유효하다 -
          libraw가 채널별로 다른 정규화를 적용하는 경우에만 틀어진다.
          이 부분은 확인하지 않았다."""
    import colour
    if as_shot_neutral is None:
        return None
    xyz = np.asarray(as_shot_neutral, dtype=np.float64) @ cam_to_xyz
    total = xyz.sum()
    if total <= 0:
        return None
    xy = np.array([xyz[0] / total, xyz[1] / total])
    cct = float(colour.xy_to_CCT(xy, method="McCamy 1992"))
    enum_value, enum_name, enum_cct = min(LIGHT_SOURCE_ENUMS,
                                          key=lambda e: abs(e[2] - cct))
    return {
        "as_shot_neutral": as_shot_neutral.tolist(),
        "neutral_xy": xy.tolist(),
        "estimated_cct": cct,
        "chosen_enum": enum_value,
        "chosen_enum_name": enum_name,
        "chosen_enum_cct": enum_cct,
        "note": "추정값 - 촬영 당시 조명이 실측되지 않았음(manifest illuminant 칼럼 공백)",
    }


def main():
    reference = chart_baseline.reference_patches_xyz_d50()
    per_image = _load_native_chart_samples()
    names = sorted(per_image.keys())
    n = len(names)
    print(f"\n검출 성공 {n}장: {names}")
    if n < 2:
        print("이미지가 2장 미만이라 교차검증 불가")
        sys.exit(1)

    raw_paths = {os.path.basename(p): p
                 for p in glob.glob(os.path.join(SET_DIR, "raw", "*.3FR"))}
    libraw_m = _libraw_matrix(raw_paths[names[0]])

    # 1) libraw 매트릭스의 방향을 실측으로 확정한다 - rgb_xyz_matrix가
    #    XYZ->cam인지 cam->XYZ인지 문서만으론 단정할 수 없어서, 두 방향
    #    다 적용해보고 XYZ 참조값에 가까워지는 쪽을 채택한다.
    as_is = float(np.mean([
        _mean_de(raw_baseline.apply_color_matrix(per_image[nm], libraw_m), reference)
        for nm in names]))
    inverted_m = np.linalg.inv(libraw_m)
    inverted = float(np.mean([
        _mean_de(raw_baseline.apply_color_matrix(per_image[nm], inverted_m), reference)
        for nm in names]))
    if as_is <= inverted:
        libraw_cam_to_xyz, chosen = libraw_m, "as_is"
    else:
        libraw_cam_to_xyz, chosen = inverted_m, "inverted"
    print("\n=== libraw rgb_xyz_matrix 방향 판정 ===")
    print(f"  그대로 적용(native @ M):        ΔE00 {as_is:.2f}")
    print(f"  역행렬 적용(native @ inv(M)):   ΔE00 {inverted:.2f}")
    print(f"  채택: {chosen}")
    libraw_mean = min(as_is, inverted)

    # 2) 보정 없음 - 네이티브 값을 XYZ로 그대로 간주(스케일 감각용,
    #    정상적으로 매우 나쁠 것)
    no_corr = float(np.mean([_mean_de(per_image[nm], reference) for nm in names]))

    # 3) 차트 피팅: in-sample + leave-one-image-out CV
    all_sources = [per_image[nm] for nm in names]
    all_targets = [reference for _ in names]
    chart_m = raw_baseline.fit_color_matrix(all_sources, all_targets)
    in_sample = float(np.mean([
        _mean_de(raw_baseline.apply_color_matrix(per_image[nm], chart_m), reference)
        for nm in names]))

    cv_per_image = {}
    for i, held_out in enumerate(names):
        train_sources = [per_image[nm] for j, nm in enumerate(names) if j != i]
        train_targets = [reference for _ in train_sources]
        m = raw_baseline.fit_color_matrix(train_sources, train_targets)
        corrected = raw_baseline.apply_color_matrix(per_image[held_out], m)
        cv_per_image[held_out] = _mean_de(corrected, reference)
    cv_mean = float(np.mean(list(cv_per_image.values())))

    improvement = (1 - cv_mean / libraw_mean) * 100 if libraw_mean > 0 else 0.0

    print("\n=== 패치 평균 ΔE00 (XYZ D50 기준, 이미지별 평균의 평균) ===")
    print(f"보정 없음(네이티브를 XYZ로 간주):        {no_corr:.2f}")
    print(f"libraw 내장 매트릭스({chosen}):          {libraw_mean:.2f}")
    print(f"차트 매트릭스 in-sample({n}장 pooled):     {in_sample:.2f}")
    print(f"차트 매트릭스 leave-one-image-out CV:   {cv_mean:.2f}")
    print(f"\nlibraw 대비 개선(CV 기준): {improvement:+.1f}%")
    if cv_mean < libraw_mean:
        print("=> 차트 매트릭스가 libraw를 이겼다. DCP 프로필 생성 조건 충족.")
    else:
        print("=> 차트 매트릭스가 libraw를 못 이겼다. DCP 프로필은 생성하지 않는다.")

    print("\n차트 매트릭스(네이티브 -> XYZ D50, in-sample):")
    print(chart_m)

    as_shot = read_as_shot_neutral(raw_paths[names[0]])
    illuminant = _estimate_illuminant(as_shot, chart_m)
    print("\n=== CalibrationIlluminant 추정 ===")
    print(illuminant)

    report = {
        "n_images": n,
        "images": names,
        "camera_model": read_unique_camera_model(raw_paths[names[0]]),
        "libraw_direction_delta_e": {"as_is": as_is, "inverted": inverted},
        "libraw_direction_chosen": chosen,
        "no_correction_delta_e_mean": no_corr,
        "libraw_matrix_delta_e_mean": libraw_mean,
        "chart_matrix_in_sample_delta_e_mean": in_sample,
        "chart_matrix_cv_delta_e_mean": cv_mean,
        "chart_matrix_cv_delta_e_per_image": cv_per_image,
        "improvement_vs_libraw_pct": improvement,
        "chart_matrix_beats_libraw": bool(cv_mean < libraw_mean),
        "chart_matrix_in_sample": chart_m.tolist(),
        "libraw_cam_to_xyz": libraw_cam_to_xyz.tolist(),
        "estimated_illuminant": illuminant,
    }
    out_path = os.path.join(SET_DIR, "camera_native_matrix_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 (10장 100MP RAW 디코드 - 수 분 소요)**

Run: `python3 -m tools.analyze_camera_native_matrix`
Expected: 예외 없이 완주하고 위 형식의 표 + `camera_native_matrix_report.json` 생성.

**출력된 모든 수치를 받아적어 둔다** - Task 5가 문서에 그대로 옮긴다. 특히:
- libraw 방향 판정 결과(`as_is` vs `inverted`, 각 ΔE)
- 네 가지 ΔE(보정 없음 / libraw / in-sample / CV)
- `improvement_vs_libraw_pct`와 `chart_matrix_beats_libraw`(True/False) - **이게 Task 5의 프로필 생성 게이트**
- 추정된 CalibrationIlluminant enum과 CCT

**차트 검출이 2장 미만만 성공하면** 멈추고 보고할 것(네이티브 이미지에서 검출이 예상보다 불안정하다는 뜻 - 설계 단계에서 1장은 성공 확인했으나 전수는 미확인).

- [ ] **Step 3: 커밋**

```bash
git add tools/analyze_camera_native_matrix.py \
        datasets/hasselblad/contributed/kmichels-x2dii-2026-07/camera_native_matrix_report.json
git commit -m "Add camera-native matrix fitting experiment vs libraw's built-in matrix"
```

---

### Task 4: `.dcp` writer + 라운드트립 파서

**Files:**
- Create: `core/dcp_export.py`
- Test: `tests/test_dcp_export.py` (신규)

**Interfaces:**
- Produces: `write_dcp(path, camera_model, profile_name, color_matrix_1, calibration_illuminant_1, forward_matrix_1=None) -> None` - `color_matrix_1`/`forward_matrix_1`은 `(3, 3)` 또는 길이 9로 reshape 가능한 배열, `calibration_illuminant_1`은 EXIF LightSource enum int.
- Produces: `read_dcp(path) -> dict` - 태그 ID를 키로 하는 dict. ASCII 태그는 `str`, SHORT은 `int`, SRATIONAL은 `(9,)` float 배열.
- Produces: 태그 상수 `TAG_UNIQUE_CAMERA_MODEL=50708`, `TAG_COLOR_MATRIX_1=50721`, `TAG_CALIBRATION_ILLUMINANT_1=50778`, `TAG_PROFILE_NAME=50936`, `TAG_FORWARD_MATRIX_1=50964`.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_dcp_export.py` 신규 작성:

```python
import os
import struct
import tempfile
import unittest

import numpy as np

from core.dcp_export import (
    TAG_CALIBRATION_ILLUMINANT_1, TAG_COLOR_MATRIX_1, TAG_FORWARD_MATRIX_1,
    TAG_PROFILE_NAME, TAG_UNIQUE_CAMERA_MODEL, read_dcp, write_dcp,
)

_MATRIX = np.array([
    [0.7123, -0.1234, 0.0456],
    [-0.3456, 1.2345, 0.0789],
    [0.0123, -0.2345, 0.8901],
])


class TestWriteReadRoundTrip(unittest.TestCase):
    def test_round_trip_recovers_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21)

            tags = read_dcp(path)

            self.assertEqual(tags[TAG_UNIQUE_CAMERA_MODEL], "Test Camera 1")
            self.assertEqual(tags[TAG_PROFILE_NAME], "Test Profile")
            self.assertEqual(tags[TAG_CALIBRATION_ILLUMINANT_1], 21)
            # SRATIONAL은 분모 1000000로 양자화되므로 그 반올림 오차 내에서 일치
            np.testing.assert_allclose(tags[TAG_COLOR_MATRIX_1],
                                        _MATRIX.reshape(9), atol=1e-6)

    def test_forward_matrix_omitted_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21)
            tags = read_dcp(path)
            self.assertNotIn(TAG_FORWARD_MATRIX_1, tags)

    def test_forward_matrix_included_when_given(self):
        forward = _MATRIX * 0.5
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=21,
                       forward_matrix_1=forward)
            tags = read_dcp(path)
            np.testing.assert_allclose(tags[TAG_FORWARD_MATRIX_1],
                                        forward.reshape(9), atol=1e-6)

    def test_negative_values_survive_round_trip(self):
        # SRATIONAL은 부호 있는 타입 - 음수 계수(색매트릭스에 흔함)가
        # 부호 없는 타입으로 잘못 패킹되면 여기서 깨진다.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.dcp")
            write_dcp(path, camera_model="C", profile_name="P",
                       color_matrix_1=_MATRIX, calibration_illuminant_1=23)
            recovered = read_dcp(path)[TAG_COLOR_MATRIX_1]
        self.assertLess(recovered[1], 0)
        self.assertLess(recovered[3], 0)
        np.testing.assert_allclose(recovered[1], _MATRIX[0, 1], atol=1e-6)


class TestTiffStructure(unittest.TestCase):
    def _write_sample(self, tmp):
        path = os.path.join(tmp, "test.dcp")
        write_dcp(path, camera_model="Test Camera 1", profile_name="Test Profile",
                   color_matrix_1=_MATRIX, calibration_illuminant_1=21)
        return path

    def test_header_is_valid_little_endian_tiff(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                header = f.read(8)
        byte_order, magic, first_ifd = struct.unpack("<2sHI", header)
        self.assertEqual(byte_order, b"II")
        self.assertEqual(magic, 42)
        self.assertEqual(first_ifd, 8)

    def test_ifd_entries_sorted_by_tag(self):
        # TIFF 스펙은 IFD 엔트리를 태그 오름차순으로 요구한다 - 어기면
        # 엄격한 리더가 거부할 수 있다.
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                data = f.read()
        (n_entries,) = struct.unpack_from("<H", data, 8)
        tags = [struct.unpack_from("<H", data, 8 + 2 + 12 * i)[0]
                for i in range(n_entries)]
        self.assertEqual(tags, sorted(tags))

    def test_all_offsets_within_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                data = f.read()
        (n_entries,) = struct.unpack_from("<H", data, 8)
        type_sizes = {2: 1, 3: 2, 10: 8}
        for i in range(n_entries):
            off = 8 + 2 + 12 * i
            _tag, typ, count = struct.unpack_from("<HHI", data, off)
            size = type_sizes[typ] * count
            if size > 4:
                (payload_offset,) = struct.unpack_from("<I", data, off + 8)
                self.assertLessEqual(payload_offset + size, len(data))

    def test_next_ifd_offset_is_zero(self):
        # 단일 IFD 파일이므로 다음 IFD 오프셋은 0(체인 끝)이어야 한다.
        with tempfile.TemporaryDirectory() as tmp:
            with open(self._write_sample(tmp), "rb") as f:
                data = f.read()
        (n_entries,) = struct.unpack_from("<H", data, 8)
        (next_ifd,) = struct.unpack_from("<I", data, 8 + 2 + 12 * n_entries)
        self.assertEqual(next_ifd, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m unittest tests.test_dcp_export -v`
Expected: `ModuleNotFoundError: No module named 'core.dcp_export'`

- [ ] **Step 3: 구현 작성**

`core/dcp_export.py` 신규 작성:

```python
"""Adobe DCP(카메라 프로필) 파일 쓰기 - 카메라 네이티브 색매트릭스를
Lightroom Classic/Camera Raw가 읽을 수 있는 형태로 내보낸다.

DCP는 TIFF 구조 파일(리틀엔디안 헤더 + 단일 IFD + DNG 카메라 프로필
태그들)이라 표준 라이브러리 struct로 직접 쓸 수 있다 - Adobe DNG SDK나
추가 의존성이 필요 없다.

core/lut_export.py의 `.cube` 내보내기와 목적이 다르다: `.cube`는 이미
렌더링된 이미지에 얹는 "룩"이고, DCP는 RAW 디모자이크 직후 색변환
단계에 들어가는 색채측정 보정이다. 그래서 DCP에 넣는 매트릭스는 반드시
카메라 네이티브 RGB 공간에서 피팅된 것이어야 한다(설계 근거:
docs/superpowers/specs/2026-07-25-camera-native-matrix-dcp-design.md).

**미검증**: 이 모듈이 만든 파일의 구조 유효성(exiftool 파싱)과 수치
라운드트립은 검증했지만, Lightroom/ACR이 실제로 로드해서 의도한 색을
내는지는 이 프로젝트의 개발 환경에 Adobe 제품이 없어 확인하지 못했다.
프로젝트의 다른 "미검증" 항목들과 같은 성격의 caveat다."""
import struct

import numpy as np

# DNG 스펙 태그 ID
TAG_UNIQUE_CAMERA_MODEL = 50708
TAG_COLOR_MATRIX_1 = 50721
TAG_CALIBRATION_ILLUMINANT_1 = 50778
TAG_PROFILE_NAME = 50936
TAG_FORWARD_MATRIX_1 = 50964

# TIFF 필드 타입
_TYPE_ASCII = 2
_TYPE_SHORT = 3
_TYPE_SRATIONAL = 10

_TYPE_SIZES = {_TYPE_ASCII: 1, _TYPE_SHORT: 2, _TYPE_SRATIONAL: 8}

# SRATIONAL(분자/분모 정수쌍)의 고정 분모. 1e-6 해상도면 색매트릭스
# 계수에 충분하고(계수 크기가 대략 -1~2 범위), int32 범위도 넉넉하다.
_RATIONAL_DENOM = 1000000


def _srational_payload(values):
    """실수 배열을 SRATIONAL 바이트열로. 각 값이 (분자 int32, 분모
    int32) 쌍 8바이트가 된다. 부호 있는 'i'를 쓰는 게 중요하다 -
    색매트릭스는 음수 계수가 흔하다."""
    out = b""
    for v in np.asarray(values, dtype=np.float64).reshape(-1):
        numerator = int(round(float(v) * _RATIONAL_DENOM))
        out += struct.pack("<ii", numerator, _RATIONAL_DENOM)
    return out


def _ascii_payload(text):
    """TIFF ASCII 필드는 NUL 종료 문자열이고 count에 NUL도 포함한다."""
    return text.encode("ascii") + b"\x00"


def write_dcp(path, camera_model, profile_name, color_matrix_1,
              calibration_illuminant_1, forward_matrix_1=None):
    """DCP 카메라 프로필을 path에 쓴다.

    camera_model: UniqueCameraModel - "이 프로필은 어느 카메라용인가".
        이게 없으면 Lightroom이 적용 대상을 판단할 수 없다.
    profile_name: Profile Browser에 표시될 이름.
    color_matrix_1: (3, 3) 또는 길이 9. DNG 정의상 **XYZ(D50) -> 카메라
        네이티브 RGB** 방향이다 - 카메라 네이티브 -> XYZ로 피팅한
        매트릭스를 넣으려면 호출부에서 역행렬을 취해 넘겨야 한다.
    calibration_illuminant_1: EXIF LightSource enum(예: 21=D65, 23=D50).
    forward_matrix_1: 선택. 카메라 네이티브 -> XYZ(D50). DNG 스펙상
        카메라 중립점을 D50 백색점으로 정확히 매핑하는 정규화 제약이
        있는데 그 구현을 Lightroom으로 검증할 수 없어서 기본값은
        None(생략)이다 - 생략해도 유효한 프로필이다."""
    entries = []  # (tag, type, count, payload)

    model_payload = _ascii_payload(camera_model)
    entries.append((TAG_UNIQUE_CAMERA_MODEL, _TYPE_ASCII,
                    len(model_payload), model_payload))

    name_payload = _ascii_payload(profile_name)
    entries.append((TAG_PROFILE_NAME, _TYPE_ASCII,
                    len(name_payload), name_payload))

    entries.append((TAG_CALIBRATION_ILLUMINANT_1, _TYPE_SHORT, 1,
                    struct.pack("<H", int(calibration_illuminant_1))))

    entries.append((TAG_COLOR_MATRIX_1, _TYPE_SRATIONAL, 9,
                    _srational_payload(color_matrix_1)))

    if forward_matrix_1 is not None:
        entries.append((TAG_FORWARD_MATRIX_1, _TYPE_SRATIONAL, 9,
                        _srational_payload(forward_matrix_1)))

    # TIFF 스펙: IFD 엔트리는 태그 오름차순이어야 한다.
    entries.sort(key=lambda e: e[0])

    ifd_size = 2 + 12 * len(entries) + 4  # 엔트리 수 + 엔트리들 + 다음 IFD 오프셋
    data_start = 8 + ifd_size            # 헤더 8바이트 다음이 IFD

    ifd = struct.pack("<H", len(entries))
    trailing = b""
    for tag, typ, count, payload in entries:
        if len(payload) <= 4:
            # 4바이트 이하는 value 필드에 인라인으로 넣는다
            value_field = payload + b"\x00" * (4 - len(payload))
        else:
            value_field = struct.pack("<I", data_start + len(trailing))
            trailing += payload
            if len(trailing) % 2:  # TIFF는 워드 정렬을 요구
                trailing += b"\x00"
        ifd += struct.pack("<HHI", tag, typ, count) + value_field
    ifd += struct.pack("<I", 0)  # 다음 IFD 없음

    with open(path, "wb") as f:
        f.write(struct.pack("<2sHI", b"II", 42, 8))  # 리틀엔디안 TIFF 헤더
        f.write(ifd)
        f.write(trailing)


def read_dcp(path):
    """write_dcp()가 쓴 파일을 되읽어 {태그 ID: 값} dict를 반환한다.
    범용 TIFF 파서가 아니라 이 모듈이 쓰는 세 타입(ASCII/SHORT/
    SRATIONAL)만 다루는 라운드트립 검증용 최소 파서다."""
    with open(path, "rb") as f:
        data = f.read()

    byte_order, magic, first_ifd = struct.unpack_from("<2sHI", data, 0)
    if byte_order != b"II" or magic != 42:
        raise ValueError(f"리틀엔디안 TIFF 헤더가 아님: {byte_order!r}, magic={magic}")

    (n_entries,) = struct.unpack_from("<H", data, first_ifd)
    tags = {}
    for i in range(n_entries):
        off = first_ifd + 2 + 12 * i
        tag, typ, count = struct.unpack_from("<HHI", data, off)
        if typ not in _TYPE_SIZES:
            raise ValueError(f"지원하지 않는 TIFF 필드 타입: {typ} (태그 {tag})")
        size = _TYPE_SIZES[typ] * count
        if size <= 4:
            payload = data[off + 8:off + 8 + size]
        else:
            (payload_offset,) = struct.unpack_from("<I", data, off + 8)
            payload = data[payload_offset:payload_offset + size]

        if typ == _TYPE_ASCII:
            tags[tag] = payload.rstrip(b"\x00").decode("ascii")
        elif typ == _TYPE_SHORT:
            tags[tag] = struct.unpack_from("<H", payload, 0)[0]
        else:
            ints = struct.unpack(f"<{2 * count}i", payload)
            tags[tag] = np.array([ints[2 * j] / ints[2 * j + 1]
                                   for j in range(count)], dtype=np.float64)
    return tags
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m unittest tests.test_dcp_export -v`
Expected: `OK` (8 tests)

- [ ] **Step 5: exiftool 구조 검증 (수동)**

Run:
```bash
python3 -c "
import numpy as np
from core.dcp_export import write_dcp
m = np.array([[0.7123,-0.1234,0.0456],[-0.3456,1.2345,0.0789],[0.0123,-0.2345,0.8901]])
write_dcp('/tmp/claude-0/-home-user-Hncs/1d07a51d-3df6-5c74-ae37-0cc778eeeb5b/scratchpad/verify.dcp',
          camera_model='Hasselblad X2D II 100C', profile_name='Structure Check',
          color_matrix_1=m, calibration_illuminant_1=21)
print('written')
"
exiftool /tmp/claude-0/-home-user-Hncs/1d07a51d-3df6-5c74-ae37-0cc778eeeb5b/scratchpad/verify.dcp
```
Expected: exiftool이 에러 없이 파싱하고 `Unique Camera Model`, `Profile Name`, `Calibration Illuminant 1`, `Color Matrix 1`이 위에서 넣은 값으로 표시된다. Color Matrix 1은 9개 값이 `0.7123 -0.1234 0.0456 ...` 형태로 나와야 한다.

**exiftool이 파싱에 실패하거나 값이 다르면** 멈추고 실제 출력을 그대로 보고할 것 - 자체 라운드트립은 통과하는데 exiftool이 못 읽는다면 TIFF 구조에 문제가 있다는 뜻이다.

- [ ] **Step 6: 전체 스위트 확인 + 커밋**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, 362 tests (Task 1 이후 354 + 8)

```bash
git add core/dcp_export.py tests/test_dcp_export.py
git commit -m "Add DCP camera profile writer + round-trip parser (struct-based, no new deps)"
```

---

### Task 5: 조건부 프로필 생성 + 문서화

**Files:**
- Create (조건부): `hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp` - **Task 3의 `chart_matrix_beats_libraw`가 `true`일 때만**
- Modify: `hybrid_engine/EVALUATION.md`
- Modify: `README.md`, `README.ko.md`
- Modify: `docs/project_structure.md`, `docs/project_structure.en.md`

**Interfaces:**
- Consumes: Task 3의 리포트 JSON `datasets/hasselblad/contributed/kmichels-x2dii-2026-07/camera_native_matrix_report.json`(모든 수치의 출처), Task 4의 `core.dcp_export.write_dcp()`.

- [ ] **Step 1: 게이트 판정**

Run:
```bash
python3 -c "
import json
r = json.load(open('datasets/hasselblad/contributed/kmichels-x2dii-2026-07/camera_native_matrix_report.json'))
print('beats libraw:', r['chart_matrix_beats_libraw'])
print('libraw ΔE:', round(r['libraw_matrix_delta_e_mean'], 3))
print('chart CV ΔE:', round(r['chart_matrix_cv_delta_e_mean'], 3))
print('improvement:', round(r['improvement_vs_libraw_pct'], 1), '%')
print('illuminant enum:', r['estimated_illuminant']['chosen_enum'], r['estimated_illuminant']['chosen_enum_name'])
"
```

`beats libraw`가 `True`면 Step 2를 실행한다. `False`면 **Step 2를 건너뛰고** Step 3으로 간다(프로필 파일 생성 안 함 - Global Constraints의 게이트).

- [ ] **Step 2: (게이트 통과 시에만) `.dcp` 프로필 생성**

Run:
```bash
python3 -c "
import json, numpy as np
from core.dcp_export import write_dcp
r = json.load(open('datasets/hasselblad/contributed/kmichels-x2dii-2026-07/camera_native_matrix_report.json'))
assert r['chart_matrix_beats_libraw'], '게이트 미통과 - 이 스텝을 실행해서는 안 됨'
# 피팅된 매트릭스는 네이티브 -> XYZ(D50) 방향. DCP의 ColorMatrix1은
# 반대 방향(XYZ D50 -> 네이티브)이라 역행렬을 넣는다.
cam_to_xyz = np.array(r['chart_matrix_in_sample'], dtype=np.float64)
color_matrix_1 = np.linalg.inv(cam_to_xyz)
write_dcp(
    'hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp',
    camera_model=r['camera_model'],
    profile_name='HNCS X2D II Chart Colorimetric',
    color_matrix_1=color_matrix_1,
    calibration_illuminant_1=r['estimated_illuminant']['chosen_enum'],
)
print('생성 완료. ColorMatrix1 (XYZ D50 -> native):')
print(np.round(color_matrix_1, 4))
"
exiftool hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp
```
Expected: 파일이 생성되고 exiftool이 `Unique Camera Model = Hasselblad X2D II 100C`, `Profile Name = HNCS X2D II Chart Colorimetric`, `Color Matrix 1`(9개 값), `Calibration Illuminant 1`을 정상 표시.

- [ ] **Step 3: `hybrid_engine/EVALUATION.md`에 결과 기록**

파일 맨 끝에 새 섹션을 추가한다. `<...>` 자리는 Step 1에서 출력된 **실제 수치**로 채운다(플레이스홀더를 그대로 커밋하지 말 것):

```markdown
## 후속 실측 21: 카메라 네이티브 색매트릭스 + DCP 프로필 (2026-07-25)

**동기**: 후속 실측 9에서 차트로 피팅한 매트릭스가 libraw 기본 디코드의
색채측정 오차를 7.58 -> 2.78로 줄였지만, 그 매트릭스는 Lightroom/ACR에
넣을 수 없는 형태였다. `decode_raw()`가 `output_color=sRGB` +
`use_camera_wb=True`를 쓰므로 libraw가 **이미** 자기 색매트릭스와 WB를
적용한 결과를 다루기 때문이다 - 즉 그 매트릭스는 "libraw sRGB -> 참값
sRGB" 보정이고, DCP의 `ColorMatrix1`이 요구하는 "XYZ(D50) -> 카메라
네이티브 RGB"가 아니다. 그 자리에 넣으면 Lightroom이 다른 공간의 값으로
해석해 조용히 틀린 색을 낸다.

**방법**: `decode_raw_native()`(`output_color=raw` + `user_wb=[1,1,1,1]`)로
libraw의 색변환·WB를 둘 다 우회한 카메라 네이티브 RGB를 얻고, 그 공간에서
차트 24패치 vs XYZ(D50) 참조값으로 3×3을 피팅했다. 데이터는 후속 실측 9와
같은 X2D II ColorChecker 차트 10장.

libraw 내장 `rgb_xyz_matrix`의 방향(XYZ->cam인지 cam->XYZ인지)은 문서로
단정할 수 없어 두 방향 다 적용해 실측으로 확정했다: 그대로 적용 ΔE00
<as_is>, 역행렬 적용 ΔE00 <inverted> -> **<chosen>** 채택.

**결과** (XYZ D50 공간 패치 평균 ΔE00, 이미지별 평균의 평균):

| 방식 | ΔE00 |
|---|---|
| 보정 없음(네이티브를 XYZ로 간주) | <no_correction> |
| libraw 내장 매트릭스 | <libraw> |
| 차트 매트릭스 in-sample(10장 pooled) | <in_sample> |
| **차트 매트릭스 leave-one-image-out CV** | **<cv>** |

libraw 대비 개선(CV 기준): **<improvement>%**

**판정**: <"차트 매트릭스가 libraw를 이겨서 .dcp 프로필을 생성했다
(hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp)" 또는 "차트
매트릭스가 libraw를 이기지 못해 프로필을 생성하지 않았다 - writer 코드
(core/dcp_export.py)는 향후 더 나은 차트 데이터를 위해 남겨뒀다">

**알려진 한계**:
- **조명 미측정**: 기여받은 manifest의 `illuminant` 칼럼이 10장 전부
  비어있다(이슈 #4에서 "measured illuminant"를 요청했으나 그 항목은 오지
  않았다). `CalibrationIlluminant1`은 `AsShotNeutral`
  <as_shot_neutral>에서 역산한 추정 CCT <estimated_cct>K를 가장 가까운
  EXIF LightSource enum <chosen_enum>(<chosen_enum_name>)로 매핑한
  **추정값**이다. 그 조명에서 벗어난 촬영의 오차 증가량은 다른 조명
  데이터가 없어 정량화할 수 없다.
- **조명 조건 1개**: 10장 전부 94초 한 버스트라 dual-illuminant 보간이
  불가능하다(`ColorMatrix2` 미사용).
- **Lightroom 렌더링 미검증**: 생성 파일의 TIFF 구조 유효성(exiftool
  파싱)과 수치 라운드트립은 검증했지만, Lightroom/ACR이 실제로 로드해서
  의도한 색을 내는지는 개발 환경에 Adobe 제품이 없어 확인하지 못했다.
- **`ForwardMatrix1` 미포함**: DNG 스펙상 카메라 중립점을 D50 백색점으로
  정확히 매핑하는 정규화 제약이 있는데 그 구현을 검증할 방법이 없어
  넣지 않았다(`ColorMatrix1`만 있는 프로필도 유효). `write_dcp()`는
  옵션 인자로 지원한다.
- **패치 24개 / 카메라 1대**: ColorChecker Classic(무채색 6 + 유채색 18)은
  본격 프로파일링 타깃보다 훨씬 적어 차트에 없는 색역의 정확도는 알 수
  없고, X2D II 100C 전용이다(`UniqueCameraModel`로 대상 명시).

**기존 `raw_baseline_matrix`와의 관계**: 이 매트릭스는 `hasselblad.json`의
`raw_baseline_matrix`를 대체하지 않는다. 그쪽은 "카메라 JPEG 룩 근사"가
목적이고(후속 실측 9에서 확인: 차트 참값에 대고 재면 오히려 나빠지는 게
정상), 이쪽은 색채측정 정확도가 목적인 별개 산출물이다. `hasselblad.json`은
건드리지 않았다.
```

- [ ] **Step 4: README.ko.md에 절 추가**

"## 포토샵 / DaVinci Resolve 프리셋 내보내기 (.cube LUT)" 절의 마지막 문단
(Lightroom Classic / Adobe Camera Raw 설명) 다음, "## 브랜드 시그니처
판별력 검증 (연구용)" 절 **직전**에 삽입. `<...>`는 실제 수치로 채운다:

```markdown
## DCP 카메라 프로필 (색채측정 보정, X2D II 전용)

위 `.cube` 경로가 "이미 렌더링된 이미지에 얹는 룩"이라면, 이쪽은
**RAW 디모자이크 직후 색변환 단계**에 들어가는 색채측정 보정이다. 기여받은
X2D II ColorChecker 차트 10장을 카메라 네이티브 RGB 공간(libraw의
색매트릭스·WB를 둘 다 우회한 `decode_raw_native()`)에서 XYZ(D50) 참조값에
최소자승 피팅해서, Lightroom Classic/Camera Raw가 읽는 Adobe `.dcp`
프로필로 내보낸다.

```
python3 -m tools.analyze_camera_native_matrix   # 피팅 + libraw 내장 매트릭스와 교차검증 비교
```

실측 결과(XYZ D50 패치 평균 ΔE00): libraw 내장 매트릭스 <libraw> ->
차트 피팅 매트릭스 **<cv>**(leave-one-image-out 교차검증),
libraw 대비 <improvement>%. 상세 수치와 한계는
`hybrid_engine/EVALUATION.md`의 "후속 실측 21" 참고.

**알려진 한계**: ① 차트 촬영 당시 조명이 실측되지 않아
(`manifest.csv`의 `illuminant` 칼럼 공백) `CalibrationIlluminant1`이
`AsShotNeutral`에서 역산한 **추정값**이다 ② 10장 전부 한 버스트라 조명
조건이 1개뿐이고 dual-illuminant 보간이 불가능하다 ③ **Lightroom이 실제로
이 파일을 의도대로 렌더링하는지는 미검증**이다 - 개발 환경에 Adobe 제품이
없어 TIFF 구조 유효성(exiftool)과 수치 라운드트립만 검증했다 ④ X2D II
100C 전용(`UniqueCameraModel`로 대상 명시).
```

- [ ] **Step 5: README.md에 같은 절의 영어판 추가**

"## Photoshop / DaVinci Resolve preset export (.cube LUT)" 절의 Lightroom
문단 다음, "## Brand-signature discriminability check (research)" 절
**직전**에 삽입(Step 4와 같은 실측 수치 사용):

```markdown
## DCP camera profile (colorimetric correction, X2D II only)

Where the `.cube` path above is a look layered onto an already-rendered
image, this one goes into the **color-conversion stage right after RAW
demosaic**. It least-squares-fits the 10 contributed X2D II ColorChecker
frames against XYZ(D50) references in camera-native RGB space (via
`decode_raw_native()`, which bypasses both libraw's color matrix and its
white balance), then exports the result as an Adobe `.dcp` profile that
Lightroom Classic/Camera Raw reads.

```
python3 -m tools.analyze_camera_native_matrix   # fit + cross-validated comparison against libraw's built-in matrix
```

Measured (patch-mean ΔE00 in XYZ D50): libraw's built-in matrix <libraw>
-> chart-fit matrix **<cv>** (leave-one-image-out cross-validation),
<improvement>% better than libraw. Full numbers and caveats in
`hybrid_engine/EVALUATION.md` ("후속 실측 21").

**Known limitations**: (1) the illuminant at capture time was never
measured (the contributed `manifest.csv`'s `illuminant` column is empty),
so `CalibrationIlluminant1` is **estimated** back out of `AsShotNeutral`;
(2) all 10 frames come from a single burst, so there's only one lighting
condition and dual-illuminant interpolation isn't possible; (3) **whether
Lightroom actually renders this file as intended is unverified** - there's
no Adobe software in this project's dev environment, so only TIFF
structural validity (via exiftool) and numeric round-tripping were
checked; (4) X2D II 100C only (declared via `UniqueCameraModel`).
```

- [ ] **Step 6: `docs/project_structure.md`/`.en.md`에 행 추가**

`docs/project_structure.md`의 `core/photo_signature.py` 행 **다음**에 추가:

```markdown
| `core/dcp_export.py` | Adobe DCP(카메라 프로필) 쓰기 - 카메라 네이티브 색매트릭스를 Lightroom Classic/Camera Raw가 읽는 `.dcp`로 내보낸다(`write_dcp`/`read_dcp`). DCP는 TIFF 구조라 표준 `struct`로 직접 쓴다(새 의존성 0). `.cube`(룩)와 달리 RAW 디모자이크 직후 색변환 단계용 색채측정 보정. Lightroom 실제 렌더링은 미검증(구조·수치 검증만) |
```

`docs/project_structure.md`의 `tools/classify_brand.py` 행 **다음**에 추가:

```markdown
| `tools/analyze_camera_native_matrix.py` | 카메라 네이티브 공간 색매트릭스 피팅 실험 CLI - `python3 -m tools.analyze_camera_native_matrix` (차트 10장을 `decode_raw_native()`로 디코드 -> XYZ(D50) 참조값에 피팅 -> libraw 내장 매트릭스와 leave-one-image-out 교차검증 비교, 리포트 JSON 저장) |
```

`docs/project_structure.en.md`의 `core/photo_signature.py` 행 **다음**에 추가:

```markdown
| `core/dcp_export.py` | Adobe DCP (camera profile) writing - exports a camera-native color matrix as a `.dcp` that Lightroom Classic/Camera Raw reads (`write_dcp`/`read_dcp`). DCP is TIFF-structured, so it's written directly with the standard-library `struct` (no new dependencies). Unlike `.cube` (a look), this is a colorimetric correction for the color-conversion stage right after RAW demosaic. Lightroom's actual rendering is unverified (only structure and numerics were checked) |
```

`docs/project_structure.en.md`의 `tools/classify_brand.py` 행 **다음**에 추가:

```markdown
| `tools/analyze_camera_native_matrix.py` | Camera-native color-matrix fitting experiment CLI - `python3 -m tools.analyze_camera_native_matrix` (decodes the 10 chart frames via `decode_raw_native()`, fits against XYZ(D50) references, compares to libraw's built-in matrix under leave-one-image-out cross-validation, saves a report JSON) |
```

- [ ] **Step 7: 전체 스위트 확인 + 커밋 + 푸시**

Run: `python3 -m unittest discover -s tests`
Expected: `OK`, 362 tests

```bash
git add hybrid_engine/EVALUATION.md README.md README.ko.md \
        docs/project_structure.md docs/project_structure.en.md
# 게이트를 통과해 프로필을 생성한 경우에만 아래 줄도 함께 add
# git add hybrid_engine/assets/profiles/hasselblad_x2dii_chart.dcp
git commit -m "Document camera-native matrix results (follow-up measurement 21) + DCP export"
git push -u origin claude/unknown-character-0x48vp
```
