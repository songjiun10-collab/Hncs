"""
[Phase 0] 카메라 고유 색특성 통일 ("색정제"). 카메라마다 센서/CFA/색매트릭스가
달라서 "raw RGB"가 가리키는 색 자체가 카메라마다 다르다 - Phase 1의
normalizer.py(Gray World)는 장면 콘텐츠에 의존하는 휴리스틱이라 이 차이를
다 못 지운다. 이 모듈은 그 앞단에서 두 가지를 한다:

  1. utils/io.py의 decode_raw()가 rawpy(libraw)를 통해 이미 적용한 "카메라
     고유 색매트릭스 -> 표준 RGB 프라이머리" 변환이 실제로 어떤 값을
     썼는지 투명하게 노출한다(extract_camera_metadata) - 카메라별 비교/
     감사용.
  2. 촬영 당시 카메라가 추정한 화이트밸런스(광원)가 표준 D65 기준광과
     어긋나는 잔차를, XYZ 공간에서 명시적인 Bradford 색순응변환으로 한 번
     더 눌러서 카메라 간 결과를 더 통일된 기준으로 맞춘다(unify_to_d65).

카메라 고유 색매트릭스 자체를 직접 재구현하지 않는 이유: DNG/제조사 고유
캘리브레이션 데이터라 rawpy(libraw)가 이미 각 RAW 파일에 내장된 정확한
값을 쓰고 있다 - 손으로 재구현하면 libraw보다 부정확해질 위험만 크고,
이미 신뢰할 수 있는 구현을 다시 만드는 과잉설계다.

**알려진 한계 (메타메리즘, 2026-07 설계 시점에 명시)**: 이 모듈이 하는
정규화는 "센서 반응의 최선 근사"일 뿐 완벽한 카메라 무관 중립 공간을
만들지 못한다. 실제 센서는 CFA 분광감도가 CIE 표준관측자 함수와
비례하는 Luther-Ives 조건을 만족하지 않기 때문에, 3x3 매트릭스로는 두
카메라가 같은 실제 피사체를 찍어도 XYZ가 정확히 일치하도록 만들 수
없다(메타메리즘 오차). 이 잔차는 원래 HNCS 프로젝트가 rawpy 베이스라인을
"더 정밀하게" 바꿔도 핫셀블라드 실제 파이프라인과 안 맞았던 사례
(docs/measurements.md 참고)와 같은 성격의 근본적 한계 - 더 줄이려면
같은 장면을 여러 센서로 실측 비교하거나(컬러차트/raw+jpeg 페어) 아니면
`utils/evaluate.py`의 ΔE 루프로 남은 오차를 profile 파라미터 튜닝으로
흡수하는 수밖에 없다.
"""
import numpy as np
import rawpy
import colour

_D65_XY = np.array([0.31270, 0.32900])


def extract_camera_metadata(raw_path):
    """진단/감사용 - 이 RAW 파일에 rawpy가 실제로 쓰는 카메라 고유
    색매트릭스와 화이트밸런스 배수를 그대로 노출한다."""
    with rawpy.imread(raw_path) as raw:
        return {
            "camera_whitebalance": list(raw.camera_whitebalance),
            "daylight_whitebalance": list(raw.daylight_whitebalance),
            "color_matrix": raw.color_matrix.tolist(),
            "rgb_xyz_matrix": raw.rgb_xyz_matrix.tolist(),
            "white_level": raw.white_level,
            "black_level_per_channel": list(raw.black_level_per_channel),
        }


def estimate_source_white_xy(camera_whitebalance):
    """camera_whitebalance(R/G/B/G2 배수)로부터 촬영 당시 광원의 대략적인
    백색점(CIE xy)을 역산한다 - WB 배수의 역수를 sRGB 값으로 해석해
    XYZ -> xy로 변환하는 근사법이지 정밀한 분광 기반 추정은 아니다."""
    r, g, b = camera_whitebalance[0], camera_whitebalance[1], camera_whitebalance[2]
    inv_rgb = np.array([1.0 / r, 1.0 / g, 1.0 / b])
    inv_rgb = inv_rgb / inv_rgb[1]  # G 채널 기준 정규화
    srgb = colour.RGB_COLOURSPACES["sRGB"]
    xyz = colour.RGB_to_XYZ(inv_rgb, srgb, apply_cctf_decoding=False)
    return colour.XYZ_to_xy(xyz)


def unify_to_d65(xyz_img, source_white_xy):
    """XYZ 이미지(임의 shape, 마지막 축이 3)를 촬영 당시 추정
    백색점(source_white_xy)에서 표준 D65 기준광으로 Bradford 색순응
    변환한다."""
    shape = xyz_img.shape
    flat = xyz_img.reshape(-1, 3)
    XYZ_w = colour.xy_to_XYZ(source_white_xy)
    XYZ_wr = colour.xy_to_XYZ(_D65_XY)
    adapted = colour.chromatic_adaptation(flat, XYZ_w, XYZ_wr,
                                           method="Von Kries", transform="Bradford")
    return adapted.reshape(shape)
