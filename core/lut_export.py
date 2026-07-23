"""brands/*.py의 apply_* 함수(임의의 BGR->BGR 변환, 내부 로직이
제각각)를 표준 3D LUT(.cube)로 구워내는 도구 - "포토샵 프리셋"의 실질적
구현체. Photoshop은 파라메트릭 ACR 프리셋(.xmp)과 달리 Color Lookup
조정 레이어로 .cube 파일을 직접 읽을 수 있어서, apply_* 내부가 HSV/Lab
변환이든 CLAHE든 뭐든 상관없이 "입력 색 -> 출력 색" 대응만 저장하면
브랜드 룩을 그대로 옮길 수 있다(DaVinci Resolve/Premiere/After Effects도
같은 .cube를 읽음).

한계: apply_* 함수 중 CLAHE(적응형 지역 대비, 예: fuji.apply_pro_neg_hi)를
쓰는 것들은 결과가 "이 픽셀 값"뿐 아니라 "주변 픽셀 분포"에도 좌우되는데,
3D LUT은 정의상 픽셀별 독립 매핑(같은 입력 색은 항상 같은 출력 색)이라
이 지역 적응성을 구조적으로 담을 수 없다 - 이건 LUT 포맷 자체의 근본적
한계지 이 코드의 버그가 아니다. 그런 함수는 "격자점 전체를 하나의 합성
이미지로 만들어 한 번에 통과"시켜서 CLAHE가 최소한 안정적인(격자 구조에
의존하는) 결과를 내게는 하지만, 실제 사진에 적용했을 때와 완전히
같지는 않다."""
import numpy as np


def build_identity_grid(size=33):
    """0~1 범위를 size단계로 균등분할한 (size, size, size, 3) RGB 격자
    (identity - 아직 아무 변환도 안 된 값). 인덱스는 [b_idx, g_idx, r_idx]
    순서로 저장해서 write_cube_file()의 순회 순서(R이 가장 빨리 바뀜)와
    바로 맞물리게 한다."""
    axis = np.linspace(0.0, 1.0, size)
    r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")  # r/g/b shape (size,size,size), 각각 axis0=b,axis1=g,axis2=r로 아래에서 재배열
    # meshgrid(indexing="ij")의 축 순서를 b,g,r로 명시적으로 맞춤(R이 마지막 축=가장 빨리 바뀜)
    grid = np.stack([r, g, b], axis=-1)  # 이 시점 axis0/1/2가 각각 r,g,b 격자축 - 아래서 전치
    return np.transpose(grid, (2, 1, 0, 3))  # -> axis0=b, axis1=g, axis2=r, 마지막 축=[R,G,B]값


def bake_lut_from_function(apply_fn, size=33, **fn_kwargs):
    """apply_fn(BGR uint8 이미지 -> BGR uint8 이미지)을 identity 격자
    전체에 한 번에 통과시켜서 (size,size,size,3) RGB(0~1 float) LUT을
    만든다. 격자를 (size*size, size, 3) 모양의 합성 "이미지" 하나로 펴서
    한 번만 호출 - 픽셀 하나씩 호출하면 CLAHE 같은 적응형 연산이 무의미한
    1x1 입력을 받게 되는 것을 피하기 위함(모듈 docstring의 한계 참고)."""
    grid = build_identity_grid(size)  # (size,size,size,3), RGB
    flat = grid.reshape(size * size, size, 3)
    bgr_u8 = np.clip(flat[..., ::-1] * 255.0 + 0.5, 0, 255).astype(np.uint8)  # RGB->BGR, uint8

    out_bgr_u8 = apply_fn(bgr_u8, **fn_kwargs) if fn_kwargs else apply_fn(bgr_u8)
    if out_bgr_u8.ndim == 2:  # apply_acros/apply_monochrome처럼 그레이스케일 반환하는 함수 방지
        raise ValueError("그레이스케일(단일 채널)을 반환하는 함수는 3D LUT으로 구울 수 없음")

    out_rgb = out_bgr_u8[..., ::-1].astype(np.float64) / 255.0  # BGR->RGB, [0,1]
    return out_rgb.reshape(size, size, size, 3)


def write_cube_file(lut_rgb, path, title=None):
    """(size,size,size,3) RGB LUT을 표준 Adobe .cube 텍스트 포맷으로
    저장 - Photoshop(Color Lookup 조정 레이어)/DaVinci Resolve/Premiere/
    After Effects가 전부 읽는다. 격자점 순회 순서는 스펙대로 R이 가장
    빨리 바뀌고 그다음 G, 그다음 B(build_identity_grid의 axis 순서와
    일치)."""
    size = lut_rgb.shape[0]
    lines = []
    if title:
        lines.append(f'TITLE "{title}"')
    lines.append(f"LUT_3D_SIZE {size}")
    lines.append("DOMAIN_MIN 0.0 0.0 0.0")
    lines.append("DOMAIN_MAX 1.0 1.0 1.0")
    for b_idx in range(size):
        for g_idx in range(size):
            for r_idx in range(size):
                rr, gg, bb = np.clip(lut_rgb[b_idx, g_idx, r_idx], 0.0, 1.0)
                lines.append(f"{rr:.6f} {gg:.6f} {bb:.6f}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
