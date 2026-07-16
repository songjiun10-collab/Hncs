"""
RAW 디코딩 및 TIFF 입출력. rawpy로 어떤 카메라의 RAW든 16비트 Linear RGB로
순수하게 뽑아내고(감마/톤커브 없음 - 이후 파이프라인이 전부 처리), 최종
결과를 16비트 무손실 TIFF로 저장한다.
"""
import numpy as np
import rawpy
import cv2
import colour


def decode_raw(raw_path):
    """RAW -> Linear RGB, float64 [0, 1] 근방(하이라이트는 1을 넘을 수
    있음), shape (H, W, 3), RGB 순서. 카메라 고유 색공간이 아니라 sRGB
    프라이머리 기준 선형광(linear light) 값 - 이후 core/pipeline이
    이 프라이머리를 그대로 XYZ 변환 기준으로 쓴다."""
    with rawpy.imread(raw_path) as raw:
        rgb16 = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            output_bps=16,
            output_color=rawpy.ColorSpace.sRGB,
            gamma=(1, 1),  # 순수 linear
        )
    return rgb16.astype(np.float64) / 65535.0


def save_tiff16(rgb_linear, path, apply_srgb_encoding=True):
    """Linear RGB -> 16비트 TIFF 저장.

    apply_srgb_encoding=True(기본)면 sRGB OETF로 감마 인코딩해서 일반
    이미지 뷰어/에디터에서 정상적으로(너무 어둡지 않게) 보이는 파일을
    만든다. False면 순수 linear 값을 그대로 저장 - ΔE 평가나 후속 파이프
    라인에 다시 먹일 때처럼 linear 데이터가 필요한 경우에 쓴다."""
    clipped = np.clip(rgb_linear, 0.0, 1.0)
    if apply_srgb_encoding:
        clipped = colour.cctf_encoding(clipped, function="sRGB")
    u16 = (np.clip(clipped, 0.0, 1.0) * 65535.0 + 0.5).astype(np.uint16)
    bgr = u16[:, :, ::-1]
    cv2.imwrite(path, bgr)


def load_image_linear(path):
    """일반 이미지 파일(JPEG/TIFF/PNG 등, 이미 sRGB 감마 인코딩된
    "완성본")을 읽어서 Linear RGB float64 [0, 1]로 되돌린다. ΔE 평가에서
    타깃 이미지(예: 실제 카메라 JPEG)를 엔진 출력과 같은 도메인으로
    맞추기 위한 용도."""
    bgr = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise FileNotFoundError(path)
    if bgr.dtype == np.uint16:
        rgb = bgr[:, :, ::-1].astype(np.float64) / 65535.0
    else:
        rgb = bgr[:, :, ::-1].astype(np.float64) / 255.0
    return colour.cctf_decoding(rgb, function="sRGB")
