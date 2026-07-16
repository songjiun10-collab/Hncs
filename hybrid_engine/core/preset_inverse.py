"""
[Phase 0'] EXIF 기반 카메라 인식 -> 프리셋 역보정 -> 목표 브랜드 재적용.

메타메리즘 문제(core/color_matrix.py 참고) 때문에 물리적으로 완벽한
카메라 무관 색공간은 못 만든다는 한계를, 이 프로젝트가 이미 실측으로
확보해둔 자산으로 우회한다: `brands/*.py`의 population-fit 브랜드
10종(hasselblad + 9개)은 전부 `core.curve.film_curve`(toe+linear mid+
smoothstep shoulder, 단조함수)에 브랜드별 실측 toe_lift/white_point를
대입하는 동일 구조라, **닫힌 형태로 역산이 가능하다.**

흐름: EXIF Make/Model -> 소스 브랜드 추정 -> 그 브랜드 커브의 역함수로
"카메라 시그니처 제거" -> 근사 중립 상태 -> 타깃 브랜드의 실제 apply_*
함수(이미 검증된 기존 코드, 그대로 재사용)로 재렌더링.

알려진 한계:
  - CLAHE(지각보상 대비)는 역산하지 않는다 - 적응형(local) 연산이라 정확한
    역함수가 없고, 9개 population-fit 브랜드가 전부 clahe_clip=1.25(핫셀
    블라드 차용값, 미검증)를 공유해서 애초에 브랜드 구분력이 약하다.
    역산 대상은 toe_lift/shoulder_start/white_point로 만드는 L채널 톤
    커브뿐 - 채도/hue/텍스처는 population-fit 브랜드들이 원래 안 건드리는
    채널이라 역산할 것도 없다.
  - film_curve 자체가 "population 평균에 맞춘 근사"라 개별 사진의 실제
    렌더링과는 항상 오차가 있다 - 역산해도 그 오차가 사라지진 않는다.
  - Pentax와 Ricoh GR은 EXIF Make가 둘 다 "RICOH IMAGING COMPANY"로
    같이 찍혀 나오는 경우가 있어 Model 문자열("GR" 포함 여부)로 구분한다
    - 애매한 모델명이면 오판할 수 있음.
"""
import cv2
import numpy as np

from core.curve import film_curve
from brands import canon, leica, nikon, olympus, panasonic, pentax, phaseone, ricoh_gr, sigma, sony
from brands.hasselblad import apply_hncs

_LUT_SIZE = 4096

# population-fit 브랜드(핫셀블라드 포함 10종)의 정방향 apply_* 함수 -
# 타깃 브랜드 재적용 단계에서 그대로 재사용한다(새로 안 만듦).
BRAND_FUNCS = {
    "hasselblad": apply_hncs,
    "canon": canon.apply_canon_look,
    "leica": leica.apply_leica_look,
    "nikon": nikon.apply_nikon_look,
    "olympus": olympus.apply_olympus_look,
    "panasonic": panasonic.apply_panasonic_look,
    "pentax": pentax.apply_pentax_look,
    "phaseone": phaseone.apply_phaseone_look,
    "ricoh_gr": ricoh_gr.apply_ricoh_gr_look,
    "sigma": sigma.apply_sigma_look,
    "sony": sony.apply_sony_look,
}


def curve_params(brand):
    """brand의 apply_* 함수 기본 파라미터(toe_lift/shoulder_start/
    white_point)를 함수 시그니처에서 직접 읽어온다 - brands/*.py의 실측값을
    이 파일에 중복 기록하지 않고 항상 최신값을 그대로 참조하기 위함."""
    import inspect
    if brand not in BRAND_FUNCS:
        raise ValueError(f"알 수 없는 브랜드: {brand} (지원: {sorted(BRAND_FUNCS)})")
    sig = inspect.signature(BRAND_FUNCS[brand])
    return {
        "toe_lift": sig.parameters["toe_lift"].default,
        "shoulder_start": sig.parameters["shoulder_start"].default,
        "white_point": sig.parameters["white_point"].default,
    }


def _inverse_lut(toe_lift, shoulder_start, white_point):
    """film_curve(x)의 역함수를 (도메인, 치역) 쌍으로 반환 - film_curve가
    단조 비감소라 x/y를 swap한 뒤 np.interp로 그대로 역보간할 수 있다."""
    x = np.linspace(0.0, 1.0, _LUT_SIZE)
    y = film_curve(x, toe_lift, shoulder_start, white_point)
    return y, x  # (원래 y를 도메인으로, 원래 x를 치역으로)


def remove_camera_signature(img_bgr, brand):
    """img_bgr(이미 brand의 apply_* 특성이 적용된 완성 JPEG로 가정)에서
    그 브랜드의 L채널 톤커브만 역산해서 근사 중립 상태로 되돌린다.
    CLAHE는 역산하지 않음(모듈 docstring 참고)."""
    params = curve_params(brand)
    y_dom, x_range = _inverse_lut(**params)

    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l_norm = l.astype(np.float64) / 255.0
    l_neutral = np.interp(l_norm.ravel(), y_dom, x_range).reshape(l_norm.shape)
    l_out = np.clip(l_neutral * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.merge((l_out, a, b)), cv2.COLOR_LAB2BGR)


def convert_between_brands(img_bgr, source_brand, target_brand):
    """소스 브랜드 시그니처 제거 -> 타깃 브랜드 정방향 apply_* 재적용."""
    neutral = remove_camera_signature(img_bgr, source_brand)
    if target_brand not in BRAND_FUNCS:
        raise ValueError(f"알 수 없는 타깃 브랜드: {target_brand} (지원: {sorted(BRAND_FUNCS)})")
    return BRAND_FUNCS[target_brand](neutral)


def detect_brand_from_exif(make, model):
    """EXIF Make/Model 문자열로 BRAND_FUNCS 키를 추정한다. 못 알아보면
    None을 반환 - 호출부가 "역산 불가, 근거 데이터 없음"으로 처리해야
    한다(임의로 아무 브랜드나 추측해서 적용하면 안 됨)."""
    make_l = (make or "").lower()
    model_l = (model or "").lower()

    if "hasselblad" in make_l:
        return "hasselblad"
    if "phase one" in make_l or "phaseone" in make_l:
        return "phaseone"
    if "leica" in make_l:
        return "leica"
    if "sigma" in make_l:
        return "sigma"
    if "panasonic" in make_l or "lumix" in model_l:
        return "panasonic"
    if "olympus" in make_l or "om digital" in make_l:
        return "olympus"
    if "sony" in make_l:
        return "sony"
    if "nikon" in make_l:
        return "nikon"
    if "canon" in make_l:
        return "canon"
    if "ricoh" in make_l or "pentax" in make_l:
        # RICOH IMAGING이 Pentax/Ricoh GR 둘 다의 Make로 찍혀 나옴 -
        # Model 문자열로 GR 라인 여부를 구분(모듈 docstring의 한계 참고)
        return "ricoh_gr" if "gr" in model_l else "pentax"
    return None
