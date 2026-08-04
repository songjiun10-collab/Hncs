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


def raw_to_prophoto_linear(raw_path, use_camera_wb=True):
    """RAW -> ProPhoto RGB Linear, float64 [0, 1] 범위 (근사 - 하이라이트는
    1을 넘을 수 있음), shape (H, W, 3), RGB 순서.

    use_camera_wb=False면 카메라 WB 게인을 아예 안 걸고(rawpy user_wb를
    항등[1,1,1,1]로 고정) 디모자이크한다 - White Patch/Shades of Gray
    같은 이미지 기반 화이트밸런스 추정 알고리즘은 카메라 WB가 이미
    적용된 상태에 걸면 이중 보정이 되어 의미가 없으므로, 그 알고리즘을
    쓰는 쪽(estimate_wb_*)이 이 플래그로 원본 채널 비율을 먼저 받아야
    한다."""
    with rawpy.imread(raw_path) as raw:
        kwargs = dict(
            no_auto_bright=True,
            output_bps=16,
            output_color=rawpy.ColorSpace.ProPhoto,
            gamma=(1, 1),  # 순수 linear - 톤커브 없음
        )
        if use_camera_wb:
            kwargs["use_camera_wb"] = True
        else:
            kwargs["user_wb"] = [1.0, 1.0, 1.0, 1.0]
        rgb16 = raw.postprocess(**kwargs)
    return rgb16.astype(np.float64) / 65535.0


def apply_exposure(linear_rgb, ev=0.0):
    """linear 도메인에서 EV 스탑만큼 노출 보정 (양수=밝게)."""
    if ev == 0.0:
        return linear_rgb
    return linear_rgb * (2.0 ** ev)


def auto_exposure_average(linear_rgb, target_gray=0.18):
    """전체 평균 밝기를 middle gray로 맞추는 가장 단순한 자동노출
    (raw-alchemy의 average metering과 동급)."""
    mean = float(np.mean(linear_rgb))
    if mean <= 0:
        return linear_rgb
    return linear_rgb * (target_gray / mean)


def auto_exposure_highlight_safe(linear_rgb, percentile=99.5, target=0.9):
    """하이라이트 세이프 측광 - 화면에서 percentile 백분위수(기본
    99.5, 극소수 스펙큘러 하이라이트/센서 노이즈 한두 픽셀은 무시)에
    해당하는 밝기가 target(기본 0.9, 클리핑 전 여유를 둠)에 오도록
    노출을 맞춘다. average metering(전체 평균을 미드그레이로)과 달리
    하이라이트를 절대 태우지 않는 게 목표라, 콘트라스트가 큰 장면
    (창밖 하늘이 보이는 실내, 역광 등)에서 average metering이 하이라이트를
    날려버리는 걸 피할 수 있다 - 대신 전체적으로 더 어둡게 나올 수 있음
    (그림자 디테일을 희생해서 하이라이트를 지키는 전형적인 트레이드오프)."""
    luma = linear_rgb.mean(axis=-1) if linear_rgb.ndim == 3 else linear_rgb
    p = float(np.percentile(luma, percentile))
    if p <= 0:
        return linear_rgb
    return linear_rgb * (target / p)


def auto_exposure_matrix(linear_rgb, target_gray=0.18, center_weight=3.0, n_zones=5):
    """매트릭스(평가) 측광 - 카메라의 다분할 측광을 흉내내서, 화면을
    n_zones x n_zones 격자로 나누고 중앙 영역에 center_weight배 가중치를
    준 가중평균을 middle gray에 맞춘다. average metering(순수 전체
    평균)은 가장자리의 극단적인 밝기(창밖 하늘, 어두운 구석)에 쉽게
    휘둘리는데, 이 모드는 보통 피사체가 있는 중앙을 우선시해서 그 영향을
    줄인다 - 실제 카메라의 "평가측광"/"멀티존 측광"과 같은 발상."""
    luma = linear_rgb.mean(axis=-1) if linear_rgb.ndim == 3 else linear_rgb
    h, w = luma.shape
    row_edges = np.linspace(0, h, n_zones + 1).astype(int)
    col_edges = np.linspace(0, w, n_zones + 1).astype(int)
    center_idx = (n_zones - 1) / 2.0

    weighted_sum = 0.0
    weight_total = 0.0
    for i in range(n_zones):
        for j in range(n_zones):
            zone = luma[row_edges[i]:row_edges[i + 1], col_edges[j]:col_edges[j + 1]]
            if zone.size == 0:
                continue
            dist_from_center = np.hypot(i - center_idx, j - center_idx)
            max_dist = np.hypot(center_idx, center_idx)
            proximity = 1.0 - (dist_from_center / max_dist if max_dist > 0 else 0.0)
            weight = 1.0 + (center_weight - 1.0) * proximity
            weighted_sum += float(zone.mean()) * weight
            weight_total += weight

    if weight_total <= 0:
        return linear_rgb
    weighted_mean = weighted_sum / weight_total
    if weighted_mean <= 0:
        return linear_rgb
    return linear_rgb * (target_gray / weighted_mean)


def estimate_wb_white_patch(linear_rgb, percentile=99.9):
    """White Patch(Max-RGB Retinex) 화이트밸런스 추정 - 채널별 상위
    percentile(기본 99.9 - 순수 100은 핫픽셀/센서노이즈 한두 개에
    흔들리기 쉬워 살짝 낮춤) 밝기가 조명색을 반사한 흰/회색 표면이라고
    가정하고, 그 값이 1(흰색)이 되도록 채널마다 독립적으로 게인을
    건다(Land의 Retinex 이론에서 나온 고전적 색항상성 알고리즘).
    raw_to_prophoto_linear(..., use_camera_wb=False)로 카메라 WB 없이
    디코드한 결과에 적용해야 의미가 있다 - 이미 WB된 이미지에 걸면
    이중보정이 된다.

    실측(2026-08, docs/measurements.md "White Patch/Shades of Gray 자동
    화이트밸런스 정확도"): raw_calib_cache 13장(실사진, 컬러차트 아님)
    기준 카메라 실제 AsShotNeutral 대비 평균 ΔE00 15.80(ΔE00<2.0이 "구별
    안 됨" 기준이라 명백히 다른 색감) - 장면 안에 진짜 중립 표면이
    있다는 전제가 실사진에서 자주 깨져서(밝은 색유리/하늘 등이 있으면
    채널비가 1.000으로 saturate) 실사용 권장 안 함.

    후속 실측(2026-08, docs/measurements.md "ΔE00 낮추기 시도"/"노이즈가
    ΔE00의 원인인가"): 채도 높은 픽셀 제외, 앙상블(shades_of_gray와 평균)
    둘 다 개선 안 됨(오히려 소폭 악화) - 파라미터/알고리즘 변경 없음.
    결과물의 노이즈 증폭(채널 게인이 그 채널 센서노이즈를 비례증폭)은
    실재하지만, 74쌍 전체 픽셀 단위 블러 테스트에서 노이즈 제거가 평균
    ΔE00을 낮추지 못함(오히려 평균 -3.9%로 소폭 악화) - 위 ΔE00은 노이즈가
    아니라 순수 체계적 색편차."""
    flat = linear_rgb.reshape(-1, 3)
    channel_patch = np.percentile(flat, percentile, axis=0)
    channel_patch = np.where(channel_patch <= 0, 1.0, channel_patch)
    return linear_rgb / channel_patch


def estimate_wb_shades_of_gray(linear_rgb, p=6):
    """Shades of Gray(Finlayson & Trezzi 2004) 화이트밸런스 추정 - Gray
    World(p=1, 채널별 산술평균)와 White Patch/Max-RGB(p->무한대)를
    민코프스키 p-노름 하나로 일반화한 방법. 채널별 (mean(x^p))^(1/p)을
    조명색 추정치로 쓰고, 그 추정치 벡터를 자기 노름으로 정규화해
    나눠서(전체 밝기는 유지한 채 색만 중화) 게인을 건다. 기본 p=6은
    원 논문이 여러 조명 이미지셋 실측으로 고른 값. White Patch와 마찬가지로
    use_camera_wb=False로 디코드한 결과에 적용해야 한다.

    실측(2026-08, docs/measurements.md 같은 절): raw_calib_cache 13장
    기준 평균 ΔE00 14.04 - White Patch보다 근소하게 낫지만 마찬가지로
    실사용 권장 안 함(자세한 수치/원인은 White Patch 쪽 docstring 참고).

    후속 실측(2026-08, docs/measurements.md "ΔE00 낮추기 시도"/"노이즈가
    ΔE00의 원인인가"): 채도 높은 픽셀 제외, 앙상블 둘 다 개선 안 됨(자세한
    수치는 White Patch 쪽 docstring 참고) - 파라미터(p=6) 변경 없음. 이
    함수의 게인이 채널별 센서노이즈를 비례증폭하는 것도 실재하지만,
    74쌍 전체 블러 테스트에서 노이즈 제거가 평균 ΔE00을 낮추지 못함(평균
    -3.9%로 오히려 소폭 악화) - 위 ΔE00은 노이즈가 아니라 순수 체계적
    색편차."""
    flat = np.clip(linear_rgb.reshape(-1, 3), 0, None)
    illuminant = np.power(np.mean(np.power(flat, p), axis=0), 1.0 / p)
    illuminant = np.where(illuminant <= 0, 1.0, illuminant)
    illuminant = illuminant / np.linalg.norm(illuminant)
    return linear_rgb / illuminant


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


# 이름 -> colour.cctf_encoding()용 함수 이름. Log 커브와 달리 둘 다
# BT.2020(=Rec.2100과 같은 프라이머리) 색역 하나만 쓴다.
HDR_SPACES = {
    "PQ": "ITU-R BT.2100 PQ",
    "HLG": "ITU-R BT.2100 HLG",
}
_HDR_GAMUT = "ITU-R BT.2020"


def to_hdr_space(linear_prophoto_rgb, hdr_space, peak_nits=1000.0):
    """ProPhoto RGB Linear -> BT.2020 색역의 PQ(SMPTE ST 2084) 또는
    HLG(Hybrid Log-Gamma) 인코딩. Log 커브(scene-referred, 절대 밝기
    기준점 없음)와 달리 PQ/HLG는 둘 다 **절대 cd/m^2(nits) 입력을
    기대하는 display-referred 함수**다(colour-science의
    `eotf_inverse_ST2084`/`eotf_inverse_BT2100_HLG` 실측 확인 - "HLG는
    PQ와 달리 절대기준 불필요"라는 처음 가정은 틀렸음, HLG도 nominal peak
    luminance(L_W)를 요구한다). 그래서 linear의 1.0(기준 화이트)이
    peak_nits cd/m^2에 대응한다고 보고 그 값을 곱해서 넘긴다 - PQ는
    ST 2084 스펙상 항상 10000nit 시스템피크를 가정하므로 peak_nits는
    "1.0이 몇 nit인가"만 결정하고, HLG는 `L_W=peak_nits`를 직접 전달해
    같은 값을 시스템 피크로도 쓴다.

    반환값은 [0, 1] 근방의 PQ/HLG 인코딩된 RGB (Log 커브와 마찬가지로
    색역 밖 값은 클리핑하지 않음 - 저장 단계에서 처리).

    **미검증**: 실제 HDR10/HLG 대응 디스플레이나 DaVinci Resolve 등에서
    이 출력이 의도한 대로 보이는지는 확인 못 함 - colour-science 함수
    정의를 그대로 신뢰한 것으로, 이 프로젝트의 다른 "미검증" 항목과 같은
    성격의 caveat."""
    if hdr_space not in HDR_SPACES:
        raise ValueError(f"지원하지 않는 hdr_space: {hdr_space} "
                          f"(지원: {sorted(HDR_SPACES)})")
    if peak_nits <= 0:
        raise ValueError(f"peak_nits는 0보다 커야 함: {peak_nits}")

    curve_name = HDR_SPACES[hdr_space]
    target_gamut = colour.RGB_COLOURSPACES[_HDR_GAMUT]
    gamut_linear = colour.RGB_to_RGB(linear_prophoto_rgb, _PROPHOTO, target_gamut)
    gamut_linear = np.clip(gamut_linear, 0.0, None)  # 음수(색역 밖) 방지
    nits = gamut_linear * peak_nits
    kwargs = {"L_W": peak_nits} if hdr_space == "HLG" else {}
    return colour.cctf_encoding(nits, function=curve_name, **kwargs)


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


def write_exr(rgb_float, path, compression="zip"):
    """32비트 float OpenEXR 저장 - Log/씬 참조(scene-referred) 워크플로우의
    실제 업계 표준 포맷. 16비트 정수 TIFF와 달리 클리핑이 필요 없다(Log
    인코딩된 값도, 그 이전의 linear 값도 있는 그대로 float으로 저장되고
    DaVinci Resolve/Nuke 등 컬러 그레이딩 툴이 직접 읽는다). compression은
    "none"/"rle"/"zips"/"zip"/"piz"/"pxr24"/"b44"/"b44a"/"dwaa"/"dwab" 중
    선택(OpenEXR 표준 압축 방식, 기본 zip이 무손실+합리적 속도로 무난)."""
    import OpenEXR

    compression_map = {
        "none": OpenEXR.NO_COMPRESSION,
        "rle": OpenEXR.RLE_COMPRESSION,
        "zips": OpenEXR.ZIPS_COMPRESSION,
        "zip": OpenEXR.ZIP_COMPRESSION,
        "piz": OpenEXR.PIZ_COMPRESSION,
        "pxr24": OpenEXR.PXR24_COMPRESSION,
        "b44": OpenEXR.B44_COMPRESSION,
        "b44a": OpenEXR.B44A_COMPRESSION,
        "dwaa": OpenEXR.DWAA_COMPRESSION,
        "dwab": OpenEXR.DWAB_COMPRESSION,
    }
    if compression not in compression_map:
        raise ValueError(f"지원하지 않는 compression: {compression!r} "
                          f"(지원: {sorted(compression_map)})")

    header = {"compression": compression_map[compression], "type": OpenEXR.scanlineimage}
    channels = {"RGB": rgb_float.astype(np.float32)}
    OpenEXR.File(header, channels).write(path)
