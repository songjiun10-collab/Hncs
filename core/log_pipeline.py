"""
RAW -> Log 색공간 변환 파이프라인. HNCS의 나머지 코드(브랜드별 apply_*)가
"이 카메라가 실제로 뽑는 JPEG 색을 근사"하는 것과는 목적이 다르다 - 여기는
카메라 종류에 무관하게 RAW를 표준 중간 색공간(ProPhoto RGB Linear)으로
통일한 뒤, 원하는 영상 카메라의 Log 커브/색역으로 인코딩해서 그 카메라용
크리에이티브 LUT(.cube)를 RAW 사진에도 색 어긋남 없이 적용할 수 있게 한다
(참고: https://github.com/shenmintao/raw-alchemy - 같은 문제의식, 이 모듈은
그 파이프라인을 colour-science 기반으로 재구현한 것).

파이프라인: RAW -> ProPhoto RGB Linear -> (노출 보정) -> 타깃 Log 색역
(linear) -> 타깃 Log 커브 인코딩 -> (선택) .cube LUT 적용

Log 커브/색역 페어링(F-Log2+F-Gamut 등)은 각 제조사 공식 스펙을 따랐다고
자신할 만큼 전수 검증한 건 아니다 - colour-science가 제공하는 정의를
그대로 쓴 것으로, HNCS의 다른 "미검증" 라벨과 같은 성격의 caveat.
"""
import numpy as np
import rawpy
import colour

# 이름 -> (colour.log_encoding용 커브 이름, colour.RGB_COLOURSPACES용 색역 이름)
LOG_SPACES = {
    "F-Log": ("F-Log", "F-Gamut"),
    "F-Log2": ("F-Log2", "F-Gamut"),
    "V-Log": ("V-Log", "V-Gamut"),
    "N-Log": ("N-Log", "N-Gamut"),
    "Canon Log 2": ("Canon Log 2", "Cinema Gamut"),
    "Canon Log 3": ("Canon Log 3", "Cinema Gamut"),
    "S-Log3": ("S-Log3", "S-Gamut3"),
    "S-Log3.Cine": ("S-Log3", "S-Gamut3.Cine"),
    "Arri LogC3": ("ARRI LogC3", "ARRI Wide Gamut 3"),
    "Arri LogC4": ("ARRI LogC4", "ARRI Wide Gamut 4"),
    "Log3G10": ("Log3G10", "REDWideGamutRGB"),
    "D-Log": ("D-Log", "DJI D-Gamut"),
}

_PROPHOTO = colour.RGB_COLOURSPACES["ProPhoto RGB"]


def raw_to_prophoto_linear(raw_path):
    """RAW -> ProPhoto RGB Linear, float64 [0, 1] 범위 (근사 - 하이라이트는
    1을 넘을 수 있음), shape (H, W, 3), RGB 순서."""
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=16,
            output_color=rawpy.ColorSpace.ProPhoto,
            gamma=(1, 1),  # 순수 linear - 톤커브 없음
        )
    return rgb16.astype(np.float64) / 65535.0


def apply_exposure(linear_rgb, ev=0.0):
    """linear 도메인에서 EV 스탑만큼 노출 보정 (양수=밝게)."""
    if ev == 0.0:
        return linear_rgb
    return linear_rgb * (2.0 ** ev)


def auto_exposure_average(linear_rgb, target_gray=0.18):
    """전체 평균 밝기를 middle gray로 맞추는 가장 단순한 자동노출
    (raw-alchemy의 average metering과 동급 - matrix/highlight-safe 같은
    정교한 모드는 아직 없음)."""
    mean = float(np.mean(linear_rgb))
    if mean <= 0:
        return linear_rgb
    return linear_rgb * (target_gray / mean)


def to_log_space(linear_prophoto_rgb, log_space):
    """ProPhoto RGB Linear -> 타깃 Log 색역/커브. 반환값은 [0, 1] 근방의
    Log 인코딩된 RGB (색역 밖 값은 클리핑하지 않음 - LUT 적용/저장 단계에서
    처리)."""
    if log_space not in LOG_SPACES:
        raise ValueError(f"지원하지 않는 log_space: {log_space} "
                          f"(지원: {sorted(LOG_SPACES)})")
    curve_name, gamut_name = LOG_SPACES[log_space]
    target_gamut = colour.RGB_COLOURSPACES[gamut_name]
    gamut_linear = colour.RGB_to_RGB(linear_prophoto_rgb, _PROPHOTO, target_gamut)
    gamut_linear = np.clip(gamut_linear, 0.0, None)  # 음수(색역 밖) 방지
    return colour.log_encoding(gamut_linear, curve_name)


def apply_cube_lut(rgb_float, lut_path):
    """.cube 3D LUT 파일을 로드해서 적용 (trilinear 보간, colour-science
    LUT3D.apply 사용)."""
    lut = colour.io.read_LUT(lut_path)
    return lut.apply(np.clip(rgb_float, 0.0, 1.0))


def to_16bit_bgr(rgb_float):
    """cv2.imwrite로 저장 가능한 16비트 BGR array로 변환 (클리핑 포함)."""
    clipped = np.clip(rgb_float, 0.0, 1.0)
    u16 = (clipped * 65535.0 + 0.5).astype(np.uint16)
    return u16[:, :, ::-1]  # RGB -> BGR
