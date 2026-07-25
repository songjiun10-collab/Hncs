"""
[GitHub 이슈 #4 지적 4번 대응] ColorChecker Classic 차트로 raw 베이스라인의
"진짜" 색채측정학적 오차를 정량화한다.

`raw_baseline.py`(Phase 0)는 실사진 raw+jpeg 페어로 "rawpy 기본 디코드가
카메라 JPEG를 얼마나 못 맞추는가"를 잰다 - 타깃이 카메라 자체의(의도적
채도 부스트 등이 섞인) JPEG 렌더링이라 색채측정학적으로 "정답"이 아니다.
이 모듈은 반대로 진짜 정답(제조사가 분광측정으로 발행한 ColorChecker
Classic 24패치 참조값)과 rawpy 기본 디코드를 직접 비교해서, rawpy
기본 매트릭스 자체가 얼마나 정확한 색채측정 변환인지, 그리고 차트로
직접 피팅한 매트릭스가 그 오차를 얼마나 줄이는지를 측정한다.

칩 위치는 OpenCV의 cv2.mcc(Macbeth ColorChecker Detector, opencv 5.x
기준 opencv-python에 포함)로 자동 검출한다 - 수동 좌표 지정 없이 아무
차트 촬영본에나 재사용 가능. 참조값은 colour-science가 내장한
'ColorChecker24 - After November 2014'(Calibrite/X-Rite 공식 분광측정
기반) 데이터셋을 그대로 쓴다.

100MP급 원본에서 바로 색공간 변환을 돌리면 메모리를 19GB 넘게 먹고
OOM으로 죽는다(실측) - 그래서 detect_and_sample()은 decode_raw() 직후
바로 리사이즈부터 한다.
"""
import cv2
import numpy as np
import colour

_SRGB = colour.RGB_COLOURSPACES["sRGB"]
D50_XY = colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"]

# 표준 4x6 ColorChecker Classic 레이아웃의 canonical 순서 (row-major,
# dark skin이 좌상단). colour-science 데이터셋과 cv2.mcc의 getRefColors()
# 둘 다 이 순서를 쓰는 것을 실측으로 확인함(로그 참고).
PATCH_NAMES = [
    "dark skin", "light skin", "blue sky", "foliage", "blue flower", "bluish green",
    "orange", "purplish blue", "moderate red", "purple", "yellow green", "orange yellow",
    "blue", "green", "red", "yellow", "magenta", "cyan",
    "white 9.5 (.05 D)", "neutral 8 (.23 D)", "neutral 6.5 (.44 D)",
    "neutral 5 (.70 D)", "neutral 3.5 (1.05 D)", "black 2 (1.5 D)",
]


def reference_patches_linear_srgb():
    """ColorChecker Classic 24패치의 공식 참조값을, 이 프로젝트의 나머지
    ΔE 계산과 같은 공간(선형 sRGB 프라이머리, D65 백색점)으로 변환해서
    반환. (24, 3) ndarray, PATCH_NAMES와 같은 순서.

    colour-science 데이터셋은 CIE Illuminant C 기준 xyY라서, sRGB의
    D65 백색점으로 Bradford CAT 색순응을 거쳐야 한다(XYZ_to_RGB의
    illuminant 인자로 자동 처리됨)."""
    cc = colour.CCS_COLOURCHECKERS["ColorChecker24 - After November 2014"]
    xyY = np.array([cc.data[name] for name in PATCH_NAMES])
    XYZ = colour.xyY_to_XYZ(xyY)
    rgb_linear = colour.XYZ_to_RGB(
        XYZ, _SRGB, cc.illuminant,
        chromatic_adaptation_transform="Bradford",
        apply_cctf_encoding=False,
    )
    return rgb_linear


def reference_patches_xyz_d50():
    """ColorChecker Classic 24패치의 공식 참조값을 XYZ(D50)로 변환해서
    반환. (24, 3) ndarray, PATCH_NAMES와 같은 순서.

    reference_patches_linear_srgb()가 sRGB 프라이머리/D65로 가는 것과
    달리 이건 XYZ D50으로 간다 - Adobe DNG/DCP 프로필의 기준 공간이
    XYZ D50이기 때문(ColorMatrix1이 정의상 XYZ(D50) -> 카메라 네이티브
    RGB). 이 colour-science 버전이 내장한 'ColorChecker24 - After
    November 2014' 데이터셋의 cc.illuminant는 이미 D50에 가까운 값
    ([0.3457, 0.3585] 근처)이라, 이 데이터셋에 한해서는 아래 Bradford
    색순응이 사실상 항등변환에 가깝다. 다만 코드는 cc.illuminant를
    하드코딩하지 않고 항상 동적으로 읽어서 색순응하므로, 향후
    colour-science 데이터셋 버전이 바뀌어 기준 백색점이 실제 Illuminant C나
    다른 값으로 바뀌더라도 여전히 올바르게 동작한다."""
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


def _detect_chart_bgr8(bgr_u8):
    """cv2.mcc로 24패치 차트를 검출. 성공 시 (24, 4, 2) 꼭짓점 배열
    (PATCH_NAMES 순서), 실패 시 None."""
    detector = cv2.mcc.CCheckerDetector_create()
    detector.setColorChartType(cv2.mcc.MCC24)
    if not detector.process(bgr_u8):
        return None
    checker = detector.getListColorChecker()[0]
    return checker.getColorCharts().reshape(24, 4, 2)


def detect_and_sample(linear_rgb, max_dim=2000, shrink=0.5):
    """decode_raw() 출력(선형 RGB, 임의 해상도)에서 24패치를 자동 검출해서
    각 패치 중심부(경계 색번짐을 피하려고 bounding box를 shrink 비율로
    축소)의 평균 선형 RGB를 반환. (24, 3) ndarray, PATCH_NAMES 순서.
    검출 실패 시 None.

    검출 자체는 리사이즈 + 퍼센타일 정규화 + sRGB 인코딩한 8비트 프리뷰로
    하지만(cv2.mcc가 일반 사진처럼 렌더링된 8비트 입력을 기대), 실제
    패치 값 샘플링은 그 프리뷰가 아니라 원본 선형 값에서 한다."""
    h, w = linear_rgb.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    small = cv2.resize(linear_rgb.astype(np.float32), (int(w * scale), int(h * scale)),
                        interpolation=cv2.INTER_AREA) if scale < 1.0 else linear_rgb.astype(np.float32)

    lo, hi = np.percentile(small, 0.5), np.percentile(small, 99.5)
    norm = np.clip((small - lo) / max(hi - lo, 1e-8), 0.0, 1.0)
    preview_srgb = colour.cctf_encoding(norm, function="sRGB")
    bgr_u8 = (preview_srgb * 255).astype(np.uint8)[:, :, ::-1].copy()

    quads = _detect_chart_bgr8(bgr_u8)
    if quads is None:
        return None

    samples = np.zeros((24, 3), dtype=np.float64)
    img_h, img_w = small.shape[:2]
    for i, quad in enumerate(quads):
        x0, y0 = quad.min(axis=0)
        x1, y1 = quad.max(axis=0)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        hw, hh = (x1 - x0) / 2.0 * shrink, (y1 - y0) / 2.0 * shrink
        sx0 = int(np.clip(cx - hw, 0, img_w - 1))
        sx1 = int(np.clip(cx + hw, sx0 + 1, img_w))
        sy0 = int(np.clip(cy - hh, 0, img_h - 1))
        sy1 = int(np.clip(cy + hh, sy0 + 1, img_h))
        samples[i] = small[sy0:sy1, sx0:sx1].reshape(-1, 3).mean(axis=0)
    return samples


def patch_delta_e(samples_linear_rgb, reference_linear_rgb=None, method="CIE 2000"):
    """샘플링된 (N, 3) 선형 RGB와 참조값 사이의 패치별 ΔE00. reference
    생략 시 reference_patches_linear_srgb()를 씀. metrics.py의
    _to_lab()과 동일한 변환(sRGB 프라이머리, apply_cctf_decoding=False)."""
    if reference_linear_rgb is None:
        reference_linear_rgb = reference_patches_linear_srgb()
    xyz_a = colour.RGB_to_XYZ(samples_linear_rgb, _SRGB, apply_cctf_decoding=False)
    xyz_b = colour.RGB_to_XYZ(reference_linear_rgb, _SRGB, apply_cctf_decoding=False)
    lab_a = colour.XYZ_to_Lab(xyz_a)
    lab_b = colour.XYZ_to_Lab(xyz_b)
    return np.asarray(colour.delta_E(lab_a, lab_b, method=method))
