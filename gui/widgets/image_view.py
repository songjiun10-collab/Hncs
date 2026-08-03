"""Before/After 이미지를 나란히 보여주는 위젯. 픽셀 처리(리사이즈, 채널
변환)는 Tk 없이 테스트 가능하도록 prepare_for_display()로 분리한다."""
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
import rawpy
from PIL import Image, ImageTk

RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf", ".3fr", ".fff", ".dng"}


def prepare_for_display(img, max_width=480):
    """np.ndarray(BGR 3채널, 그레이스케일 2채널, 8/16비트 전부 허용)를
    화면 표시용 8비트 RGB PIL.Image로 변환한다. 16비트는 8비트로
    스케일다운(>>8), 2차원 그레이스케일은 BGR로 확장(brands/CLAUDE.md의
    apply_acros/apply_monochrome 예외 처리와 동일한 규칙)."""
    if img.dtype == np.uint16:
        img = (img >> 8).astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    h, w = img.shape[:2]
    if w > max_width:
        scale = max_width / w
        img = cv2.resize(img, (max_width, max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def quick_raw_preview(path):
    """RAW 파일의 빠른 프리뷰용 디코드(half_size, camera WB) -
    tools/lens_correction.py의 _load_image() RAW 분기와 동일한 rawpy
    호출에 half_size=True만 추가(hybrid_engine/utils/io.py의 half_size
    파라미터와 같은 목적 - 프리뷰용 다운스케일)."""
    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True,
                               output_bps=8, half_size=True)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


class ImageView(ttk.Frame):
    """Before/After 두 이미지를 나란히 그리는 프레임. show(before, after)로
    np.ndarray 두 장을 넘기면 각각 prepare_for_display()를 거쳐 갱신한다."""

    def __init__(self, master):
        super().__init__(master)
        self._before_label = ttk.Label(self, text="Before")
        self._after_label = ttk.Label(self, text="After")
        self._before_label.grid(row=0, column=0, padx=4, pady=4)
        self._after_label.grid(row=0, column=1, padx=4, pady=4)
        self._before_photo = None
        self._after_photo = None

    def show(self, before, after):
        self._before_photo = ImageTk.PhotoImage(prepare_for_display(before))
        self._after_photo = ImageTk.PhotoImage(prepare_for_display(after))
        self._before_label.configure(image=self._before_photo, text="")
        self._after_label.configure(image=self._after_photo, text="")
