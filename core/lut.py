"""LUT 적용 헬퍼."""
import cv2
import numpy as np


def apply_lut(img, lut):
    if img.dtype != np.uint8:
        img = np.clip(img * 255, 0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)
