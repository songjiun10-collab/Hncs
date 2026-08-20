"""LUT 적용 헬퍼."""
import cv2
import numpy as np


def ensure_uint8(img):
    """apply_* 프리셋들은 uint8 BGR([0,255])을 가정하고 cv2.cvtColor로
    HSV/LAB 변환을 거는데, float 입력(예: [0,1] 정규화 이미지)이 그대로
    들어오면 cv2가 이미 정규화된 값으로 오해석해 결과가 조용히 깨진다."""
    if img.dtype != np.uint8:
        return np.clip(img * 255, 0, 255).astype(np.uint8)
    return img


def apply_lut(img, lut):
    img = ensure_uint8(img)
    return cv2.LUT(img, lut)
