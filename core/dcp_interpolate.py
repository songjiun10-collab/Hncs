"""DNG dual-illuminant `ColorMatrix1`/`ColorMatrix2` 보간 - Adobe DNG
스펙이 문서화한 알고리즘의 재현(Adobe DNG SDK 바이너리 자체가 아니라,
그 스펙을 따르는 공개 구현들 - RawTherapee `dcp.cc`의
`DCPProfile::MakeXYZCAM`, darktable `colorin.c` - 이 쓰는 것과 같은
알고리즘). `tools/refit_x2dii_dual_illuminant.py`가 처음 배포할 때 쓴
"측정 R/G를 두 기준 클러스터 R/G 사이에서 선형보간"은 이 프로젝트가
급조한 근사였다 - 이 모듈이 그걸 실제 알고리즘으로 교체한다
(`hybrid_engine/EVALUATION.md` "X2D II 100C dual-illuminant" 절
참고, 사용자가 "만들어내"로 지시).

**핵심 아이디어(고정점 반복)**: `ColorMatrix1`/`ColorMatrix2`는 각각
`CalibrationIlluminant1`/`2`(예: D65/Standard Light A) 아래서 캘리브레이션된
"XYZ(D50) -> 카메라 네이티브" 행렬이다. 실제 촬영 조명이 그 둘 중
어디에 더 가까운지는 촬영본의 white balance 중립색(`AsShotNeutral`)을
봐야 아는데, 그 중립색을 XYZ로 변환하려면 이미 보간된 매트릭스가
필요하다 - 순환 의존. DNG 스펙은 이걸 **고정점 반복**으로 푼다:

1. 보간 가중치 g(1=illuminant1, 0=illuminant2)를 0.5로 초기화.
2. `CM(g) = g*CM1 + (1-g)*CM2` (**행렬 자체를 성분별로 선형보간** -
   역행렬이 아니라 DCP에 저장되는 형태 그대로. 역행렬은 선형보간과
   교환되지 않으므로(`inv(g*A+(1-g)*B) != g*inv(A)+(1-g)*inv(B)`) 이
   순서가 중요하다 - Adobe가 실제로 보간하는 건 저장된 `CM1`/`CM2`
   그 자체다).
3. `CM(g)`를 뒤집어 `native -> XYZ`로 촬영본의 중립색을 XYZ로 변환.
4. 그 XYZ의 색도좌표(xy)에서 상관색온도(CCT)를 McCamy(1992) 근사식으로
   추정.
5. 두 기준 조명의 CCT를 mired(=1e6/CCT, Adobe가 색온도를 선형보간하는
   표준 단위 - Kelvin이 아니라 mired에서 선형이어야 지각적으로 고른
   보간이 된다) 공간으로 바꿔서 새 g를 계산.
6. g가 수렴할 때까지(보통 몇 번 안에 수렴) 2-5 반복.

**한계(정직하게 명시)**: 이건 DNG 스펙이 공개 문서화한 알고리즘의
재구현이지, Adobe DNG SDK 바이너리를 실행한 결과가 아니다. Lightroom/
ACR이 내부적으로 미세하게 다른 반올림/클램핑을 할 가능성은 남아있다 -
실기기 검증 전까지는 여전히 근사로 취급해야 한다(기존 파일들의
"실기기 미검증" 패턴과 동일 성격). 이전의 R/G 선형보간 근사보다
스펙에 훨씬 가깝다는 것이지, 완전한 재현이라는 뜻은 아니다.

참고: McCamy, C.S. (1992), "Correlation of color temperature with
chromaticity of daylight and incandescent light sources", Color
Research & Application. xy<->CCT 근사식이 실사용되는 표준 공식이다."""
import numpy as np

# 표준 EXIF LightSource enum -> 상관색온도(K). DNG/EXIF 스펙이 이
# 매핑을 이름으로만 정의하고(예: "Standard Light A"), 그 이름이 가리키는
# CIE 표준광의 CCT는 색채과학 표준값이다.
STANDARD_ILLUMINANT_CCT_K = {
    17: 2856.0,  # Standard Light A(백열/텅스텐)
    21: 6504.0,  # D65
    23: 5003.0,  # D50
}


def _xyz_to_xy(xyz):
    xyz = np.asarray(xyz, dtype=np.float64)
    s = xyz.sum()
    if s <= 0:
        return 0.3127, 0.3290  # D65 근처로 폴백(퇴화 입력 방어)
    return float(xyz[0] / s), float(xyz[1] / s)


def _cct_from_xy(x, y):
    """McCamy(1992) 근사식. 2856K~6504K(Standard Light A~D65) 범위에서
    표준적으로 쓰이는 근사 - 이 프로젝트의 두 보정 illuminant가 정확히
    그 범위 안이다."""
    n = (x - 0.3320) / (y - 0.1858)
    return -449.0 * n**3 + 3525.0 * n**2 - 6823.3 * n + 5520.33


def interpolate_dng_matrix(camera_neutral, color_matrix_1, illuminant_1,
                            color_matrix_2, illuminant_2,
                            max_iter=30, tol=1e-6):
    """DNG dual-illuminant 고정점 보간.

    camera_neutral: 카메라 네이티브 RGB 3벡터(그 이미지의 화이트밸런스
        중립색 추정치 - 이 프로젝트에서는 무채색 패치 평균, G=1 정규화).
    color_matrix_1/2: DCP `ColorMatrix1`/`ColorMatrix2`와 같은 형태 -
        XYZ(D50) -> 카메라 네이티브, **열벡터 규약**(3x3 또는 길이9).
        `write_dcp()`에 넘기는 것과 정확히 같은 값(예: 이 프로젝트의
        `dcp_color_matrix_1`/`dcp_color_matrix_2` 리포트 필드).
    illuminant_1/2: `STANDARD_ILLUMINANT_CCT_K`의 키(EXIF LightSource
        enum, 예: 21=D65, 17=Standard Light A).

    반환: (native_to_xyz_row_matrix, g) - 첫 번째는 이 프로젝트의 행벡터
    규약(`raw_baseline.apply_color_matrix()`에 바로 쓸 수 있는 (3,3),
    `xyz_row = native_row @ 반환값`)으로 변환된 최종 보간 매트릭스.
    g는 수렴한 보간 가중치(1=illuminant_1 전적으로, 0=illuminant_2
    전적으로)."""
    cm1 = np.asarray(color_matrix_1, dtype=np.float64).reshape(3, 3)
    cm2 = np.asarray(color_matrix_2, dtype=np.float64).reshape(3, 3)
    neutral = np.asarray(camera_neutral, dtype=np.float64).reshape(3)

    cct1 = STANDARD_ILLUMINANT_CCT_K[illuminant_1]
    cct2 = STANDARD_ILLUMINANT_CCT_K[illuminant_2]
    mired1 = 1.0e6 / cct1
    mired2 = 1.0e6 / cct2

    if np.allclose(cm1, cm2):
        # 퇴화 케이스: 둘이 같으면 g가 뭐든 결과가 같다 - 반복 없이 바로 반환.
        return np.linalg.inv(cm1).T, 0.5

    g = 0.5
    for _ in range(max_iter):
        cm = g * cm1 + (1.0 - g) * cm2
        cam_to_xyz = np.linalg.inv(cm)
        xyz = cam_to_xyz @ neutral
        x, y = _xyz_to_xy(xyz)
        cct = _cct_from_xy(x, y)
        mired = 1.0e6 / cct
        g_new = (mired - mired2) / (mired1 - mired2)
        g_new = float(np.clip(g_new, 0.0, 1.0))
        if abs(g_new - g) < tol:
            g = g_new
            break
        g = g_new

    cm_final = g * cm1 + (1.0 - g) * cm2
    native_to_xyz_row = np.linalg.inv(cm_final).T
    return native_to_xyz_row, g
